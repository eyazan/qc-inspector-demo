"""
Formul isleyici — matematiksel ifadeleri LaTeX olarak yakalar.

PaddleOCR-VL formul moduna sahip; ciktisini LaTeX olarak structured_data'ya
koyar. Muhendislik hesaplari (gerilme, tolerans formulleri) bu sayede kayipsiz.
"""

from app.core.config import settings
from app.services.ocr.processors.base import ProcessorResult, RegionProcessor


class FormulaProcessor(RegionProcessor):
    async def process(self, client, ocr_engine, region_image_png, region_type):
        text, confidence, failed = await ocr_engine.recognize(client, region_image_png, task="formula")

        structured = None
        if text.strip():
            structured = {
                "format": "formula",
                "latex": self._clean_latex(text),
                "raw": text,
            }

        needs_review = failed or not text.strip()
        if confidence is not None and confidence < settings.ocr_confidence_review_threshold:
            needs_review = True

        return ProcessorResult(
            text=text,
            confidence=confidence,
            structured_data=structured,
            needs_review=needs_review,
        )

    def _clean_latex(self, text: str) -> str:
        cleaned = text.strip()
        # OCR bazen $$...$$ veya \[...\] sarmalar; koru ama normalize et
        for wrapper in ("$$", "$", "\\[", "\\]"):
            cleaned = cleaned.replace(wrapper, "")
        return cleaned.strip()
