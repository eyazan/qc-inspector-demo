from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas import SpecLine, SpecQueryRequest, SpecQueryResponse

logger = get_logger(__name__)


class SpecService:
    def __init__(self):
        self._source_dir = settings.spec_source_dir

    def query(self, request: SpecQueryRequest) -> SpecQueryResponse:
        spec_file = self._resolve_spec_file(request)
        if spec_file is None or not spec_file.exists():
            return SpecQueryResponse(
                status="not_found",
                header_lines=self._header(request),
                lines=[],
            )

        text = spec_file.read_text(encoding="utf-8")
        lines = [
            SpecLine(tdline=line)
            for line in text.splitlines()
            if line.strip()
        ]
        return SpecQueryResponse(
            status="success",
            header_lines=self._header(request),
            lines=lines,
        )

    def _resolve_spec_file(self, request: SpecQueryRequest) -> Path | None:
        candidates = []
        if request.po_number and request.po_item:
            candidates.append(self._source_dir / f"{request.po_number}_{request.po_item}.md")
        if request.po_number:
            candidates.append(self._source_dir / f"{request.po_number}.md")
        if request.material:
            candidates.append(self._source_dir / f"{request.material}.md")
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _header(self, request: SpecQueryRequest) -> str:
        parts = []
        if request.po_number:
            parts.append(f"PO {request.po_number}")
        if request.po_item:
            parts.append(f"Item {request.po_item}")
        if request.material:
            parts.append(f"Malzeme {request.material}")
        return " | ".join(parts)
