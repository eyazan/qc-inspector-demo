"""PaddleOCR-VL OCR provider — REMOTE OpenAI-compatible endpoint.

Per the deployment topology this is always an HTTP call (OCR_SERVICE_URL); the
model is never loaded locally on this machine. Delegates to the existing
OcrEngine so the request/response shape and config-driven auth are reused.
"""

from app.providers.ocr.base import OcrProvider
from app.services.ocr.ocr_engine import OcrEngine


class PaddleOcrVlProvider(OcrProvider):
    name = "paddleocr_vl"

    def __init__(self):
        self._engine = OcrEngine()

    def recognize(self, region_image_png: bytes) -> tuple[str, float | None]:
        return self._engine.recognize(region_image_png)

    def recognize_batch(self, images: list[bytes]) -> list[tuple[str, float | None]]:
        return self._engine.recognize_batch(images)
