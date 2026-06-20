import json

from app.providers.llm.mock_provider import MockLlmProvider
from app.providers.ocr.mock_provider import MockOcrProvider
from app.prompts import prompts


def test_mock_ocr_returns_text_and_confidence():
    text, conf = MockOcrProvider().recognize(b"")
    assert "4500180435" in text
    assert conf == 0.99


def test_mock_llm_segmentation_returns_valid_json():
    llm = MockLlmProvider()
    user = '"region_id": "page1_region0"\n"page_number": 1'
    out = llm.complete(prompts.segmentation_system, user)
    data = json.loads(out)
    assert data["segments"]
    assert data["segments"][0]["region_ids"] == ["page1_region0"]


def test_mock_llm_comparison_returns_findings_json():
    llm = MockLlmProvider()
    out = llm.complete(prompts.segment_comparison_system, "vendor + spec")
    data = json.loads(out)
    assert "findings" in data and len(data["findings"]) >= 1
    assert data["findings"][0]["result"] in {
        "COMPLIANT", "NON_COMPLIANT", "NOT_COVERED_IN_THIS_DOCUMENT", "MISSING", "UNCLEAR"
    }


def test_mock_llm_metadata_json():
    llm = MockLlmProvider()
    out = llm.complete("Extract METADATA as JSON", "doc text")
    data = json.loads(out)
    assert data["po_number"] == "4500180435"
    assert isinstance(data["spec_references"], list)
