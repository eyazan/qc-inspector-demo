"""Job model + file-backed JobStore.

Jobs are the durable unit of async work (vendor pipeline, spec indexing). Records
are persisted as JSON under data/jobs/{job_id}.json so status/result survive a
process restart and are inspectable, and so failed jobs are retained as a
dead-letter record. The store is an interface so a DB-backed impl can drop in.
"""

import json
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings

# Status lifecycle: pending -> running -> (completed | failed | dead_letter)
#                   pending/running -> cancelled
JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"
JOB_DEAD_LETTER = "dead_letter"
JOB_CANCELLED = "cancelled"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    type: str
    status: str = JOB_PENDING
    params: dict = field(default_factory=dict)
    result: Optional[dict] = None
    error: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 1
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


class JobStore(ABC):
    @abstractmethod
    def create(self, job_type: str, params: dict, max_attempts: int) -> Job: ...

    @abstractmethod
    def get(self, job_id: str) -> Optional[Job]: ...

    @abstractmethod
    def save(self, job: Job) -> None: ...

    @abstractmethod
    def list(self) -> list[Job]: ...


class FileJobStore(JobStore):
    def __init__(self, root: Path | None = None):
        self._root = Path(root or (settings.data_root / "jobs"))
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, job_id: str) -> Path:
        return self._root / f"{job_id}.json"

    def create(self, job_type: str, params: dict, max_attempts: int) -> Job:
        job = Job(
            id=f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            type=job_type,
            params=params or {},
            max_attempts=max_attempts,
        )
        self.save(job)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        path = self._path(job_id)
        if not path.exists():
            return None
        return Job(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, job: Job) -> None:
        job.updated_at = _now()
        with self._lock:
            self._path(job.id).write_text(
                json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

    def list(self) -> list[Job]:
        out = []
        for p in sorted(self._root.glob("job_*.json"), reverse=True):
            try:
                out.append(Job(**json.loads(p.read_text(encoding="utf-8"))))
            except Exception:  # noqa: BLE001
                continue
        return out
