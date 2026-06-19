"""Final aggregation — deterministic cross-document reconciliation (Section 4).

Reconciliation is done in code (not by the LLM) so it cannot hallucinate
coverage: findings for the same (parameter, spec_section) across segments are
merged, and a substantive result (COMPLIANT/NON_COMPLIANT) in any segment
overrides NOT_COVERED/MISSING from another. Produces the structured final_report
consumed programmatically; the Turkish narrative is rendered from it elsewhere.
"""

from app.core.constants import (
    RESULT_PRIORITY,
    RESULTS,
    RESULT_MISSING,
    RESULT_NOT_COVERED,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class AggregationService:
    def aggregate(
        self,
        segment_findings: list[dict],
        referenced_specs: list[dict] | None = None,
    ) -> dict:
        """segment_findings: list of {segment_index, doc_type, findings:[...]}.

        Returns the structured final_report dict.
        """
        flat: list[dict] = []
        for seg in segment_findings:
            for f in seg.get("findings", []):
                flat.append({**f, "segment_index": seg.get("segment_index")})

        reconciled, notes = self._reconcile(flat)

        for idx, finding in enumerate(reconciled, start=1):
            finding["finding_id"] = f"F{idx:04d}"

        summary = {r: 0 for r in RESULTS}
        for f in reconciled:
            summary[f["result"]] = summary.get(f["result"], 0) + 1

        return {
            "summary": summary,
            "total_findings": len(reconciled),
            "findings": reconciled,
            "referenced_spec_warnings": self._referenced_warnings(referenced_specs),
            "reconciliation_notes": notes,
        }

    def _reconcile(self, findings: list[dict]) -> tuple[list[dict], list[str]]:
        groups: dict[tuple, list[dict]] = {}
        order: list[tuple] = []
        for f in findings:
            key = (
                (f.get("parameter") or "").strip().lower(),
                (f.get("spec_section") or "").strip().lower(),
            )
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(f)

        reconciled: list[dict] = []
        notes: list[str] = []
        for key in order:
            members = groups[key]
            best = max(members, key=lambda f: RESULT_PRIORITY.get(f["result"], 0))
            covered_by_other = any(
                m["result"] not in (RESULT_NOT_COVERED, RESULT_MISSING) for m in members
            )
            if len(members) > 1 and covered_by_other and any(
                m["result"] in (RESULT_NOT_COVERED, RESULT_MISSING) for m in members
            ):
                notes.append(
                    f"'{best.get('parameter')}' bir segmentte kapsanmiyordu, "
                    f"baska segmentte {best['result']} olarak cozuldu."
                )
            merged = dict(best)
            merged["evidence_segments"] = sorted(
                {m.get("segment_index") for m in members if m.get("segment_index") is not None}
            )
            reconciled.append(merged)
        return reconciled, notes

    def _referenced_warnings(self, referenced_specs: list[dict] | None) -> list[dict]:
        warnings = []
        for ref in referenced_specs or []:
            if not ref.get("indexed"):
                warnings.append(
                    {
                        "referenced_spec_no": ref.get("referenced_spec_no"),
                        "message": (
                            f"Referans verilen spec '{ref.get('referenced_spec_no')}' "
                            "indekslenmemis; icerigi dogrulanamadi."
                        ),
                    }
                )
        return warnings
