"""
Tablo isleyici — yapi korumali extraction.

Onemli: deger-bazli karsilastirma (Faz 3) tam buradan beslenir.
PaddleOCR-VL tablo cikti formatini (HTML veya markdown) parse edip
satir/sutun yapisini structured_data olarak saklar.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr.processors.base import ProcessorResult, RegionProcessor

logger = get_logger(__name__)


class TableProcessor(RegionProcessor):
    async def process(self, client, ocr_engine, region_image_png, region_type):
        text, confidence, failed = await ocr_engine.recognize(client, region_image_png, task="table")

        structured = None
        if text.strip():
            structured = self._parse_table(text)

        needs_review = failed or not text.strip() or structured is None
        if confidence is not None and confidence < settings.ocr_confidence_review_threshold:
            needs_review = True

        return ProcessorResult(
            text=text,
            confidence=confidence,
            structured_data=structured,
            needs_review=needs_review,
        )

    def _parse_table(self, text: str) -> dict | None:
        """
        OCR ciktisini satir/sutun yapisina cevirir.
        PaddleOCR-VL HTML tablo donerse onu, degilse markdown/pipe formatini dener.
        """
        stripped = text.strip()
        try:
            if "<table" in stripped.lower() or "<tr" in stripped.lower():
                return self._parse_html_table(stripped)
            if "|" in stripped:
                return self._parse_pipe_table(stripped)
        except Exception as error:  # noqa: BLE001
            logger.warning("Tablo parse hatasi: %s", error)
            return None
        return None

    def _parse_html_table(self, html: str) -> dict:
        import re

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL)
        parsed_rows = []
        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.IGNORECASE | re.DOTALL)
            cleaned = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if cleaned:
                parsed_rows.append(cleaned)
        if not parsed_rows:
            return None
        header = parsed_rows[0]
        body = parsed_rows[1:]
        return {
            "format": "table",
            "header": header,
            "rows": body,
            "row_count": len(body),
            "col_count": len(header),
        }

    def _parse_pipe_table(self, text: str) -> dict:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        rows = []
        for line in lines:
            if set(line.strip()) <= {"|", "-", " ", ":"}:  # ayirici satir
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if any(cells):
                rows.append(cells)
        if not rows:
            return None
        return {
            "format": "table",
            "header": rows[0],
            "rows": rows[1:],
            "row_count": max(len(rows) - 1, 0),
            "col_count": len(rows[0]),
        }
