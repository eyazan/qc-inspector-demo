"""PP-DocLayoutV3 layout provider — LOCAL paddlex on this machine (CPU).

Delegates to the existing thread-affine LayoutDetector so the proven paddlex
loading/threading logic is reused rather than duplicated.
"""

from app.providers.layout.base import LayoutProvider
from app.services.ocr.layout_detector import LayoutDetector
from app.services.ocr.models import LayoutRegion


class PaddlexDocLayoutProvider(LayoutProvider):
    name = "paddlex_doclayout"

    def __init__(self):
        self._detector = LayoutDetector()

    def detect(self, page_image_png: bytes, page_number: int) -> list[LayoutRegion]:
        return self._detector.detect(page_image_png, page_number)
