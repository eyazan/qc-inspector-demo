from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr.layout_detector import LayoutDetector
from app.services.ocr.models import LayoutRegion, OcrRegion
from app.services.ocr.ocr_engine import OcrEngine

logger = get_logger(__name__)


class OcrPipeline:
    def __init__(self, layout_detector: LayoutDetector, ocr_engine: OcrEngine):
        self._layout_detector = layout_detector
        self._ocr_engine = ocr_engine
        self._dpi = settings.pdf_render_dpi
        self._max_workers = settings.ocr_max_concurrency

    def run(self, pdf_path: Path, max_pages: int | None = None) -> list[OcrRegion]:
        document = fitz.open(str(pdf_path))
        all_regions: list[OcrRegion] = []

        page_count = document.page_count
        if max_pages:
            page_count = min(max_pages, page_count)

        for page_index in range(page_count):
            page = document[page_index]
            page_number = page_index + 1
            page_png = self._render_page(page)
            layout_regions = self._layout_detector.detect(page_png, page_number)
            page_results = self._recognize_regions(page, layout_regions)
            all_regions.extend(page_results)

        document.close()
        return all_regions

    def _render_page(self, page) -> bytes:
        zoom = self._dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        return pixmap.tobytes("png")

    def _crop_region(self, page, bbox: list[float]) -> bytes:
        rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
        zoom = self._dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, clip=rect)
        
        # PNG formatında dene, hata olursa JPEG dene
        try:
            return pixmap.tobytes("png")
        except Exception:
            try:
                return pixmap.tobytes("jpeg")
            except Exception:
                logger.warning(f"PNG and JPEG conversion failed for region on page {page.number}, returning empty bytes")
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
