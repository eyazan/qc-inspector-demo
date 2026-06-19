"""Bounding-box geometry helpers. bbox = [x1, y1, x2, y2] (any consistent units)."""


def area(bbox: list[float]) -> float:
    w = max(0.0, bbox[2] - bbox[0])
    h = max(0.0, bbox[3] - bbox[1])
    return w * h


def intersection_area(a: list[float], b: list[float]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def iou(a: list[float], b: list[float]) -> float:
    inter = intersection_area(a, b)
    if inter <= 0.0:
        return 0.0
    union = area(a) + area(b) - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def containment(inner: list[float], outer: list[float]) -> float:
    """Fraction of `inner` that lies inside `outer` (0..1)."""
    inner_area = area(inner)
    if inner_area <= 0.0:
        return 0.0
    return intersection_area(inner, outer) / inner_area
