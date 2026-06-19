from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
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
    logger.info("%s %s started", settings.app_name, settings.app_version)
    yield


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

    app.include_router(api_router)

    settings.output_path.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.static_mount_path,
        StaticFiles(directory=str(settings.output_path)),
        name="files",
    )

    return app


app = create_app()
