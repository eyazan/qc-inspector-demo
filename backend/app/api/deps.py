from functools import lru_cache

from app.services.pipeline_service import PipelineService
from app.services.spec_service import SpecService
from app.services.storage_service import StorageService


@lru_cache
def get_storage_service() -> StorageService:
    return StorageService()


@lru_cache
def get_pipeline_service() -> PipelineService:
    return PipelineService(get_storage_service())


@lru_cache
def get_spec_service() -> SpecService:
    return SpecService()
