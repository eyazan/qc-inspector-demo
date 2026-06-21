"""Spec indexing + search routes (Section 5, adapted to the repo's /api prefix).

The indexing pipeline (2B) is normally driven by scripts/index_specs.py; this
synchronous endpoint is a convenience for on-demand runs. Search/get expose the
spec store to clients.
"""

from fastapi import APIRouter, HTTPException, Query

from app.jobs.factory import get_job_queue
from app.providers.factory import get_spec_store
from app.services.spec_indexing_service import SpecIndexingService

router = APIRouter(prefix="/api", tags=["spec-index"])


@router.post("/spec-index/run")
def run_spec_index(
    mode: str = "incremental", spec_name: str | None = None, async_mode: bool = False
) -> dict:
    """Sync by default; async_mode=true submits a background job (Section 5)."""
    if async_mode:
        job = get_job_queue().submit("spec_index", {"mode": mode, "spec_name": spec_name})
        return {"status": "submitted", "run_id": job.id, "job": job.to_dict()}
    summary = SpecIndexingService().run(mode=mode, spec_name=spec_name)
    return {"status": "completed", **summary}


@router.get("/spec-index/status/{run_id}")
def spec_index_status(run_id: str) -> dict:
    job = get_job_queue().store.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Indeksleme isi bulunamadi")
    return job.to_dict()


@router.get("/specs")
def list_specs(limit: int = 200) -> dict:
    """List indexed specs (slim view for the Spec Index screen)."""
    store = get_spec_store()
    rows = store.list_specs()[:limit]
    results = [
        {
            "id": r.get("id"),
            "spec_no": r.get("spec_no"),
            "revision": r.get("revision"),
            "status": r.get("status"),
            "file_path": r.get("file_path"),
            "content_hash": (r.get("content_hash") or "")[:12],
            "indexed_at": r.get("indexed_at"),
        }
        for r in rows
    ]
    return {"count": len(results), "results": results}


@router.get("/specs/search")
def search_specs(query: str = Query(...), limit: int = 10) -> dict:
    matches = get_spec_store().search(query, limit=limit)
    return {"query": query, "count": len(matches), "results": matches}


@router.get("/specs/{spec_id}")
def get_spec(spec_id: int) -> dict:
    store = get_spec_store()
    for spec in store.list_specs():
        if spec.get("id") == spec_id:
            return {
                **spec,
                "sections": store.get_sections(spec_id),
                "references": store.get_references(spec_id),
            }
    raise HTTPException(status_code=404, detail="Spec bulunamadi")
