"""
Spec PDF bulucu — network/yerel klasorde spec_no ile eslesen PDF'i bulur.

settings.spec_docs_unc_path bir KLASOR olmali (icinde spec PDF'leri).
Yanlislikla dosya verilirse otomatik klasorune duser.
spec_no normalize (S-400 <-> S400) ile eslestirme; coklu eslesmede en yeni dosya.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FoundSpec:
    file_name: str
    file_path: str


def _normalize(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


class SpecFinder:
    def __init__(self):
        self._root = settings.spec_docs_unc_path

    def find(self, spec_no: str) -> FoundSpec | None:
        if not self._root or not spec_no:
            return None
        root = Path(self._root)
        if root.is_file():
            logger.warning(
                "SpecFinder: spec_docs_unc_path bir dosya (%s); klasoru kullanilacak: %s",
                root.name, root.parent,
            )
            root = root.parent
        if not root.exists():
            logger.error("SpecFinder: path erisilemiyor: %s", self._root)
            return None

        target = _normalize(spec_no)
        matches = []
        for pdf in root.glob("*.pdf"):
            if target in _normalize(pdf.stem):
                matches.append(pdf)
        if not matches:
            logger.info("SpecFinder: '%s' icin eslesen PDF yok (%s)", spec_no, root)
            return None
        # En yeni dosya
        newest = max(matches, key=lambda p: p.stat().st_mtime)
        logger.info(
            "SpecFinder: '%s' icin %s eslesme, en yeni secildi: %s",
            spec_no, len(matches), newest.name,
        )
        return FoundSpec(file_name=newest.name, file_path=str(newest))
