"""Spec text extraction — native-first, OCR fallback (Section 2B step 5).

Returns page-by-page text so section/clause parsing can track page numbers.
Digital PDFs are read directly with PyMuPDF; scanned PDFs (no extractable text)
fall back to the SAME layout+OCR pipeline used for vendor docs.
"""

from pathlib import Path

import fitz

from app.core.logging import get_logger

logger = get_logger(__name__)

# Minimum chars of native text per page (averaged) to trust native extraction.
_MIN_NATIVE_CHARS_PER_PAGE = 20


class SpecOcrPipelineService:
    def __init__(self, ocr_pipeline=None):
        self._ocr_pipeline = ocr_pipeline

    def extract_pages(self, pdf_path: Path) -> tuple[list[str], str]:
        """Return (pages_text, source) where source is 'native' or 'ocr'."""
        native = self._native_pages(pdf_path)
        total = sum(len(p) for p in native)
        if native and total >= _MIN_NATIVE_CHARS_PER_PAGE * len(native):
            return native, "native"

        if self._ocr_pipeline is None:
            logger.warning(
                "Native metin yetersiz ve ocr_pipeline yok (%s); native donduruluyor",
                Path(pdf_path).name,
            )
            return native, "native"

        return self._ocr_pages(pdf_path), "ocr"

    def _native_pages(self, pdf_path: Path) -> list[str]:
        pages: list[str] = []
        try:
            doc = fitz.open(str(pdf_path))
            for page in doc:
                pages.append(page.get_text() or "")
            doc.close()
        except Exception as err:  # noqa: BLE001
            logger.warning("Native metin cikarma hatasi (%s): %s", Path(pdf_path).name, err)
        return pages

    def _ocr_pages(self, pdf_path: Path) -> list[str]:
        regions = self._ocr_pipeline.run(Path(pdf_path))
        by_page: dict[int, list] = {}
        for r in regions:
            by_page.setdefault(r.page_number, []).append(r)
        pages: list[str] = []
        for page_number in sorted(by_page):
            ordered = sorted(by_page[page_number], key=lambda r: (r.bbox[1] if r.bbox else 0))
            pages.append("\n".join(r.text for r in ordered if r.text))
        return pages
