"""Object-store artifact mirroring + serve/read fallback.

A LocalFsObjectStore rooted at a separate dir stands in for a remote store
(S3/MinIO share the same ObjectStore interface). We write a run, delete the
LOCAL copies, and assert reads + PDF serving still resolve from the store — i.e.
a stateless replica can serve a run created by another. Local-only behavior
(mirror disabled) is covered by the existing 58 tests staying green.
"""

import shutil

from app.repositories.object_store import LocalFsObjectStore


def _storage_with_mirror(tmp_path):
    from app.core.config import get_settings

    import os

    os.environ["DATA_ROOT"] = str(tmp_path / "local")
    get_settings.cache_clear()
    from app.services.storage_service import StorageService

    st = StorageService()
    # Inject a remote-like store (S3 stand-in) as the mirror target.
    st._mirror_store = LocalFsObjectStore(root=tmp_path / "remote", mount="/files")
    return st


def test_artifacts_mirrored_and_served_from_store(tmp_path):
    st = _storage_with_mirror(tmp_path)
    run_id = st.create_run()

    # A vendor PDF copied into the run + a recorded path in metadata.
    src = tmp_path / "vendor.pdf"
    src.write_bytes(b"%PDF-1.4 vendor")
    pdf_url = st.copy_pdf_into_run(run_id, src, is_spec=False)
    st.write_metadata(run_id, {"display_name": "PO1", "vendor_pdf_path": pdf_url})
    st.save_preview(run_id, {"po_number": "PO1"})
    st.save_final_report(run_id, "# Rapor")
    st.save_final_report_json(run_id, {"run_id": run_id, "findings": [], "summary": {}})

    # Everything also landed in the remote store under run-relative keys.
    assert st._mirror_store.exists(f"{run_id}/pdfs/vendor/vendor.pdf")
    assert st._mirror_store.exists(f"{run_id}/metadata.json")
    assert st._mirror_store.exists(f"{run_id}/reports/final_report.json")

    # Simulate a replica with no local artifacts: wipe the local run dir.
    shutil.rmtree(st.run_path(run_id))
    assert not st.run_path(run_id).exists()

    # Reads + PDF serving still resolve via the store fallback.
    assert st.read_metadata(run_id)["display_name"] == "PO1"
    assert st.read_preview(run_id)["po_number"] == "PO1"
    assert st.read_final_report_json(run_id)["run_id"] == run_id
    served = st.read_pdf_bytes(run_id, is_spec=False)
    assert served is not None
    data, name = served
    assert data == b"%PDF-1.4 vendor" and name == "vendor.pdf"


def test_mirror_disabled_no_remote_writes(tmp_path):
    """With no mirror store (local default), nothing is pushed and reads still
    work straight off the FS."""
    from app.core.config import get_settings
    import os

    os.environ["DATA_ROOT"] = str(tmp_path / "local")
    get_settings.cache_clear()
    from app.services.storage_service import StorageService

    st = StorageService()
    st._mirror_store = None
    run_id = st.create_run()
    st.save_final_report_json(run_id, {"run_id": run_id, "findings": []})
    assert st.read_final_report_json(run_id)["run_id"] == run_id
