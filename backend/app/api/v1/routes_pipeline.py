from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from app.api.deps import get_pipeline_service, get_storage_service
from app.schemas import (
    CancelResponse,
    PipelineStartRequest,
    PipelineStartResponse,
    ProcessingStatusResponse,
)
from app.services.pipeline_service import PipelineService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api", tags=["pipeline"])


# ---- AŞAMA 1: yükleme pipeline'ı başlat ----
@router.post("/start-full-pipeline", response_model=PipelineStartResponse)
def start_full_pipeline(
    request: PipelineStartRequest | None = None,
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> PipelineStartResponse:
    seed = request.model_dump() if request else None
    started, message, run_id = pipeline.start_upload(seed=seed)
    return PipelineStartResponse(
        status="started" if started else "rejected",
        run_id=run_id,
        message=message,
    )


# ---- run_id bazlı durum ----
@router.get("/processing-status/{run_id}", response_model=ProcessingStatusResponse)
def processing_status(
    run_id: str,
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> ProcessingStatusResponse:
    return ProcessingStatusResponse(**pipeline.status(run_id))


@router.post("/cancel-processing/{run_id}", response_model=CancelResponse)
def cancel_processing(
    run_id: str,
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> CancelResponse:
    pipeline.cancel(run_id)
    return CancelResponse(status="cancelled", message="Islem iptal edildi")


# ---- AŞAMA 1 sonucu: önizleme verisi ----
@router.get("/spec-preview/{run_id}")
def spec_preview(
    run_id: str,
    storage: StorageService = Depends(get_storage_service),
) -> dict:
    preview = storage.read_preview(run_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Onizleme bulunamadi")
    return preview


def _serve_pdf(storage: StorageService, run_id: str, is_spec: bool, missing: str):
    """Local file first, else object-store fallback (S3/MinIO). Same response
    shape either way, so the frontend /api/* contract is unchanged."""
    path = storage.spec_pdf_file(run_id) if is_spec else storage.vendor_pdf_file(run_id)
    if path is not None and path.exists():
        return FileResponse(str(path), media_type="application/pdf", filename=path.name)
    found = storage.read_pdf_bytes(run_id, is_spec=is_spec)
    if found is None:
        raise HTTPException(status_code=404, detail=missing)
    data, name = found
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


# ---- vendor PDF servis ----
@router.get("/document/{run_id}/{kind}")
def get_document(
    run_id: str,
    kind: str,
    storage: StorageService = Depends(get_storage_service),
):
    return _serve_pdf(storage, run_id, is_spec=(kind != "vendor"), missing="Dokuman bulunamadi")


# ---- spec PDF servis ----
@router.get("/spec-document/{run_id}")
def get_spec_document(
    run_id: str,
    storage: StorageService = Depends(get_storage_service),
):
    return _serve_pdf(storage, run_id, is_spec=True, missing="Spec dokumani bulunamadi")


# ---- AŞAMA 2: karşılaştırmayı başlat ----
@router.post("/start-comparison/{run_id}", response_model=PipelineStartResponse)
def start_comparison(
    run_id: str,
    pipeline: PipelineService = Depends(get_pipeline_service),
) -> PipelineStartResponse:
    started, message = pipeline.start_comparison(run_id)
    return PipelineStartResponse(
        status="started" if started else "rejected",
        run_id=run_id,
        message=message,
    )
