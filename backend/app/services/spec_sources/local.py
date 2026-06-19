"""Local spec kaynagi — data/specs altindaki <key>.md dosyalarindan okur.
Orijinal SpecService mantiginin esdegeri; gelistirme/test icin."""
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.services.spec_sources.base import SpecResult, SpecSource

logger = get_logger(__name__)


class LocalSpecSource(SpecSource):
    def __init__(self):
        self._dir = settings.spec_source_dir

    def fetch(self, po_number=None, po_item=None, material=None) -> SpecResult:
        candidates = []
        if po_number and po_item:
            candidates.append(self._dir / f"{po_number}_{po_item}.md")
        if po_number:
            candidates.append(self._dir / f"{po_number}.md")
        if material:
            candidates.append(self._dir / f"{material}.md")
        for cand in candidates:
            if cand.exists():
                text = cand.read_text(encoding="utf-8")
                lines = [l for l in text.splitlines() if l.strip()]
                return SpecResult(
                    status="success",
                    spec_name=cand.stem,
                    spec_text=text,
                    lines=lines,
                )
        return SpecResult(status="not_found")
