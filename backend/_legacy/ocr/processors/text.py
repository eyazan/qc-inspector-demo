"""Standart metin/baslik/paragraf isleyici — hizli yol."""

from app.core.config import settings
from app.services.ocr.processors.base import ProcessorResult, RegionProcessor


class TextProcessor(RegionProcessor):
    async def process(self, client, ocr_engine, region_image_png, region_type):
        text, confidence, failed = await ocr_engine.recognize(client, region_image_png, task="ocr")

        needs_review = failed or not text.strip()
        if confidence is not None and confidence < settings.ocr_confidence_review_threshold:
            needs_review = True

        return ProcessorResult(
            text=text,
            confidence=confidence,
            structured_data=None,
            needs_review=needs_review,
        )
