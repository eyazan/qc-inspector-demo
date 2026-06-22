"""Per-page artifact structure + timings (prompt Section 3). Uses in-test
provider doubles (not app mocks) to drive the real OcrPipeline."""

import json

import fitz

from app.services.ocr.models import LayoutRegion
from app.services.ocr.ocr_pipeline import OcrPipeline


class _FakeLayout:
    name = "fake"

    def detect(self, page_png, page_number):
        return [
            LayoutRegion(f"page{page_number}_region0", [0, 0, 200, 100], page_number, "text", 0.9),
            LayoutRegion(f"page{page_number}_region1", [0, 110, 200, 200], page_number, "table", 0.8),
        ]


class _FakeOcr:
    name = "fake"

    def recognize(self, b):
        return "ABC 123", 0.95

    def recognize_batch(self, images):
        return [("ABC 123", 0.95) for _ in images]


def _make_pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(width=300, height=300)
        p.insert_text((20, 40), f"page {i+1} content")
    doc.save(str(path))
    doc.close()


def test_run_processes_all_pages_parallel(tmp_path, monkeypatch):
    """Spec OCR uses OcrPipeline.run(); it must process ALL pages (page-parallel)
    and return regions for every page, order-stable."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "page_parallelism", True, raising=False)
    pdf = tmp_path / "spec.pdf"
    _make_pdf(pdf, pages=3)
    pipe = OcrPipeline(_FakeLayout(), _FakeOcr())
    regions = pipe.run(pdf)

    assert {r.page_number for r in regions} == {1, 2, 3}
    assert len(regions) == 6  # 3 pages x 2 regions
    assert pipe.dedup_stats["before"] == 6


def test_skip_region_types_keeps_region_but_skips_ocr(tmp_path, monkeypatch):
    """OCR_SKIP_REGION_TYPES skips the OCR call for those types but KEEPS the
    region in the output (empty text) — nothing is dropped, parallelism intact."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ocr_skip_region_types", "table", raising=False)

    pdf = tmp_path / "v.pdf"
    _make_pdf(pdf, pages=1)
    pipe = OcrPipeline(_FakeLayout(), _FakeOcr())
    regions, _ = pipe.run_with_artifacts(pdf, tmp_path / "pages")

    by_type = {r.region_type: r for r in regions}
    assert set(by_type) == {"text", "table"}          # both regions present
    assert by_type["text"].text == "ABC 123"          # text region OCR'd
    assert by_type["table"].text == ""                # table region skipped (no OCR)


def test_default_no_skip_ocrs_everything(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ocr_skip_region_types", "", raising=False)
    pdf = tmp_path / "v.pdf"
    _make_pdf(pdf, pages=1)
    pipe = OcrPipeline(_FakeLayout(), _FakeOcr())
    regions, _ = pipe.run_with_artifacts(pdf, tmp_path / "pages")
    assert all(r.text == "ABC 123" for r in regions)   # default: nothing skipped


def test_run_with_artifacts(tmp_path):
    pdf = tmp_path / "v.pdf"
    _make_pdf(pdf, pages=2)
    pages_dir = tmp_path / "pages"

    pipe = OcrPipeline(_FakeLayout(), _FakeOcr())
    regions, timings = pipe.run_with_artifacts(pdf, pages_dir)

    # both pages processed (not just the first)
    assert {r.page_number for r in regions} == {1, 2}
    assert len(timings["pages"]) == 2
    assert "ocr_s" in timings and "doclayout_s" in timings

    for n in (1, 2):
        d = pages_dir / f"page_{n:03d}"
        for f in ("page_image.png", "doclayout.json", "regions.json", "ocr.json", "normalized_segments.json"):
            assert (d / f).exists(), f"{d/f} missing"
        ocr = json.loads((d / "ocr.json").read_text())
        assert ocr["page_number"] == n
        assert ocr["regions"][0]["text"] == "ABC 123"
        norm = json.loads((d / "normalized_segments.json").read_text())
        assert norm["segments"][0]["text"] == "ABC 123"
