"""Spec identity (label-based spec-no naming) + force-OCR policy (Item 1)."""

import fitz

from app.services import spec_structure_parser as sp
from app.services.spec_ocr_pipeline_service import SpecOcrPipelineService


# ---- label-based spec number ----

def test_label_spec_no_basic():
    assert sp.extract_spec_no_from_label("Specification No: XYZ-123 Rev A") == "XYZ-123"
    assert sp.extract_spec_no_from_label("SPEC NO. AMS4911") == "AMS4911"
    assert sp.extract_spec_no_from_label("Specification Number AB12/34") == "AB12/34"


def test_label_requires_digit_and_absent_label():
    assert sp.extract_spec_no_from_label("Specification No: TITLE") is None  # no digit
    assert sp.extract_spec_no_from_label("just some text") is None


def test_extract_identity_prefers_label_over_family():
    # Label code wins even when a known family code (AMS4911) also appears.
    text = "Specification No: ZZ100\nConforms to AMS4911 Rev T"
    spec_no, _rev = sp.extract_identity(text, file_name="whatever.pdf")
    assert spec_no == "ZZ100"


def test_extract_identity_falls_back_to_family_then_filename():
    spec_no, _ = sp.extract_identity("Material per AMS4911 Rev T")
    assert spec_no == "AMS4911"
    spec_no2, _ = sp.extract_identity("no code here", file_name="ABS5125A.pdf")
    assert spec_no2 and spec_no2.startswith("ABS5125")


# ---- force-OCR policy ----

class _FakeRegion:
    def __init__(self, text, y):
        self.text = text
        self.page_number = 1
        self.bbox = [0, y, 100, y + 10]


class _FakeOcrPipeline:
    def run(self, pdf_path, max_pages=None):
        return [_FakeRegion("OCR LINE", 0)]


def _text_pdf(path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((20, 40), "NATIVE TEXT LAYER " * 5)
    doc.save(str(path))
    doc.close()


def test_force_ocr_uses_ocr_even_for_digital_pdf(tmp_path, monkeypatch):
    from app.core.config import settings

    pdf = tmp_path / "s.pdf"
    _text_pdf(pdf)
    svc = SpecOcrPipelineService(_FakeOcrPipeline())

    monkeypatch.setattr(settings, "spec_force_ocr", True, raising=False)
    pages, source = svc.extract_pages(pdf)
    assert source == "ocr" and "OCR LINE" in "\n".join(pages)

    monkeypatch.setattr(settings, "spec_force_ocr", False, raising=False)
    pages2, source2 = svc.extract_pages(pdf)
    assert source2 == "native" and "NATIVE" in "\n".join(pages2)
