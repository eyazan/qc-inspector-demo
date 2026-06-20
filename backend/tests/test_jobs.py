"""Job queue: submit->complete, failure->retry->dead_letter, cancel.
Uses a temp file store + the in-process queue (no broker)."""

import time

from app.jobs.models import (
    JOB_COMPLETED,
    JOB_DEAD_LETTER,
    JOB_CANCELLED,
    FileJobStore,
)
from app.jobs.queue import InProcessJobQueue, register_handler


def _wait(store, job_id, terminal, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = store.get(job_id)
        if job and job.status in terminal:
            return job
        time.sleep(0.05)
    return store.get(job_id)


def test_submit_completes(tmp_path):
    store = FileJobStore(root=tmp_path)
    q = InProcessJobQueue(store=store)
    register_handler("echo", lambda p: {"echoed": p.get("x")})
    job = q.submit("echo", {"x": 42})
    done = _wait(store, job.id, {JOB_COMPLETED})
    assert done.status == JOB_COMPLETED
    assert done.result == {"echoed": 42}


def test_failure_dead_letters_after_retries(tmp_path):
    store = FileJobStore(root=tmp_path)
    q = InProcessJobQueue(store=store)
    calls = {"n": 0}

    def _boom(_):
        calls["n"] += 1
        raise RuntimeError("nope")

    register_handler("boom", _boom)
    job = q.submit("boom", {}, max_attempts=3)
    done = _wait(store, job.id, {JOB_DEAD_LETTER})
    assert done.status == JOB_DEAD_LETTER
    assert done.attempts == 3
    assert calls["n"] == 3
    assert "nope" in (done.error or "")


def test_unknown_type_rejected(tmp_path):
    q = InProcessJobQueue(store=FileJobStore(root=tmp_path))
    try:
        q.submit("does_not_exist", {})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_cancel_pending(tmp_path):
    store = FileJobStore(root=tmp_path)
    q = InProcessJobQueue(store=store)
    register_handler("slow", lambda p: (time.sleep(0.3) or {"ok": True}))
    job = q.submit("slow", {})
    assert q.cancel(job.id) is True
    job2 = store.get(job.id)
    assert job2.status == JOB_CANCELLED
