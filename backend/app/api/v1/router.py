from fastapi import APIRouter

from app.api.v1 import (
    routes_health,
    routes_pipeline,
    routes_results,
    routes_spec,
    routes_upload,
)

api_router = APIRouter()
api_router.include_router(routes_health.router)
api_router.include_router(routes_spec.router)
api_router.include_router(routes_upload.router)
api_router.include_router(routes_pipeline.router)
api_router.include_router(routes_results.router)
