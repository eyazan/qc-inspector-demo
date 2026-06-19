"""Spec indexing + search routes (Section 5, adapted to the repo's /api prefix).

The indexing pipeline (2B) is normally driven by scripts/index_specs.py; this
synchronous endpoint is a convenience for on-demand runs. Search/get expose the
spec store to clients.
"""

from fastapi import APIRouter, HTTPException, Query

from app.providers.factory import get_spec_store
from app.services.spec_indexing_service import SpecIndexingService

router = APIRouter(prefix="/api", tags=["spec-index"])


@router.post("/spec-index/run")
def run_spec_index(mode: str = "incremental", spec_name: str | None = None) -> dict:
    summary = SpecIndexingService().run(mode=mode, spec_name=spec_name)
    return {"status": "completed", **summary}


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
