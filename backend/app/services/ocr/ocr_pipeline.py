from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import fitz

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr.models import LayoutRegion, OcrRegion

if TYPE_CHECKING:
    from app.providers.layout.base import LayoutProvider
    from app.providers.ocr.base import OcrProvider
    from app.services.dedup_service import DedupService

logger = get_logger(__name__)


class OcrPipeline:
    def __init__(
        self,
        layout_detector: "LayoutProvider",
        ocr_engine: "OcrProvider",
        dedup: "DedupService | None" = None,
    ):
        # Lazy import: dedup_service imports ocr.models, which loads this package.
        from app.services.dedup_service import DedupService

        self._layout_detector = layout_detector
        self._ocr_engine = ocr_engine
        self._dedup = dedup or DedupService()
        self._dpi = settings.pdf_render_dpi
        self._zoom = self._dpi / 72.0
        self._max_workers = settings.ocr_max_concurrency
        # Per-run dedup counts (before/after per page), surfaced to the report.
        self.dedup_stats: dict = {"before": 0, "after": 0, "removed": 0, "pages": []}

    def run(self, pdf_path: Path, max_pages: int | None = None) -> list[OcrRegion]:
        document = fitz.open(str(pdf_path))
        all_regions: list[OcrRegion] = []
        self.dedup_stats = {"before": 0, "after": 0, "removed": 0, "pages": []}

        page_count = document.page_count
        if max_pages:
            page_count = min(max_pages, page_count)

        for page_index in range(page_count):
            page = document[page_index]
            page_number = page_index + 1
            page_png = self._render_page(page)
            layout_regions = self._layout_detector.detect(page_png, page_number)
            kept, stats = self._dedup.deduplicate(layout_regions)
            self._accumulate_stats(page_number, stats)
            page_results = self._recognize_regions(page, kept)
            all_regions.extend(page_results)

        document.close()
        return all_regions

    def _accumulate_stats(self, page_number: int, stats: dict) -> None:
        self.dedup_stats["before"] += stats["before"]
        self.dedup_stats["after"] += stats["after"]
        self.dedup_stats["removed"] += stats["removed"]
        self.dedup_stats["pages"].append({"page": page_number, **stats})

    def _render_page(self, page) -> bytes:
        matrix = fitz.Matrix(self._zoom, self._zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        return pixmap.tobytes("png")

    def _crop_region(self, page, bbox: list[float]) -> bytes:
        # Layout bbox is in PIXEL coords of the page rendered at self._zoom.
        # fitz clip rects are in PDF points, so divide by zoom before clipping,
        # then re-render the clipped region at full dpi.
        rect = fitz.Rect(*[c / self._zoom for c in bbox])
        matrix = fitz.Matrix(self._zoom, self._zoom)
        pixmap = page.get_pixmap(matrix=matrix, clip=rect)

        try:
            return pixmap.tobytes("png")
        except Exception:
            try:
                return pixmap.tobytes("jpeg")
            except Exception:
                logger.warning(
                    "PNG/JPEG donusumu basarisiz (sayfa %s); bos bytes donduruluyor",
                    getattr(page, "number", "?"),
                )
                return b""

    def _recognize_regions(
        self, page, layout_regions: list[LayoutRegion]
    ) -> list[OcrRegion]:
        crops = [(region, self._crop_region(page, region.bbox)) for region in layout_regions]

        def recognize(item):
            region, crop = item
            text, confidence = self._ocr_engine.recognize(crop)
            return OcrRegion(
                region_id=region.region_id,
                text=text,
                bbox=region.bbox,
                page_number=region.page_number,
                region_type=region.region_type,
                confidence=confidence,
            )

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            results = list(executor.map(recognize, crops))

        return results
