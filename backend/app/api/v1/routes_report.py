"""PDF export + review-regions routes (file-backed)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.deps import get_storage_service
from app.core.config import settings
from app.schemas import ReviewRegion
from app.services.report_service import build_compliance_pdf
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api", tags=["report"])

# Structured result enum -> the report_service status vocabulary.
_RESULT_TO_PDF_STATUS = {
    "COMPLIANT": "COMPLIANT",
    "NON_COMPLIANT": "NON_COMPLIANT",
    "NOT_COVERED_IN_THIS_DOCUMENT": "NOT_COVERED",
    "MISSING": "MISSING",
    "UNCLEAR": "PARTIAL",
}


def _to_pdf_finding(f: dict) -> dict:
    status = f.get("effective_result") or f.get("result")
    return {
        "parameter": f.get("parameter"),
        "spec_value": f.get("spec_evidence"),
        "vendor_value": f.get("vendor_evidence"),
        "status": _RESULT_TO_PDF_STATUS.get(status, "PARTIAL"),
        "severity": f.get("severity"),
        "spec_section": f.get("spec_section"),
        "rationale": f.get("rationale"),
        "override_note": f.get("override_note"),
    }


@router.get("/report/{run_id}/pdf")
def export_pdf(run_id: str, storage: StorageService = Depends(get_storage_service)):
    report = storage.read_final_report_json(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi")

    preview = storage.read_preview(run_id) or {}
    run_meta = {
        "id": run_id,
        "po_number": preview.get("po_number"),
        "po_item": preview.get("po_item"),
        "material": preview.get("material"),
    }
    findings = [_to_pdf_finding(f) for f in report.get("findings", [])]
    pdf_bytes = build_compliance_pdf(run_meta, findings)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="QC_Rapor_{run_id}.pdf"'},
    )


# Returns a bare ARRAY — the InspectorReport screen reads `regions.length`.
@router.get("/report/{run_id}/review-regions", response_model=list[ReviewRegion])
def review_regions(
    run_id: str, storage: StorageService = Depends(get_storage_service)
) -> list[ReviewRegion]:
    regions = storage.regions_for_review_list(run_id, settings.ocr_review_min_confidence)
    return [
        ReviewRegion(
            region_id=r.get("region_id", ""),
            page_number=r.get("page_number", 0),
            region_type=r.get("region_type"),
            text=r.get("text", "") or "",
            confidence=r.get("confidence"),
        )
        for r in regions
    ]
