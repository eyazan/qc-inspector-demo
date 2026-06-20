"""End-to-end vendor pipeline smoke test (two-stage flow).

Builds a vendor PDF from the sample images (data/samples/*.jpg) if present, runs
Stage 1 (upload -> preview -> pause) then Stage 2 (comparison -> aggregation),
and prints the structured final_report plus which providers were real vs mock.

    RUN_MODE=mock python scripts/test_full_pipeline.py     # fully offline
    python scripts/test_full_pipeline.py                    # uses configured providers
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.providers.factory import (  # noqa: E402
    get_layout_provider,
    get_llm_provider,
    get_ocr_provider,
)
from app.services.pipeline_service import PipelineService  # noqa: E402
from app.services.storage_service import StorageService  # noqa: E402
from app.utils.image_utils import images_to_pdf  # noqa: E402

VENDOR_IMAGE_COUNT = 4


def _build_vendor_pdf() -> bytes:
    samples = sorted(Path("data/samples").glob("*.jpg"))[:VENDOR_IMAGE_COUNT]
    if samples:
        print(f"Vendor PDF: {len(samples)} sample image(s) -> {[p.name for p in samples]}")
        return images_to_pdf([p.read_bytes() for p in samples])
    # Fallback synthetic vendor doc.
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 60), "Mal giris fisi\nPurchase Order 4500180435\nAMS4911(20THK)B")
    data = doc.tobytes()
    doc.close()
    print("Vendor PDF: synthetic (no sample images found)")
    return data


def _wait(pipeline: PipelineService, run_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = pipeline.status(run_id)
        if not snap.get("is_processing"):
            return snap
        time.sleep(0.5)
    return pipeline.status(run_id)


def main() -> int:
    storage = StorageService()
    storage.clear_inputs()
    storage.save_upload("vendor_sample.pdf", _build_vendor_pdf(), is_spec=False)

    print(
        f"Providers -> layout={get_layout_provider().name} "
        f"ocr={get_ocr_provider().name} llm={get_llm_provider(60).name} "
        f"(run_mode={settings.run_mode})"
    )

    pipeline = PipelineService(storage)

    started, msg, run_id = pipeline.start_upload()
    print(f"Stage 1 start: {started} {msg} run_id={run_id}")
    if not started:
        return 1
    snap = _wait(pipeline, run_id)
    print(f"Stage 1 end: status={snap.get('status')} step={snap.get('current_step')}")
    preview = storage.read_preview(run_id) or {}
    print(
        f"  Extracted: PO={preview.get('po_number')} item={preview.get('po_item')} "
        f"material={preview.get('material')} specs={preview.get('spec_references')}"
    )
    print(f"  Spec lookup: {preview.get('spec_doc_status')} (source={preview.get('spec_lookup_source')})")
    print(f"  Dedup: {preview.get('dedup_stats', {}).get('before')} -> {preview.get('dedup_stats', {}).get('after')}")

    started, msg = pipeline.start_comparison(run_id)
    print(f"Stage 2 start: {started} {msg}")
    snap = _wait(pipeline, run_id)
    print(f"Stage 2 end: status={snap.get('status')} step={snap.get('current_step')}")

    report = storage.read_final_report_json(run_id)
    if report:
        print("  final_report.json summary:", report.get("summary"))
        print("  findings:", report.get("total_findings"))
        for f in report.get("findings", [])[:3]:
            print(
                f"    [{f['finding_id']}] {f['parameter']} -> {f['result']} "
                f"(spec {f.get('spec_section')}, vendor s.{f.get('vendor_page')} {f.get('vendor_region_ids')})"
            )
    narrative = storage.read_report(run_id)
    if narrative:
        print("  final_report_text head:")
        print("   " + "\n   ".join(narrative["content"].splitlines()[:6]))

    ok = snap.get("status") == "completed" and report is not None
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
