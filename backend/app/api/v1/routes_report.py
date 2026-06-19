"""PDF export route'u."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.deps import get_result_service
from app.services.report_service import build_compliance_pdf

router = APIRouter(prefix="/api", tags=["report"])


@router.get("/report/{run_id}/pdf")
def export_pdf(run_id: str, service=Depends(get_result_service)):
    report = service.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi")

    run_meta = {
        "id": report["id"],
        "po_number": report.get("po_number"),
        "po_item": report.get("po_item"),
        "material": report.get("material"),
    }
    pdf_bytes = build_compliance_pdf(run_meta, report["findings"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="QC_Rapor_{run_id}.pdf"'},
    )