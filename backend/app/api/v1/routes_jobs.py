"""Generic async job APIs (Section: job queue).

Submit / Status / Result / Cancel. Additive to the existing /api/* flow (the
frozen frontend is unaffected). Used by spec indexing today; any registered job
type works. Dead-lettered jobs are retained and inspectable.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.jobs.factory import get_job_queue
from app.jobs.models import JOB_COMPLETED

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


class JobSubmitRequest(BaseModel):
    type: str
    params: dict = {}
    max_attempts: int | None = None


@router.post("")
def submit_job(request: JobSubmitRequest) -> dict:
    try:
        job = get_job_queue().submit(request.type, request.params, request.max_attempts)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return job.to_dict()


@router.get("/{job_id}")
def job_status(job_id: str) -> dict:
    job = get_job_queue().store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job bulunamadi")
    return job.to_dict()


@router.get("/{job_id}/result")
def job_result(job_id: str) -> dict:
    job = get_job_queue().store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job bulunamadi")
    if job.status != JOB_COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job not completed (status={job.status})")
    return {"id": job.id, "type": job.type, "result": job.result}


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    if not get_job_queue().cancel(job_id):
        raise HTTPException(status_code=409, detail="Job iptal edilemedi (yok ya da bitmis)")
    return {"id": job_id, "status": "cancelled"}
