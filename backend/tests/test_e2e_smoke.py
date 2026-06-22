"""End-to-end smoke test of the two-stage vendor pipeline.

Architecture-faithful: it runs the REAL PipelineService, OcrPipeline, dedup,
metadata extraction, segmentation, comparison, aggregation, report rendering and
storage. Only the external boundaries are replaced — and they are replaced by
test doubles that implement the SAME provider interfaces the app swaps via
config (LayoutProvider / OcrProvider / LlmProvider / SpecLookupStrategy). No app
logic is mocked; the remote OCR/LLM/SAP services and the heavy local DocLayout
model are stood in for so the test runs offline and fast.

Upload (Stage 1) -> awaiting_comparison -> Compare (Stage 2) -> completed, with
full artifacts + a structured final report.
"""

import re
import time

import fitz
import pytest

from app.providers.layout.base import LayoutProvider
from app.providers.llm.base import LlmProvider
from app.providers.ocr.base import OcrProvider
from app.providers.spec_lookup.base import SpecLookupResult, SpecLookupStrategy
from app.prompts import prompts
from app.prompts.metadata_extraction import METADATA_EXTRACTION_SYSTEM_PROMPT
from app.services.ocr.models import LayoutRegion


# ---------------------------------------------------------------- test doubles
class FakeLayout(LayoutProvider):
    name = "fake_layout"

    def detect(self, page_png: bytes, page_number: int):
        return [
            LayoutRegion(f"p{page_number}_r0", [0, 0, 300, 80], page_number, "text", 0.95),
            LayoutRegion(f"p{page_number}_r1", [0, 90, 300, 180], page_number, "table", 0.9),
        ]


class FakeOcr(OcrProvider):
    name = "fake_ocr"

    def recognize(self, region_png: bytes):
        return "AMS4911 PO 4500180435 Tensile 135 ksi", 0.99

    def recognize_batch(self, images):
        return [self.recognize(img) for img in images]


class FakeLlm(LlmProvider):
    """Returns canned-but-valid JSON keyed by which prompt is being run, so the
    REAL parsers (metadata/segmentation/comparison) exercise their happy paths."""

    name = "fake_llm"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if system_prompt == METADATA_EXTRACTION_SYSTEM_PROMPT:
            return (
                '{"po_number": "4500180435", "po_item": "00010", '
                '"material_number": "AMS4911", "spec_references": ["AMS4911"]}'
            )
        if system_prompt == prompts.segmentation_system:
            ids = re.findall(r'"region_id":\s*"([^"]+)"', user_prompt)
            if not ids:
                return '{"segments": []}'  # -> service falls back to one "other" segment
            id_list = ", ".join(f'"{i}"' for i in ids)
            return (
                '{"segments": [{"doc_type": "test_report", "page_range": [1, 2], '
                f'"region_ids": [{id_list}], "metadata": {{}}}}]}}'
            )
        if system_prompt == prompts.segment_comparison_system:
            return (
                '{"findings": ['
                '{"parameter": "Tensile Strength", "result": "COMPLIANT", '
                '"severity": "LOW", "spec_section": "3.5", "spec_evidence": "min 130 ksi", '
                '"vendor_page": 1, "vendor_region_ids": ["p1_r1"], "vendor_evidence": "135 ksi", '
                '"rationale": "meets requirement"},'
                '{"parameter": "Elongation", "result": "NON_COMPLIANT", '
                '"severity": "HIGH", "spec_section": "3.6", "spec_evidence": "min 10%", '
                '"vendor_page": 2, "vendor_region_ids": ["p2_r0"], "vendor_evidence": "7%", '
                '"rationale": "below minimum"}'
                ']}'
            )
        return "{}"


class FakeLookup(SpecLookupStrategy):
    name = "fake_lookup"

    def resolve(self, po_number=None, po_item=None, material=None, extra_specs=None):
        return SpecLookupResult(
            status="found",
            source="local_store_exact",
            spec_no="AMS4911",
            spec_text="3.5 Tensile Strength: min 130 ksi\n3.6 Elongation: min 10%",
            sections=[{"section_no": "3.5", "title": "Tensile", "page_number": 1, "text": "min 130 ksi"}],
            references=[],
            file_path=None,  # no spec PDF copy in the smoke test
        )


# ---------------------------------------------------------------- helpers
def _make_vendor_pdf(path, pages=2):
    doc = fitz.open()
    p1 = doc.new_page(width=320, height=240)
    p1.insert_text((20, 40), "Purchase Order 4500180435  Kalem 00010")
    p1.insert_text((20, 70), "Malzeme: AMS4911 (20THK) / 50")
    for i in range(1, pages):
        p = doc.new_page(width=320, height=240)
        p.insert_text((20, 40), f"page {i+1}: Tensile 135 ksi, Elongation 7%")
    doc.save(str(path))
    doc.close()


def _wait_idle(run_id, timeout=30.0):
    from app.services.pipeline_state import get_run_state

    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = get_run_state(run_id).snapshot()
        if not snap.get("is_processing"):
            return snap
        time.sleep(0.05)
    raise AssertionError(f"pipeline did not finish within {timeout}s")


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """Point data_root at a temp dir and swap the four external providers for the
    in-test doubles (at the module bindings the pipeline/services actually use).

    `settings` is a module-level singleton, so we patch its data_root directly
    (env + cache_clear would not affect the already-imported object)."""
    from app.core.config import settings as live_settings

    monkeypatch.setattr(live_settings, "data_root", tmp_path)
    monkeypatch.setattr(live_settings, "output_root", None)

    import app.services.pipeline_service as ps
    import app.services.metadata_extraction_service as mes
    import app.services.segmentation_service as seg
    import app.services.comparison_service as cmp

    monkeypatch.setattr(ps, "get_layout_provider", lambda *a, **k: FakeLayout())
    monkeypatch.setattr(ps, "get_ocr_provider", lambda *a, **k: FakeOcr())
    monkeypatch.setattr(ps, "get_spec_lookup_strategy", lambda *a, **k: FakeLookup())
    monkeypatch.setattr(mes, "get_llm_provider", lambda *a, **k: FakeLlm())
    monkeypatch.setattr(seg, "get_llm_provider", lambda *a, **k: FakeLlm())
    monkeypatch.setattr(cmp, "get_llm_provider", lambda *a, **k: FakeLlm())

    from app.services.storage_service import StorageService

    storage = StorageService()
    return ps, storage


def test_full_pipeline_e2e_smoke(wired):
    ps, storage = wired
    pipeline = ps.PipelineService(storage)

    # Stage a 2-page vendor PDF as if uploaded.
    pdf = storage._input_vendor / "vendor_e2e.pdf"
    _make_vendor_pdf(pdf, pages=2)

    # ---- Stage 1: upload -> awaiting_comparison ----
    started, _msg, run_id = pipeline.start_upload(seed={})
    assert started and run_id
    snap = _wait_idle(run_id)
    assert snap["status"] == "awaiting_comparison", snap

    preview = storage.read_preview(run_id)
    assert preview["po_number"] == "4500180435"
    assert preview["material"]  # extracted (regex captured "/ 50" suffix too)
    assert "AMS4911" in (preview.get("sap_spec_name") or "")
    assert "Tensile" in (preview.get("sap_spec_text") or "")

    # ---- Stage 2: compare -> completed ----
    ok, _ = pipeline.start_comparison(run_id)
    assert ok
    snap2 = _wait_idle(run_id)
    assert snap2["status"] == "completed", snap2

    # Structured final report.
    report = storage.read_final_report_json(run_id)
    assert report and report["run_id"] == run_id
    assert report["total_findings"] >= 2
    results = {f["result"] for f in report["findings"]}
    assert "COMPLIANT" in results and "NON_COMPLIANT" in results
    assert sum(report["summary"].values()) == report["total_findings"]

    # Job-root artifacts + ALL pages OCR'd into per-page artifact dirs.
    run_dir = storage.run_path(run_id)
    assert (run_dir / "comparison_result.json").exists()
    assert (run_dir / "job_metadata.json").exists()
    for n in (1, 2):
        page_dir = run_dir / "vendor" / "pages" / f"page_{n:03d}"
        for fn in ("page_image.png", "doclayout.json", "regions.json", "ocr.json", "normalized_segments.json"):
            assert (page_dir / fn).exists(), f"missing {page_dir/fn}"

    # Frontend-shaped report (InspectorReport contract).
    fe = storage.build_inspector_report(run_id)
    assert fe["po_number"] == "4500180435"
    assert len(fe["findings"]) == report["total_findings"]
    assert set(fe["summary"]) <= {"COMPLIANT", "NON_COMPLIANT", "PARTIAL", "MISSING", "NOT_COVERED"}
