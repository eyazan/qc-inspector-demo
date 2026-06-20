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

    def recognize_batch(
        self, images: list[bytes]
    ) -> list[tuple[str, float | None]]:
        """Recognize many region crops. Default: sequential per-image. Providers
        backed by a remote service override this for concurrency/batching."""
        return [self.recognize(img) for img in images]
