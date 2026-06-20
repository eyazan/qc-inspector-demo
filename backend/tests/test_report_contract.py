"""Locks the InspectorReport frontend contract: result-enum -> UI status vocab,
and the build_inspector_report shape (findings[]/summary{}/PO + override)."""

from app.core.constants import to_frontend_status


def test_status_mapping_to_frontend_vocab():
    assert to_frontend_status("COMPLIANT") == "COMPLIANT"
    assert to_frontend_status("NON_COMPLIANT") == "NON_COMPLIANT"
    assert to_frontend_status("NOT_COVERED_IN_THIS_DOCUMENT") == "NOT_COVERED"
    assert to_frontend_status("MISSING") == "MISSING"
    assert to_frontend_status("UNCLEAR") == "PARTIAL"
    # an override new_status already in frontend vocab passes through
    assert to_frontend_status("NOT_COVERED") == "NOT_COVERED"


def _seed(tmp_path):
    from app.core.config import get_settings

    get_settings.cache_clear()
    import os

    os.environ["DATA_ROOT"] = str(tmp_path)
    get_settings.cache_clear()
    from app.services.storage_service import StorageService

    st = StorageService()
    run_id = st.create_run()
    st.save_preview(run_id, {"po_number": "PO1", "po_item": "1", "material": "M"})
    fid = f"{run_id}::F0001"
    st.save_final_report_json(
        run_id,
        {
            "run_id": run_id,
            "summary": {"NOT_COVERED_IN_THIS_DOCUMENT": 1},
            "total_findings": 1,
            "findings": [
                {
                    "finding_id": fid,
                    "parameter": "Tensile",
                    "result": "NOT_COVERED_IN_THIS_DOCUMENT",
                    "severity": "MEDIUM",
                    "spec_section": "3.5",
                    "spec_evidence": "min 130 ksi",
                    "vendor_page": 1,
                    "vendor_region_ids": ["page1_region0"],
                    "vendor_evidence": None,
                    "rationale": "x",
                }
            ],
        },
    )
    return st, run_id, fid


def test_build_inspector_report_shape(tmp_path):
    st, run_id, fid = _seed(tmp_path)
    rep = st.build_inspector_report(run_id)
    assert rep["po_number"] == "PO1"
    assert isinstance(rep["findings"], list) and len(rep["findings"]) == 1
    f = rep["findings"][0]
    assert f["id"] == fid
    assert f["status"] == "NOT_COVERED"          # mapped to frontend vocab
    assert f["spec_value"] == "min 130 ksi"      # spec_evidence -> spec_value
    assert set(rep["summary"]).issubset(
        {"COMPLIANT", "PARTIAL", "NON_COMPLIANT", "MISSING", "NOT_COVERED"}
    )


def test_override_reflected_in_report(tmp_path):
    st, run_id, fid = _seed(tmp_path)
    st.apply_override(fid, {"action": "reject", "new_status": "NON_COMPLIANT", "note": "n"})
    rep = st.build_inspector_report(run_id)
    f = rep["findings"][0]
    assert f["status"] == "NON_COMPLIANT"
    assert f["has_override"] is True
    assert f["override_note"] == "n"
