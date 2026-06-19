from typing import Optional

from pydantic import BaseModel, Field


class SpecQueryRequest(BaseModel):
    po_number: str = ""
    po_item: str = ""
    material: str = ""


class SpecLine(BaseModel):
    tdline: str


class SpecQueryResponse(BaseModel):
    status: str
    header_lines: Optional[str] = None
    lines: list[SpecLine] = Field(default_factory=list)


class UploadResponse(BaseModel):
    status: str
    filename: str
    is_spec: bool
    saved_path: str


class PipelineStartRequest(BaseModel):
    po_number: str = ""
    po_item: str = ""
    material: str = ""
    inspector_id: str = ""


class PipelineStartResponse(BaseModel):
    status: str
    run_id: Optional[str] = None
    message: str


class ProcessingStatusResponse(BaseModel):
    is_processing: bool
    current_step: str
    progress: int
    logs: list[str] = Field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    elapsed_seconds: int = 0
    run_id: Optional[str] = None
    status: Optional[str] = None


class CancelResponse(BaseModel):
    status: str
    message: str


class ComparisonResultItem(BaseModel):
    id: str
    type: str
    vendor_file: Optional[str] = None
    spec_file: Optional[str] = None
    po_info: Optional[str] = None
    display_name: Optional[str] = None
    timestamp: Optional[str] = None
    spec_pdf_path: Optional[str] = None
    vendor_pdf_path: Optional[str] = None


class ReportResponse(BaseModel):
    id: str
    type: str
    content: str
    filename: Optional[str] = None


class RenameRequest(BaseModel):
    new_name: str


class GenericMessageResponse(BaseModel):
    status: str
    message: str


class SegmentItem(BaseModel):
    id: str
    document_type: Optional[str] = None
    vendor_id: Optional[str] = None
    spec_document: Optional[str] = None
    content: str = ""
    filename: Optional[str] = None
    vendor_pdf_path: Optional[str] = None
    spec_pdf_path: Optional[str] = None


class DocumentTypeGroup(BaseModel):
    type: str
    count: int
    segments: list[SegmentItem] = Field(default_factory=list)


class GroupedSegmentsResponse(BaseModel):
    document_types: list[DocumentTypeGroup] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
