from fastapi import APIRouter

from app.core.config import settings
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)
