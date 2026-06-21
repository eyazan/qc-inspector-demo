import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core import metrics
from app.core.config import settings
from app.core.errors import PipelineStageError
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.input_spec_path.mkdir(parents=True, exist_ok=True)
    settings.input_vendor_path.mkdir(parents=True, exist_ok=True)
    settings.output_path.mkdir(parents=True, exist_ok=True)
    settings.spec_source_dir.mkdir(parents=True, exist_ok=True)
    settings.spec_index_dir.mkdir(parents=True, exist_ok=True)
    settings.spec_output_dir.mkdir(parents=True, exist_ok=True)
    # Fail-fast config check for the selected providers (prompt Section 11).
    problems = settings.validate_for_providers()
    for p in problems:
        logger.error("CONFIG: %s", p)
    if problems and settings.environment == "production":
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
    try:
        from app.services.scheduler import shutdown_scheduler, start_scheduler

        if start_scheduler():
            logger.info("Spec indexing scheduler active")
    except Exception:  # noqa: BLE001
        logger.exception("Scheduler start failed (non-fatal)")
        shutdown_scheduler = None  # type: ignore
    logger.info("%s %s started", settings.app_name, settings.app_version)
    yield
    try:
        from app.services.scheduler import shutdown_scheduler

        shutdown_scheduler()
    except Exception:  # noqa: BLE001
        pass


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PipelineStageError)
    async def _pipeline_stage_error_handler(request: Request, exc: PipelineStageError):
        return JSONResponse(status_code=400, content=exc.to_dict())

    @app.middleware("http")
    async def _observability(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.monotonic()
        metrics.incr("http_requests_total")
        try:
            response = await call_next(request)
        except Exception:
            metrics.incr("http_errors_total")
            raise
        duration = time.monotonic() - start
        metrics.observe("http_request", duration)
        metrics.incr(f"http_status_{response.status_code // 100}xx")
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request id=%s %s %s -> %s %.3fs",
            request_id, request.method, request.url.path, response.status_code, duration,
        )
        return response

    @app.get("/metrics", tags=["health"])
    def metrics_endpoint():
        return JSONResponse(metrics.snapshot())

    @app.get("/metrics/prometheus", tags=["health"], response_class=PlainTextResponse)
    def metrics_prometheus():
        return metrics.render_prometheus()

    app.include_router(api_router)

    settings.output_path.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.static_mount_path,
        StaticFiles(directory=str(settings.output_path)),
        name="files",
    )

    return app


app = create_app()
