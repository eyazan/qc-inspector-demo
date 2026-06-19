"""Spec file discovery — scan the configured spec source root for spec PDFs.

SPEC_NETWORK_ROOT points at a local mock folder now and a real UNC path later
with no code change. Returns provenance (path, mtime, size) used for change
detection by the indexing pipeline.
"""

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SpecFile:
    file_name: str
    file_path: str
    modified_time: float
    size: int


class SpecFileDiscoveryService:
    def __init__(self, root: str | None = None):
        self._root = root if root is not None else settings.spec_network_root

    def _root_dir(self) -> Path | None:
        if not self._root:
            return None
        root = Path(self._root)
        if root.is_file():
            root = root.parent
        if not root.exists():
            logger.error("Spec source root erisilemiyor: %s", self._root)
            return None
        return root

    def discover(self, name_filter: str | None = None) -> list[SpecFile]:
        root = self._root_dir()
        if root is None:
            return []
        files: list[SpecFile] = []
        for pdf in sorted(root.glob("*.pdf")):
            if name_filter and name_filter.lower() not in pdf.stem.lower():
                continue
            stat = pdf.stat()
            files.append(
                SpecFile(
                    file_name=pdf.name,
                    file_path=str(pdf),
                    modified_time=stat.st_mtime,
                    size=stat.st_size,
                )
            )
        logger.info("Spec discovery: %s dosya bulundu (%s)", len(files), root)
        return files
