"""Layout provider interface.

Identical contract regardless of backend (local paddlex today, something else
later). Selected via ACTIVE_LAYOUT_PROVIDER.
"""

from abc import ABC, abstractmethod

from app.services.ocr.models import LayoutRegion


class LayoutProvider(ABC):
    name: str = "base"

    @abstractmethod
    def detect(self, page_image_png: bytes, page_number: int) -> list[LayoutRegion]:
        """Detect layout regions on a single rendered page image.

        bbox is returned in PIXEL coordinates of the rendered page image.
        """
        raise NotImplementedError
