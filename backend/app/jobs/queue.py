"""Job queue abstraction.

InProcessJobQueue runs registered handlers in a thread pool with retries and
dead-letter on final failure — no external broker, fully testable locally. A
CeleryJobQueue (or RQ/Arq) can be swapped in via ACTIVE_JOB_QUEUE without
changing callers or handlers.
"""

import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from app.core.config import settings
from app.core.logging import get_logger
from app.jobs.models import (
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_DEAD_LETTER,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    FileJobStore,
    Job,
    JobStore,
)

logger = get_logger(__name__)

# job_type -> handler(params: dict) -> dict (result)
_HANDLERS: dict[str, Callable[[dict], dict]] = {}


def register_handler(job_type: str, handler: Callable[[dict], dict]) -> None:
    _HANDLERS[job_type] = handler


class JobQueue(ABC):
    @abstractmethod
    def submit(self, job_type: str, params: dict, max_attempts: int | None = None) -> Job: ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...


class InProcessJobQueue(JobQueue):
    def __init__(self, store: JobStore | None = None):
        self._store = store or FileJobStore()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.job_workers), thread_name_prefix="job"
        )
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    @property
    def store(self) -> JobStore:
        return self._store

    def submit(self, job_type: str, params: dict, max_attempts: int | None = None) -> Job:
        if job_type not in _HANDLERS:
            raise ValueError(f"No handler registered for job type '{job_type}'")
        attempts = max_attempts if max_attempts is not None else settings.job_max_attempts
        job = self._store.create(job_type, params, attempts)
        self._executor.submit(self._run, job.id)
        return job

    def cancel(self, job_id: str) -> bool:
        job = self._store.get(job_id)
        if job is None:
            return False
        if job.status in (JOB_COMPLETED, JOB_FAILED, JOB_DEAD_LETTER, JOB_CANCELLED):
            return False
        with self._lock:
            self._cancelled.add(job_id)
        job.status = JOB_CANCELLED
        self._store.save(job)
        return True

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def _run(self, job_id: str) -> None:
        handler = None
        for attempt in range(1, 1_000_000):
            job = self._store.get(job_id)
            if job is None or self._is_cancelled(job_id):
                return
            if attempt > job.max_attempts:
                return
            handler = _HANDLERS.get(job.type)
            if handler is None:
                job.status = JOB_FAILED
                job.error = f"no handler for {job.type}"
                self._store.save(job)
                return

            job.status = JOB_RUNNING
            job.attempts = attempt
            self._store.save(job)
            try:
                result = handler(job.params)
                if self._is_cancelled(job_id):
                    return
                job.result = result if isinstance(result, dict) else {"result": result}
                job.status = JOB_COMPLETED
                job.error = None
                self._store.save(job)
                return
            except Exception as err:  # noqa: BLE001
                job.error = f"{type(err).__name__}: {err}"
                if attempt >= job.max_attempts:
                    job.status = JOB_DEAD_LETTER
                    self._store.save(job)
                    logger.error("Job %s dead-lettered after %s attempts: %s",
                                 job_id, attempt, job.error)
                    return
                job.status = JOB_PENDING
                self._store.save(job)
                logger.warning("Job %s attempt %s failed, retrying: %s",
                               job_id, attempt, job.error)


class CeleryJobQueue(JobQueue):  # pragma: no cover - future drop-in
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "CeleryJobQueue is a future drop-in; set ACTIVE_JOB_QUEUE=inprocess for now."
        )

    def submit(self, job_type, params, max_attempts=None):
        raise NotImplementedError

    def cancel(self, job_id):
        raise NotImplementedError
