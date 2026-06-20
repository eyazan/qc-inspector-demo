from app.services.dedup_service import DedupService
from app.services.ocr.models import LayoutRegion
from app.utils.bbox_utils import containment, iou


def test_iou_identical():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_iou_disjoint():
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def test_iou_half_overlap():
    assert round(iou([0, 0, 10, 10], [5, 0, 15, 10]), 3) == 0.333


def test_containment_small_in_big():
    assert containment([2, 2, 4, 4], [0, 0, 10, 10]) == 1.0
    assert containment([0, 0, 10, 10], [2, 2, 4, 4]) < 0.1


def test_dedup_removes_duplicate_and_contained():
    regions = [
        LayoutRegion("a", [0, 0, 100, 100], 1, "t", 0.9),
        LayoutRegion("b", [1, 1, 100, 100], 1, "t", 0.5),   # ~duplicate of a (low score)
        LayoutRegion("c", [10, 10, 20, 20], 1, "t", 0.8),   # contained in a
        LayoutRegion("d", [200, 200, 300, 300], 1, "t", 0.7),  # distinct
    ]
    kept, stats = DedupService(iou_threshold=0.5, containment_threshold=0.8).deduplicate(regions)
    kept_ids = [r.region_id for r in kept]
    assert kept_ids == ["a", "d"]
    assert stats == {"before": 4, "after": 2, "removed": 2}
