"""Override route'lari — inspector AI sonucunu onayla/reddet/duzelt."""

from fastapi import APIRouter, HTTPException

from app.core.database import session_scope
from app.db.models import Finding
from app.db.repository import RunRepository
from app.schemas import OverrideRequest, OverrideResponse

router = APIRouter(prefix="/api", tags=["override"])

_ACTION_STATUS = {
    "approve": None,
    "reject": "NON_COMPLIANT",
}


@router.post("/findings/{finding_id}/override", response_model=OverrideResponse)
def override_finding(finding_id: int, request: OverrideRequest) -> OverrideResponse:
    new_status = request.new_status
    if new_status is None and request.action in _ACTION_STATUS:
        new_status = _ACTION_STATUS[request.action]

    with session_scope() as db:
        repo = RunRepository(db)
        finding = db.get(Finding, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail="Bulgu bulunamadi")
        repo.add_override(
            finding_id=finding_id,
            action=request.action,
            inspector_id=request.inspector_id,
            new_status=new_status,
            new_value=request.new_value,
            note=request.note,
        )

    return OverrideResponse(status="success", finding_id=finding_id, new_status=new_status)