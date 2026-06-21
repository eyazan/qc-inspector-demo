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
