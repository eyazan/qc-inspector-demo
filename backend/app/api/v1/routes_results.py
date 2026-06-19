from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_storage_service
from app.schemas import (
    ComparisonResultItem,
    GenericMessageResponse,
    GroupedSegmentsResponse,
    RenameRequest,
    ReportResponse,
)
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api", tags=["results"])


@router.get("/comparison-results", response_model=list[ComparisonResultItem])
def comparison_results(
    storage: StorageService = Depends(get_storage_service),
) -> list[ComparisonResultItem]:
    return [ComparisonResultItem(**item) for item in storage.list_comparison_results()]


@router.get("/comparison-results/segments/grouped", response_model=GroupedSegmentsResponse)
def grouped_segments(
    storage: StorageService = Depends(get_storage_service),
) -> GroupedSegmentsResponse:
    return GroupedSegmentsResponse(**storage.grouped_segments())


@router.delete("/comparison-results/{result_id}", response_model=GenericMessageResponse)
def delete_result(
    result_id: str,
    storage: StorageService = Depends(get_storage_service),
) -> GenericMessageResponse:
    deleted = storage.delete_run(result_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sonuc bulunamadi")
    return GenericMessageResponse(status="success", message="Sonuc silindi")


@router.post("/comparison-results/{result_id}/rename", response_model=GenericMessageResponse)
def rename_result(
    result_id: str,
    request: RenameRequest,
    storage: StorageService = Depends(get_storage_service),
) -> GenericMessageResponse:
    renamed = storage.rename_run(result_id, request.new_name)
    if not renamed:
        raise HTTPException(status_code=404, detail="Sonuc bulunamadi")
    return GenericMessageResponse(status="success", message="Yeniden adlandirildi")


@router.get("/reports", response_model=list[ComparisonResultItem])
def all_reports(
    storage: StorageService = Depends(get_storage_service),
) -> list[ComparisonResultItem]:
    return [ComparisonResultItem(**item) for item in storage.list_comparison_results()]


@router.get("/report/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    storage: StorageService = Depends(get_storage_service),
) -> ReportResponse:
    report = storage.read_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi")
    return ReportResponse(**report)


@router.get("/report/{report_id}/enriched", response_model=ReportResponse)
def get_enriched_report(
    report_id: str,
    storage: StorageService = Depends(get_storage_service),
) -> ReportResponse:
    report = storage.read_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi")
    return ReportResponse(**report)


@router.get("/report/{report_id}/segments", response_model=GroupedSegmentsResponse)
def get_report_segments(
    report_id: str,
    storage: StorageService = Depends(get_storage_service),
) -> GroupedSegmentsResponse:
    return GroupedSegmentsResponse(**storage.grouped_segments())
