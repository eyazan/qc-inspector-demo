"""OCR provider interface.

Same contract whether the backend is remote PaddleOCR-VL today or something
else later. Selected via ACTIVE_OCR_PROVIDER.
"""

from abc import ABC, abstractmethod


class OcrProvider(ABC):
    name: str = "base"

    @abstractmethod
    def recognize(self, region_image_png: bytes) -> tuple[str, float | None]:
        """Recognize text in a cropped region image -> (text, confidence|None)."""
        raise NotImplementedError
