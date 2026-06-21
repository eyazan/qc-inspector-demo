from fastapi import APIRouter

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas import HealthResponse

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Liveness — process is up."""
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)


# Mirror under the versioned prefix (Section 5).
@router.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
def health_v1() -> HealthResponse:
    return health()


@router.get("/health/ready", tags=["health"])
def ready() -> dict:
    """Readiness — checks reachability of the remote OCR + LLM services so a load
    balancer can gate traffic. Does not run inference; just probes /health."""
    import httpx

    def _probe(base_url: str) -> dict:
        try:
            url = base_url.rstrip("/")
            with httpx.Client(timeout=5.0, verify=settings.tls_verify_option) as c:
                # Try the service's /health (strip a trailing /v1 if present).
                root = url[:-3] if url.endswith("/v1") else url
                r = c.get(root + "/health")
                return {"url": base_url, "reachable": r.status_code < 500, "status": r.status_code}
        except Exception as err:  # noqa: BLE001
            return {"url": base_url, "reachable": False, "error": type(err).__name__}

    checks = {
        "layout": {"provider": settings.active_layout_provider, "local": True},
        "ocr": {"provider": settings.active_ocr_provider, **_probe(settings.ocr_service_url)},
        "llm": {"provider": settings.active_llm_provider, **_probe(settings.llm_base_url)},
    }
    all_ready = checks["ocr"].get("reachable", False) and checks["llm"].get("reachable", False)
    return {"status": "ready" if all_ready else "degraded", "checks": checks}


@router.get("/api/system/config", tags=["health"])
def system_config() -> dict:
    """Non-secret config summary for the System Health screen. NEVER returns
    tokens, passwords, or certificate contents — only what is safe to display."""
    return {
        "app": {"name": settings.app_name, "version": settings.app_version},
        "environment": settings.environment,
        "providers": {
            "layout": settings.active_layout_provider,
            "ocr": settings.active_ocr_provider,
            "llm": settings.active_llm_provider,
            "sap": settings.active_sap_provider or "(local fallback)",
            "spec_store": settings.active_spec_store,
        },
        "endpoints": {
            "ocr_base_url": settings.ocr_service_url or None,
            "llm_base_url": settings.llm_base_url or None,
            "sap_spec_endpoint": settings.sap_spec_endpoint or None,
        },
        "spec_indexing": {
            "network_root": str(settings.spec_network_root),
            "store_db": str(settings.spec_store_db_path),
            "schedule": settings.spec_index_schedule or "(disabled in-app)",
            "default_mode": settings.spec_index_mode,
        },
        "performance": {
            "page_parallelism": settings.page_parallelism,
            "ocr_batch_size": settings.ocr_batch_size,
            "ocr_max_workers": settings.ocr_max_concurrency,
        },
    }
