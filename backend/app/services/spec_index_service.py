"""
Spec indeksleme — DOSYA-TABANLI (DB yok).

Bir spec PDF'i bir kez OCR'lanir ve data/specs_index/<spec_no>.json + .md
olarak kaydedilir. Ayni spec tekrar gelince diskten okunur (yeniden OCR yok).

JSON: {"spec_no","file_name","file_path","md_path","text"}
MD  : spec metni (insan-okur).
"""
import json
import re
from pathlib import Path

import fitz

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _safe_key(spec_no: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", spec_no or "spec")


class SpecIndexService:
    def __init__(self, ocr_pipeline=None):
        self._ocr_pipeline = ocr_pipeline
        self._dir = settings.spec_index_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def get_cached(self, spec_no: str) -> dict | None:
        key = _safe_key(spec_no)
        meta = self._dir / f"{key}.json"
        if meta.exists():
            try:
                return json.loads(meta.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return None
        return None

    def get_or_process(self, spec_no: str, found) -> dict | None:
        """Cache varsa dondur; yoksa OCR'la + indeksle. found: FoundSpec."""
        cached = self.get_cached(spec_no)
        if cached:
            logger.info("Spec zaten indekslenmis (cache): %s", spec_no)
            return cached

        if found is None:
            return None

        logger.info("Spec isleniyor: %s", found.file_name)
        text = self._extract_text(Path(found.file_path))
        if not text or not text.strip():
            logger.error("Spec metni bos/cikarilamadi: %s", found.file_name)
            return None

        key = _safe_key(spec_no)
        md_path = self._dir / f"{key}.md"
        md_path.write_text(text, encoding="utf-8")
        meta = {
            "spec_no": spec_no,
            "file_name": found.file_name,
            "file_path": found.file_path,
            "md_path": str(md_path),
            "text": text,
        }
        (self._dir / f"{key}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Spec indekslendi: %s -> %s", found.file_name, md_path.name)
        return meta

    def _extract_text(self, pdf_path: Path) -> str:
        # Once PyMuPDF ile dogrudan metin (dijital PDF). Bossa OCR (taranmis).
        try:
            doc = fitz.open(str(pdf_path))
            parts = []
            max_pages = settings.spec_ocr_max_pages or doc.page_count
            for i in range(min(max_pages, doc.page_count)):
                parts.append(doc[i].get_text())
            doc.close()
            direct = "\n".join(p for p in parts if p and p.strip())
            if direct.strip():
                return direct
        except Exception as err:  # noqa: BLE001
            logger.warning("PyMuPDF metin cikarma hatasi (%s): %s", pdf_path.name, err)

        # Taranmis -> OCR pipeline (vendor ile AYNI pipeline)
        if self._ocr_pipeline is None:
            logger.error("Taranmis spec icin ocr_pipeline gerekli ama verilmedi")
            return ""
        regions = self._ocr_pipeline.run(pdf_path)
        lines = [r.text.strip() for r in regions if r.text and r.text.strip()]
        return "\n".join(lines)
