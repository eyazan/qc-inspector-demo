"""IoU-based region deduplication (Section 2A step 7).

Layout detectors at low score thresholds emit overlapping/duplicate boxes. We
drop redundant regions before OCR:
  - IoU(a, b) > iou_threshold  -> keep the higher-score (else larger) region.
  - a small region almost fully contained in a larger one (containment >
    containment_threshold) -> drop the small one.

Operates per page; returns the kept regions plus before/after stats so the
report can record what was removed.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr.models import LayoutRegion
from app.utils.bbox_utils import area, containment, iou

logger = get_logger(__name__)


def _score(region: LayoutRegion) -> float:
    return region.score if region.score is not None else 0.0


class DedupService:
    def __init__(self, iou_threshold: float | None = None, containment_threshold: float | None = None):
        self._iou = iou_threshold if iou_threshold is not None else settings.dedup_iou_threshold
        self._contain = (
            containment_threshold
            if containment_threshold is not None
            else settings.dedup_containment_threshold
        )

    def deduplicate(self, regions: list[LayoutRegion]) -> tuple[list[LayoutRegion], dict]:
        """Return (kept_regions, stats) for a single page's regions."""
        kept: list[LayoutRegion] = []
        removed = 0
        for region in sorted(regions, key=lambda r: (_score(r), area(r.bbox)), reverse=True):
            drop = False
            for keep in kept:
                if iou(region.bbox, keep.bbox) > self._iou:
                    drop = True
                    break
                if containment(region.bbox, keep.bbox) > self._contain:
                    drop = True
                    break
            if drop:
                removed += 1
            else:
                kept.append(region)

        # Preserve original ordering of the survivors for stable region ids.
        kept_ids = {id(r) for r in kept}
        ordered = [r for r in regions if id(r) in kept_ids]
        stats = {"before": len(regions), "after": len(ordered), "removed": removed}
        if removed:
            logger.info("Dedup: %s -> %s (%s kaldirildi)", stats["before"], stats["after"], removed)
        return ordered, stats
