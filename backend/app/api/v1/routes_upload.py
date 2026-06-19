from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_storage_service
from app.schemas import UploadResponse
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api", tags=["upload"])


def _parse_is_spec(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    is_spec: str = Form("false"),
    storage: StorageService = Depends(get_storage_service),
) -> UploadResponse:
    spec_flag = _parse_is_spec(is_spec)
    data = await file.read()
    saved = storage.save_upload(file.filename, data, spec_flag)
    return UploadResponse(
        status="success",
        filename=file.filename,
        is_spec=spec_flag,
        saved_path=str(saved),
    )
