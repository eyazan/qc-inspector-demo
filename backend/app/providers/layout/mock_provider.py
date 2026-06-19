"""Mock layout provider — no model load.

Splits the rendered page into a small vertical grid of regions so the rest of
the pipeline (crop -> OCR -> dedup -> segment) has realistic multi-region input
to exercise, with bbox in pixel coordinates of the rendered page.
"""

import io

from PIL import Image

from app.core.logging import get_logger
from app.providers.layout.base import LayoutProvider
from app.services.ocr.models import LayoutRegion

logger = get_logger(__name__)


class MockLayoutProvider(LayoutProvider):
    name = "mock"

    def __init__(self, rows: int = 4):
        self._rows = max(1, rows)

    def detect(self, page_image_png: bytes, page_number: int) -> list[LayoutRegion]:
        with Image.open(io.BytesIO(page_image_png)) as img:
            width, height = img.size

        regions: list[LayoutRegion] = []
        band = height / self._rows
        for i in range(self._rows):
            y0 = i * band
            y1 = (i + 1) * band
            regions.append(
                LayoutRegion(
                    region_id=f"page{page_number}_region{i}",
                    bbox=[0.0, float(y0), float(width), float(y1)],
                    page_number=page_number,
                    region_type="paragraph",
                )
            )
        logger.info("MockLayout: sayfa %s -> %s bolge", page_number, len(regions))
        return regions
