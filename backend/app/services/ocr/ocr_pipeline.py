from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import fitz

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr.models import OcrRegion

if TYPE_CHECKING:
    from app.providers.layout.base import LayoutProvider
    from app.providers.ocr.base import OcrProvider
    from app.services.dedup_service import DedupService

logger = get_logger(__name__)


class OcrPipeline:
    def __init__(
        self,
        layout_detector: "LayoutProvider",
        ocr_engine: "OcrProvider",
        dedup: "DedupService | None" = None,
    ):
        # Lazy import: dedup_service imports ocr.models, which loads this package.
        from app.services.dedup_service import DedupService

        self._layout_detector = layout_detector
        self._ocr_engine = ocr_engine
        self._dedup = dedup or DedupService()
        self._dpi = settings.pdf_render_dpi
        self._zoom = self._dpi / 72.0
        self._max_workers = settings.ocr_max_concurrency
        # Region types to skip OCR for (perf). Empty by default -> OCR everything.
        self._skip_types = {
            t.strip().lower()
            for t in (settings.ocr_skip_region_types or "").split(",")
            if t.strip()
        }
        # Per-run dedup counts (before/after per page), surfaced to the report.
        self.dedup_stats: dict = {"before": 0, "after": 0, "removed": 0, "pages": []}

    def _ocr_kept_regions(self, page, page_png: bytes, kept: list) -> list[OcrRegion]:
        """OCR a page's kept regions, cropping from the already-rendered page PNG
        (no re-rasterization). Regions whose type is in the skip set keep their
        place in the output with empty text but are NOT sent to OCR — so nothing
        is dropped from the structure and no work is wasted on non-text regions.
        Returns OcrRegion list aligned to `kept` order. Parallelism unchanged:
        recognize_batch still runs the page's region crops concurrently."""
        targets = [r for r in kept if r.region_type.lower() not in self._skip_types]
        crops = [self._crop_png(page_png, r.bbox, page) for r in targets]
        results = self._ocr_engine.recognize_batch(crops)
        by_id = {t.region_id: res for t, res in zip(targets, results)}
        out: list[OcrRegion] = []
        for r in kept:
            text, conf = by_id.get(r.region_id, ("", None))
            out.append(
                OcrRegion(r.region_id, text, r.bbox, r.page_number, r.region_type, conf)
            )
        return out

    def run(self, pdf_path: Path, max_pages: int | None = None) -> list[OcrRegion]:
        document = fitz.open(str(pdf_path))
        all_regions: list[OcrRegion] = []
        self.dedup_stats = {"before": 0, "after": 0, "removed": 0, "pages": []}

        page_count = document.page_count
        if max_pages:
            page_count = min(max_pages, page_count)

        for page_index in range(page_count):
            page = document[page_index]
            page_number = page_index + 1
            page_png = self._render_page(page)
            layout_regions = self._layout_detector.detect(page_png, page_number)
            kept, stats = self._dedup.deduplicate(layout_regions)
            self._accumulate_stats(page_number, stats)
            page_results = self._ocr_kept_regions(page, page_png, kept)
            all_regions.extend(page_results)

        document.close()
        return all_regions

    def run_with_artifacts(
        self, pdf_path: Path, pages_dir: Path, max_pages: int | None = None
    ) -> tuple[list[OcrRegion], dict]:
        """Process ALL pages, write per-page JSON artifacts under
        pages_dir/page_NNN/ (page_image.png, doclayout.json, regions.json,
        ocr.json, normalized_segments.json), and return (regions, timings).

        Pages are processed concurrently when PAGE_PARALLELISM is on; DocLayout
        (paddlex, thread-affine) serializes itself, OCR batches overlap. Each
        worker opens its own fitz document (fitz is not thread-safe)."""
        pages_dir = Path(pages_dir)
        pages_dir.mkdir(parents=True, exist_ok=True)
        with fitz.open(str(pdf_path)) as doc:
            page_count = doc.page_count
        if max_pages:
            page_count = min(max_pages, page_count)

        self.dedup_stats = {"before": 0, "after": 0, "removed": 0, "pages": []}
        timings = {"render_s": 0.0, "doclayout_s": 0.0, "ocr_s": 0.0, "pages": []}

        def _do(page_index: int):
            return self._process_page(pdf_path, page_index, pages_dir)

        indices = list(range(page_count))
        if settings.page_parallelism and page_count > 1:
            workers = max(1, min(settings.page_render_max_workers, page_count))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="page") as ex:
                results = list(ex.map(_do, indices))
        else:
            results = [_do(i) for i in indices]

        all_regions: list[OcrRegion] = []
        for regions, stats, t in sorted(results, key=lambda r: r[2]["page"]):
            all_regions.extend(regions)
            self._accumulate_stats(t["page"], stats)
            timings["render_s"] += t["render_s"]
            timings["doclayout_s"] += t["doclayout_s"]
            timings["ocr_s"] += t["ocr_s"]
            timings["pages"].append(t)
        logger.info(
            "OCR pipeline: %s sayfa | render=%.1fs doclayout=%.1fs ocr=%.1fs",
            page_count, timings["render_s"], timings["doclayout_s"], timings["ocr_s"],
        )
        return all_regions, timings

    def _process_page(self, pdf_path: Path, page_index: int, pages_dir: Path):
        page_number = page_index + 1
        with fitz.open(str(pdf_path)) as doc:  # per-thread doc (fitz not thread-safe)
            page = doc[page_index]
            t0 = time.monotonic()
            page_png = self._render_page(page)
            t1 = time.monotonic()
            layout_regions = self._layout_detector.detect(page_png, page_number)
            t2 = time.monotonic()
            kept, stats = self._dedup.deduplicate(layout_regions)
            # Crop from the rendered PNG (no re-rasterization); skip-typed regions
            # are excluded from OCR but kept in the output (handled in helper).
            targets = [r for r in kept if r.region_type.lower() not in self._skip_types]
            crops = [self._crop_png(page_png, r.bbox, page) for r in targets]
        t3 = time.monotonic()
        ocr_results = self._ocr_engine.recognize_batch(crops)
        t4 = time.monotonic()

        by_id = {t.region_id: res for t, res in zip(targets, ocr_results)}
        regions: list[OcrRegion] = []
        for r in kept:
            text, conf = by_id.get(r.region_id, ("", None))
            regions.append(OcrRegion(r.region_id, text, r.bbox, r.page_number, r.region_type, conf))

        self._write_page_artifacts(pages_dir, page_number, page_png, layout_regions, kept, regions)
        timing = {
            "page": page_number,
            "render_s": round(t1 - t0, 3),
            "doclayout_s": round(t2 - t1, 3),
            "ocr_s": round(t4 - t3, 3),
            "regions": len(regions),
        }
        return regions, stats, timing

    def _write_page_artifacts(self, pages_dir, page_number, page_png, layout, kept, ocr_regions):
        d = Path(pages_dir) / f"page_{page_number:03d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "page_image.png").write_bytes(page_png)

        def _w(name, obj):
            (d / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

        _w("doclayout.json", {"page_number": page_number, "regions": [
            {"region_id": r.region_id, "type": r.region_type, "bbox": r.bbox, "score": r.score}
            for r in layout]})
        _w("regions.json", {"page_number": page_number, "kept_after_dedup": [
            {"region_id": r.region_id, "type": r.region_type, "bbox": r.bbox} for r in kept]})
        _w("ocr.json", {"page_number": page_number, "regions": [r.to_dict() for r in ocr_regions]})
        _w("normalized_segments.json", {"page_number": page_number, "segments": [
            {"region_id": r.region_id, "type": r.region_type,
             "text": re.sub(r"\s+", " ", (r.text or "")).strip()}
            for r in ocr_regions if (r.text or "").strip()]})

    def _accumulate_stats(self, page_number: int, stats: dict) -> None:
        self.dedup_stats["before"] += stats["before"]
        self.dedup_stats["after"] += stats["after"]
        self.dedup_stats["removed"] += stats["removed"]
        self.dedup_stats["pages"].append({"page": page_number, **stats})

    def _render_page(self, page) -> bytes:
        matrix = fitz.Matrix(self._zoom, self._zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        return pixmap.tobytes("png")

    def _crop_region(self, page, bbox: list[float]) -> bytes:
        # Layout bbox is in PIXEL coords of the page rendered at self._zoom.
        # fitz clip rects are in PDF points, so divide by zoom before clipping,
        # then re-render the clipped region at full dpi.
        rect = fitz.Rect(*[c / self._zoom for c in bbox])
        matrix = fitz.Matrix(self._zoom, self._zoom)
        pixmap = page.get_pixmap(matrix=matrix, clip=rect)

        try:
            return pixmap.tobytes("png")
        except Exception:
            try:
                return pixmap.tobytes("jpeg")
            except Exception:
                logger.warning(
                    "PNG/JPEG donusumu basarisiz (sayfa %s); bos bytes donduruluyor",
                    getattr(page, "number", "?"),
                )
                return b""

    def _crop_png(self, page_png: bytes, bbox: list[float], page=None) -> bytes:
        """Crop a region from the already-rendered page PNG (same DPI -> pixel
        identical to a re-render, but no extra rasterization). Falls back to the
        proven fitz re-render on any degenerate bbox / decode issue so a region
        is never silently lost."""
        import io

        from PIL import Image

        try:
            img = Image.open(io.BytesIO(page_png))
            w, h = img.size
            x0, y0, x1, y1 = (int(round(c)) for c in bbox)
            x0, x1 = max(0, min(x0, w)), max(0, min(x1, w))
            y0, y1 = max(0, min(y0, h)), max(0, min(y1, h))
            if x1 - x0 < 2 or y1 - y0 < 2:
                raise ValueError("degenerate crop")
            buf = io.BytesIO()
            img.crop((x0, y0, x1, y1)).save(buf, format="PNG")
            return buf.getvalue()
        except Exception:  # noqa: BLE001 - safe fallback to original behavior
            if page is not None:
                return self._crop_region(page, bbox)
            return b""
