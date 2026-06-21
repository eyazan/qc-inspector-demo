import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.image_utils import image_bytes_to_pdf, is_image

logger = get_logger(__name__)

METADATA_FILENAME = "metadata.json"
FINAL_REPORT_FILENAME = "final_report.md"
FINAL_REPORT_JSON_FILENAME = "final_report.json"
SEGMENT_MARKER = "__seg__"
OCR_SCHEMA_VERSION = "1.0"


class StorageService:
    def __init__(self):
        self._input_spec = settings.input_spec_path
        self._input_vendor = settings.input_vendor_path
        self._output = settings.output_path
        self._static_mount = settings.static_mount_path
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for path in (self._input_spec, self._input_vendor, self._output):
            path.mkdir(parents=True, exist_ok=True)

    def save_upload(self, filename: str, data: bytes, is_spec: bool) -> Path:
        target_dir = self._input_spec if is_spec else self._input_vendor
        target_dir.mkdir(parents=True, exist_ok=True)
        # Vendor docs often arrive as photos (JPEG/HEIC-converted). Normalize a
        # raster image to a single-page PDF so the pipeline stays format-agnostic.
        if is_image(filename):
            try:
                data = image_bytes_to_pdf(data)
                filename = f"{Path(filename).stem}.pdf"
            except Exception:  # noqa: BLE001
                logger.exception("Gorsel PDF'e cevrilemedi (%s); ham kaydediliyor", filename)
        target = target_dir / filename
        target.write_bytes(data)
        return target

    def list_input_pdfs(self) -> tuple[list[Path], list[Path]]:
        specs = sorted(p for p in self._input_spec.glob("*.pdf"))
        vendors = sorted(p for p in self._input_vendor.glob("*.pdf"))
        return specs, vendors

    def clear_inputs(self) -> None:
        for path in (self._input_spec, self._input_vendor):
            for pdf in path.glob("*.pdf"):
                pdf.unlink(missing_ok=True)

    def create_run(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}"
        run_path = self._output / run_id
        for sub in ("spec", "vendor", "comparison", "reports", "pdfs/spec", "pdfs/vendor"):
            (run_path / sub).mkdir(parents=True, exist_ok=True)
        return run_id

    def run_path(self, run_id: str) -> Path:
        return self._output / run_id

    def copy_pdf_into_run(self, run_id: str, source: Path, is_spec: bool) -> str:
        subdir = "pdfs/spec" if is_spec else "pdfs/vendor"
        target = self.run_path(run_id) / subdir / source.name
        shutil.copy2(source, target)
        return f"{self._static_mount}/{run_id}/{subdir}/{source.name}"

    def save_ocr(self, run_id: str, name: str, regions: list[dict], is_spec: bool) -> None:
        subdir = "spec" if is_spec else "vendor"
        target = self.run_path(run_id) / subdir / f"{name}.json"
        target.write_text(json.dumps(regions, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_segment_report(self, run_id: str, index: int, content: str) -> str:
        filename = f"segment_{index}.md"
        target = self.run_path(run_id) / "comparison" / filename
        target.write_text(content, encoding="utf-8")
        return filename

    def save_final_report(self, run_id: str, content: str) -> str:
        target = self.run_path(run_id) / "reports" / FINAL_REPORT_FILENAME
        target.write_text(content, encoding="utf-8")
        return FINAL_REPORT_FILENAME

    def save_final_report_json(self, run_id: str, report: dict) -> str:
        target = self.run_path(run_id) / "reports" / FINAL_REPORT_JSON_FILENAME
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return FINAL_REPORT_JSON_FILENAME

    def read_final_report_json(self, run_id: str) -> Optional[dict]:
        target = self.run_path(run_id) / "reports" / FINAL_REPORT_JSON_FILENAME
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    def save_segment_findings(self, run_id: str, index: int, findings: dict) -> str:
        filename = f"segment_{index}.json"
        target = self.run_path(run_id) / "comparison" / filename
        target.write_text(
            json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return filename

    def build_inspector_report(self, run_id: str) -> Optional[dict]:
        """Frontend-shaped report (InspectorReport screen): findings + summary +
        PO metadata, with the result enum mapped to the UI status vocabulary."""
        from app.core.constants import to_frontend_status

        report = self.read_final_report_json(run_id)
        if report is None:
            return None
        preview = self.read_preview(run_id) or {}

        findings = []
        summary: dict[str, int] = {}
        for f in report.get("findings", []):
            status = to_frontend_status(f.get("effective_result") or f.get("result"))
            summary[status] = summary.get(status, 0) + 1
            findings.append(
                {
                    "id": f.get("finding_id"),
                    "parameter": f.get("parameter"),
                    "spec_section": f.get("spec_section"),
                    "spec_value": f.get("spec_evidence"),
                    "vendor_value": f.get("vendor_evidence"),
                    "status": status,
                    "severity": (f.get("severity") or "MEDIUM"),
                    "source": "llm",
                    "rationale": f.get("rationale"),
                    "deviation_pct": f.get("deviation_pct"),
                    "page_ref": f.get("vendor_page"),
                    "has_override": bool(f.get("overrides")),
                    "override_note": f.get("override_note"),
                }
            )

        narrative_path = self.run_path(run_id) / "reports" / FINAL_REPORT_FILENAME
        content = narrative_path.read_text(encoding="utf-8") if narrative_path.exists() else None

        return {
            "id": run_id,
            "type": "final_aggregation",
            "po_number": preview.get("po_number"),
            "po_item": preview.get("po_item"),
            "material": preview.get("material"),
            "summary": summary,
            "findings": findings,
            "referenced_spec_warnings": report.get("referenced_spec_warnings", []),
            "content": content,
            "filename": FINAL_REPORT_FILENAME,
        }

    def regions_for_review_list(self, run_id: str, min_confidence=None) -> list[dict]:
        """review-regions as a bare list (the InspectorReport screen reads .length)."""
        regions = self.regions_for_review(run_id, min_confidence)
        return [
            {
                "id": r.get("region_id"),
                "region_id": r.get("region_id"),
                "page_number": r.get("page_number"),
                "region_type": r.get("region_type"),
                "text": r.get("text", "") or "",
                "confidence": r.get("confidence"),
                "needs_review": True,
            }
            for r in regions
        ]

    def write_metadata(self, run_id: str, metadata: dict) -> None:
        target = self.run_path(run_id) / METADATA_FILENAME
        target.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_metadata(self, run_id: str) -> Optional[dict]:
        target = self.run_path(run_id) / METADATA_FILENAME
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    def list_runs(self) -> list[str]:
        if not self._output.exists():
            return []
        runs = [p.name for p in self._output.iterdir() if p.is_dir()]
        return sorted(runs, reverse=True)

    def list_comparison_results(self) -> list[dict]:
        results = []
        for run_id in self.list_runs():
            metadata = self.read_metadata(run_id)
            if metadata is None:
                continue
            results.append(self._final_result_item(run_id, metadata))
        return results

    def _final_result_item(self, run_id: str, metadata: dict) -> dict:
        return {
            "id": run_id,
            "type": "final_aggregation",
            "vendor_file": ", ".join(metadata.get("vendor_files", [])) or None,
            "spec_file": ", ".join(metadata.get("spec_files", [])) or None,
            "po_info": metadata.get("display_name"),
            "display_name": metadata.get("display_name"),
            "timestamp": metadata.get("timestamp"),
            "spec_pdf_path": metadata.get("spec_pdf_path"),
            "vendor_pdf_path": metadata.get("vendor_pdf_path"),
        }

    def read_report(self, report_id: str) -> Optional[dict]:
        if SEGMENT_MARKER in report_id:
            return self._read_segment(report_id)
        return self._read_final(report_id)

    def _read_final(self, run_id: str) -> Optional[dict]:
        metadata = self.read_metadata(run_id)
        if metadata is None:
            return None
        report_path = self.run_path(run_id) / "reports" / FINAL_REPORT_FILENAME
        if not report_path.exists():
            return None
        return {
            "id": run_id,
            "type": "final_aggregation",
            "content": report_path.read_text(encoding="utf-8"),
            "filename": FINAL_REPORT_FILENAME,
        }

    def _read_segment(self, report_id: str) -> Optional[dict]:
        run_id, _, index = report_id.partition(SEGMENT_MARKER)
        metadata = self.read_metadata(run_id)
        if metadata is None:
            return None
        for segment in metadata.get("segments", []):
            if str(segment.get("index")) == index:
                report_path = self.run_path(run_id) / "comparison" / segment["filename"]
                if not report_path.exists():
                    return None
                return {
                    "id": report_id,
                    "type": "segment",
                    "content": report_path.read_text(encoding="utf-8"),
                    "filename": segment["filename"],
                }
        return None

    def grouped_segments(self) -> dict:
        groups: dict[str, list[dict]] = {}
        for run_id in self.list_runs():
            metadata = self.read_metadata(run_id)
            if metadata is None:
                continue
            for segment in metadata.get("segments", []):
                doc_type = segment.get("doc_type", "other")
                item = self._segment_item(run_id, metadata, segment)
                groups.setdefault(doc_type, []).append(item)

        document_types = [
            {"type": doc_type, "count": len(items), "segments": items}
            for doc_type, items in groups.items()
        ]
        return {"document_types": document_types}

    def _segment_item(self, run_id: str, metadata: dict, segment: dict) -> dict:
        report_path = self.run_path(run_id) / "comparison" / segment["filename"]
        content = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        return {
            "id": f"{run_id}{SEGMENT_MARKER}{segment['index']}",
            "document_type": segment.get("doc_type"),
            "vendor_id": run_id,
            "spec_document": ", ".join(metadata.get("spec_files", [])) or None,
            "content": content,
            "filename": segment.get("filename"),
            "vendor_pdf_path": metadata.get("vendor_pdf_path"),
            "spec_pdf_path": metadata.get("spec_pdf_path"),
        }

    def rename_run(self, run_id: str, new_name: str) -> bool:
        metadata = self.read_metadata(run_id)
        if metadata is None:
            return False
        metadata["display_name"] = new_name
        self.write_metadata(run_id, metadata)
        return True

    def delete_run(self, run_id: str) -> bool:
        run_path = self.run_path(run_id)
        if not run_path.exists():
            return False
        shutil.rmtree(run_path)
        return True


# ============================================================================
# İKİ AŞAMALI AKIŞ için ek metodlar (orijinal metodlar yukarıda korundu).
# Hepsi dosya-tabanlı; preview verisi run klasorunde preview.json'da tutulur.
# ============================================================================

    def save_upload_to_run(self, run_id: str, filename: str, data: bytes, is_spec: bool) -> str:
        """Yuklemeyi dogrudan run klasorune kaydet (Asama 1; input klasoru yerine)."""
        subdir = "pdfs/spec" if is_spec else "pdfs/vendor"
        target_dir = self.run_path(run_id) / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        target.write_bytes(data)
        return str(target)

    def save_preview(self, run_id: str, preview: dict) -> None:
        target = self.run_path(run_id) / "preview.json"
        target.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_preview(self, run_id: str) -> Optional[dict]:
        target = self.run_path(run_id) / "preview.json"
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    def update_preview(self, run_id: str, **fields) -> dict:
        preview = self.read_preview(run_id) or {}
        preview.update(fields)
        self.save_preview(run_id, preview)
        return preview

    def vendor_pdf_file(self, run_id: str) -> Optional[Path]:
        d = self.run_path(run_id) / "pdfs/vendor"
        if not d.exists():
            return None
        pdfs = sorted(d.glob("*.pdf"))
        return pdfs[0] if pdfs else None

    def spec_pdf_file(self, run_id: str) -> Optional[Path]:
        d = self.run_path(run_id) / "pdfs/spec"
        if not d.exists():
            return None
        pdfs = sorted(d.glob("*.pdf"))
        return pdfs[0] if pdfs else None

    def copy_spec_pdf_into_run(self, run_id: str, source: Path) -> str:
        """Bulunan spec PDF'ini run'a kopyala (onizleme sag sutun icin)."""
        target_dir = self.run_path(run_id) / "pdfs/spec"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        return str(target)

    def save_vendor_ocr_regions(self, run_id: str, name: str, regions: list[dict]) -> None:
        self.save_ocr(run_id, name, regions, is_spec=False)

    def save_ocr_pages(self, run_id: str, regions: list[dict]) -> dict:
        """Persist page-level + document-level OCR JSON (versioned schema).

        Every page that produced regions gets vendor/pages/page_{n}.json; a
        document-level vendor/document.json summarizes all pages. Returns the
        document summary.
        """
        pages_dir = self.run_path(run_id) / "vendor" / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        by_page: dict[int, list[dict]] = {}
        for r in regions:
            by_page.setdefault(r.get("page_number", 0), []).append(r)

        page_summaries = []
        for page_number in sorted(by_page):
            page_doc = {
                "schema_version": OCR_SCHEMA_VERSION,
                "run_id": run_id,
                "page_number": page_number,
                "region_count": len(by_page[page_number]),
                "regions": by_page[page_number],
            }
            (pages_dir / f"page_{page_number}.json").write_text(
                json.dumps(page_doc, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            page_summaries.append(
                {"page_number": page_number, "region_count": len(by_page[page_number])}
            )

        document = {
            "schema_version": OCR_SCHEMA_VERSION,
            "run_id": run_id,
            "page_count": len(by_page),
            "total_regions": len(regions),
            "pages": page_summaries,
        }
        (self.run_path(run_id) / "vendor" / "document.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return document

    def read_vendor_ocr_regions(self, run_id: str) -> list[dict]:
        """Asama 1'de kaydedilen vendor OCR JSON'larini geri oku (Asama 2 icin)."""
        vendor_dir = self.run_path(run_id) / "vendor"
        out: list[dict] = []
        if not vendor_dir.exists():
            return out
        for jf in sorted(vendor_dir.glob("*.json")):
            if jf.name == "document.json":
                continue  # document summary is a dict, not a region list
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    out.extend(data)
            except Exception:  # noqa: BLE001
                continue
        return out

    # ---- Structured findings: review regions + inspector overrides ----

    def regions_for_review(self, run_id: str, min_confidence=None) -> list[dict]:
        """Regions needing inspector review: empty text, or confidence below
        the configured threshold (mirrors the needs_review flag concept)."""
        regions = self.read_vendor_ocr_regions(run_id)
        flagged = []
        for r in regions:
            text = (r.get("text") or "").strip()
            conf = r.get("confidence")
            needs = not text
            if (
                not needs
                and min_confidence is not None
                and conf is not None
                and conf < min_confidence
            ):
                needs = True
            if needs:
                flagged.append({**r, "needs_review": True})
        return flagged

    @staticmethod
    def run_id_from_finding(finding_id: str) -> Optional[str]:
        if "::" in (finding_id or ""):
            return finding_id.split("::", 1)[0]
        return None

    def apply_override(self, finding_id: str, override: dict) -> Optional[dict]:
        """Apply an inspector override to a finding in final_report.json.

        Returns the updated finding, or None if the run/finding is not found.
        """
        run_id = self.run_id_from_finding(finding_id)
        if not run_id:
            return None
        report = self.read_final_report_json(run_id)
        if report is None:
            return None
        target = None
        for finding in report.get("findings", []):
            if finding.get("finding_id") == finding_id:
                target = finding
                break
        if target is None:
            return None
        target.setdefault("overrides", []).append(override)
        if override.get("new_status"):
            target["effective_result"] = override["new_status"]
        if override.get("note"):
            target["override_note"] = override["note"]
        self.save_final_report_json(run_id, report)
        return target
