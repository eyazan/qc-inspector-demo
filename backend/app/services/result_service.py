"""Result Service — DB'den sonuc okuma, ozet, finding listesi."""

from app.core.database import session_scope
from app.core.logging import get_logger
from app.db.repository import RunRepository

logger = get_logger(__name__)


class ResultService:
    def list_results(self, inspector_id: str | None = None) -> list[dict]:
        with session_scope() as db:
            repo = RunRepository(db)
            runs = repo.list_runs(inspector_id=inspector_id)
            results = []
            for run in runs:
                # Sadece KARSILASTIRMASI TAMAMLANMIS run'lar sonuclara girer.
                # Asama 1 (yukleme) biten ama henuz karsilastirilmamis run'lar
                # (awaiting_comparison), islenmekte olanlar (processing) ve
                # hatali olanlar (failed) sonuclar listesinde GORUNMEZ.
                if run.status != "completed":
                    continue
                vendor_files = [d.filename for d in run.documents if d.doc_kind == "vendor"]
                spec_files = [d.filename for d in run.documents if d.doc_kind == "spec"]
                results.append({
                    "id": run.id,
                    "type": "final_aggregation",
                    "display_name": run.display_name,
                    "po_number": run.po_number,
                    "po_item": run.po_item,
                    "material": run.material,
                    "status": run.status,
                    "vendor_file": ", ".join(vendor_files) or None,
                    "spec_file": ", ".join(spec_files) or None,
                    "timestamp": run.created_at.isoformat() if run.created_at else None,
                })
            return results

    def get_report(self, run_id: str) -> dict | None:
        with session_scope() as db:
            repo = RunRepository(db)
            run = repo.get_run(run_id)
            if run is None:
                return None
            findings = repo.get_findings(run_id)
            finding_items = [self._finding_to_dict(f) for f in findings]
            return {
                "id": run.id,
                "type": "final_aggregation",
                "content": run.final_report or "",
                "po_number": run.po_number,
                "po_item": run.po_item,
                "material": run.material,
                "findings": finding_items,
                "summary": self._summarize(finding_items),
            }

    def get_findings(self, run_id: str) -> list[dict]:
        with session_scope() as db:
            findings = RunRepository(db).get_findings(run_id)
            return [self._finding_to_dict(f) for f in findings]

    def regions_for_review(self, run_id: str) -> list[dict]:
        with session_scope() as db:
            regions = RunRepository(db).regions_needing_review(run_id)
            return [{
                "id": r.id,
                "region_id": r.region_id,
                "page_number": r.page_number,
                "region_type": r.region_type,
                "text": r.text,
                "confidence": r.confidence,
                "crop_path": r.crop_path,
            } for r in regions]

    def rename(self, run_id: str, new_name: str) -> bool:
        with session_scope() as db:
            return RunRepository(db).rename_run(run_id, new_name)

    def delete(self, run_id: str) -> bool:
        with session_scope() as db:
            return RunRepository(db).delete_run(run_id)

    def _finding_to_dict(self, f) -> dict:
        return {
            "id": f.id,
            "parameter": f.parameter,
            "spec_value": f.spec_value,
            "vendor_value": f.vendor_value,
            "unit": f.unit,
            "status": f.status,
            "severity": f.severity,
            "rationale": f.rationale,
            "spec_section": f.spec_section,
            "page_ref": f.page_ref,
            "deviation_pct": f.deviation_pct,
            "source": f.source,
            "has_override": len(f.overrides) > 0,
            "override_note": f.overrides[-1].note if f.overrides else None,
        }

    def _summarize(self, findings: list[dict]) -> dict:
        counts = {}
        for f in findings:
            counts[f["status"]] = counts.get(f["status"], 0) + 1
        return counts


result_service = ResultService()
