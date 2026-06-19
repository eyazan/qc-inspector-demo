"""
Figure/drawing isleyici — muhendislik cizimleri.

Iki katman:
1. OCR ile gomulu metin/annotation (olcuye dair sayilar)
2. (opsiyonel) VLM ile gorsel aciklama + olcu/tolerans cikarimi

VLM pahali oldugu icin sadece figure tipinde ve config aciksa calisir.
"""

import re

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr.processors.base import ProcessorResult, RegionProcessor

logger = get_logger(__name__)

# Olcu/tolerans yakalama: "45.5 ± 0.2", "R3.5", "Ø12", "M10x1.5", "12H7"
_MEASUREMENT_PATTERNS = [
    r"[ØΦ⌀]\s*\d+(?:[.,]\d+)?",            # cap
    r"R\s*\d+(?:[.,]\d+)?",                # yaricap
    r"M\d+(?:[.,]\d+)?(?:x\d+(?:[.,]\d+)?)?",  # vida
    r"\d+(?:[.,]\d+)?\s*[±+]\s*\d+(?:[.,]\d+)?",  # tolerans
    r"\d+(?:[.,]\d+)?\s*(?:mm|cm|inch|in|°)",     # birimli olcu
    r"\d+[A-Za-z]\d+",                    # ISO tolerans (12H7)
]


class FigureProcessor(RegionProcessor):
    def __init__(self, vlm_describe=None):
        # vlm_describe: async callable(image_png) -> str  (Faz 3'te baglanir)
        self._vlm_describe = vlm_describe

    async def process(self, client, ocr_engine, region_image_png, region_type):
        text, confidence, failed = await ocr_engine.recognize(client, region_image_png, task="ocr")

        measurements = self._extract_measurements(text)
        structured = {
            "format": "figure",
            "measurements": measurements,
            "annotations": text,
        }

        # VLM aciklamasi (opsiyonel, pahali)
        if settings.figure_vlm_enabled and self._vlm_describe is not None:
            try:
                description = await self._vlm_describe(region_image_png)
                structured["vlm_description"] = description
            except Exception as error:  # noqa: BLE001
                logger.warning("Figure VLM aciklamasi basarisiz: %s", error)

        # Cizimlerde OCR bos olabilir ama gorsel onemli -> her zaman review onerilir
        needs_review = failed
        if not measurements and not text.strip():
            needs_review = True

        return ProcessorResult(
            text=text,
            confidence=confidence,
            structured_data=structured,
            needs_review=needs_review,
        )

    def _extract_measurements(self, text: str) -> list[str]:
        if not text:
            return []
        found = []
        for pattern in _MEASUREMENT_PATTERNS:
            found.extend(re.findall(pattern, text))
        # tekrarsiz, sirali
        seen = set()
        result = []
        for m in found:
            key = m.strip()
            if key and key not in seen:
                seen.add(key)
                result.append(key)
        return result
