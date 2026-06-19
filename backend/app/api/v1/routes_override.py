"""Override route — inspector approves/rejects/edits an AI finding.

File-backed: the override is applied to the run's final_report.json (the live
vendor store). finding_id is globally unique ("<run_id>::F0001"), so only the id
is needed from the frontend.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_storage_service
from app.schemas import OverrideRequest, OverrideResponse
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api", tags=["override"])

_ACTION_STATUS = {
    "approve": None,
    "reject": "NON_COMPLIANT",
}


@router.post("/findings/{finding_id}/override", response_model=OverrideResponse)
def override_finding(
    finding_id: str,
    request: OverrideRequest,
    storage: StorageService = Depends(get_storage_service),
) -> OverrideResponse:
    new_status = request.new_status
    if new_status is None and request.action in _ACTION_STATUS:
        new_status = _ACTION_STATUS[request.action]

    updated = storage.apply_override(
        finding_id,
        {
            "action": request.action,
            "inspector_id": request.inspector_id,
            "new_status": new_status,
            "new_value": request.new_value,
            "note": request.note,
        },
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Bulgu bulunamadi")

    return OverrideResponse(status="success", finding_id=finding_id, new_status=new_status)
