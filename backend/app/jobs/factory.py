"""Job queue singleton + handler registration (ACTIVE_JOB_QUEUE)."""

from functools import lru_cache

from app.core.config import settings
from app.jobs.queue import InProcessJobQueue, JobQueue, register_handler


def _spec_index_handler(params: dict) -> dict:
    from app.services.spec_indexing_service import SpecIndexingService

    return SpecIndexingService().run(
        mode=params.get("mode", "incremental"), spec_name=params.get("spec_name")
    )


def _register_handlers() -> None:
    register_handler("spec_index", _spec_index_handler)


@lru_cache
def get_job_queue() -> JobQueue:
    _register_handlers()
    if (settings.active_job_queue or "inprocess") == "celery":
        from app.jobs.queue import CeleryJobQueue

        return CeleryJobQueue()
    return InProcessJobQueue()
