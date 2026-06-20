"""Real end-to-end on a clean 'scanned-style' vendor PDF (the real scenario):
PDF -> DocLayout regions -> PaddleOCR-VL per region (real text) -> dedup ->
LLM metadata -> spec lookup (indexed AMS4911) -> segmentation -> comparison ->
aggregation -> structured findings + Turkish narrative.

Uses the providers from .env (DocLayout local + PaddleOCR-VL local + Ollama LLM).
Slow on CPU; intended as a one-off validation of the full real chain.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402

from app.providers.factory import get_layout_provider, get_ocr_provider, get_llm_provider  # noqa: E402
from app.services.pipeline_service import PipelineService  # noqa: E402
from app.services.storage_service import StorageService  # noqa: E402


def _make_vendor_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 pt
    y = 60
    lines = [
        ("MAL GIRIS FISI / RECEIVING REPORT", 14),
        ("Purchase Order / SA siparisi: 4500180435", 11),
        ("Sira  PO          Kalem   Malzeme", 11),
        ("1     4500180435  00001   AMS4911(20THK)B", 11),
        ("Material: AMS4911(20THK)B  REV R OR LATER", 11),
        ("Specs: AMS4911S, AIMS 03-18-001, ABS 5125A, DIN 65039, ASTM B265", 10),
        ("", 8),
        ("CHEMICAL COMPOSITION (wt %)", 12),
        ("Al 6.10   V 4.05   Fe 0.18   O 0.13   C 0.02   N 0.01", 11),
        ("", 8),
        ("MECHANICAL TEST", 12),
        ("Tensile Strength: 985 MPa    Yield: 905 MPa    Elongation: 12 %", 11),
    ]
    for text, size in lines:
        page.insert_text((50, y), text, fontsize=size)
        y += size + 12
    data = doc.tobytes()
    doc.close()
    return data


def _wait(pipeline, run_id, timeout=1800):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = pipeline.status(run_id)
        if not snap.get("is_processing"):
            return snap
        time.sleep(2)
    return pipeline.status(run_id)


def main() -> int:
    storage = StorageService()
    storage.clear_inputs()
    storage.save_upload("vendor_scanned.pdf", _make_vendor_pdf(), is_spec=False)
    print(
        f"Providers: layout={get_layout_provider().name} "
        f"ocr={get_ocr_provider().name} llm={get_llm_provider(60).name}"
    )

    pipeline = PipelineService(storage)
    _, msg, run_id = pipeline.start_upload()
    print("Stage 1 (upload->DocLayout->OCR->metadata->spec lookup):", msg, run_id)
    snap = _wait(pipeline, run_id)
    print("  stage1 status:", snap.get("status"))

    regions = storage.read_vendor_ocr_regions(run_id)
    print(f"  REAL OCR regions: {len(regions)}")
    for r in regions[:8]:
        txt = (r.get("text") or "").replace("\n", " ")[:80]
        print(f"    [{r['region_id']}] {r['region_type']}: {txt!r}")
    preview = storage.read_preview(run_id) or {}
    print(f"  metadata: PO={preview.get('po_number')} item={preview.get('po_item')} "
          f"material={preview.get('material')} specs={preview.get('spec_references')}")
    print(f"  spec lookup: {preview.get('spec_doc_status')} (src={preview.get('spec_lookup_source')})")

    _, msg = pipeline.start_comparison(run_id)
    print("Stage 2 (segment->compare->aggregate):", msg)
    snap = _wait(pipeline, run_id)
    print("  stage2 status:", snap.get("status"))

    report = storage.build_inspector_report(run_id)
    if report:
        print("  SUMMARY:", report["summary"])
        for f in report["findings"][:6]:
            print(f"    [{f['id'].split('::')[-1]}] {f['parameter']} -> {f['status']} "
                  f"(spec {f['spec_section']}, vendor {f.get('vendor_value')})")
    print("RESULT:", "PASS" if (report and snap.get("status") == "completed") else "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
