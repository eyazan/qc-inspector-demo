"""Ozel region isleyicileri icin ortak arayuz."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProcessorResult:
    text: str
    confidence: Optional[float]
    structured_data: Optional[dict]
    needs_review: bool


class RegionProcessor:
    """
    Tum isleyicilerin tabani.
    Her isleyici, OCR ham ciktisini alip tipine ozel zenginlestirir.
    """

    async def process(
        self,
        client,
        ocr_engine,
        region_image_png: bytes,
        region_type: str,
    ) -> ProcessorResult:
        raise NotImplementedError
