"""Final aggregation prompt (cross-document reconciliation rules).

Reconciliation is performed DETERMINISTICALLY in aggregation_service over the
structured findings (no hallucination in the critical step). This prompt encodes
the same rules and the JSON contract for an optional LLM narrative/reconciliation
pass, keeping all four prompt files rule-consistent (Section 4)."""

import json

FINAL_AGGREGATION_SYSTEM_PROMPT = """You reconcile per-segment QC findings for one vendor package into a single result set.

Cross-document reconciliation rules:
- Use ONLY information present in the segment findings. Never infer coverage not stated.
- A requirement marked NOT_COVERED_IN_THIS_DOCUMENT in one segment but COMPLIANT/NON_COMPLIANT in another is RESOLVED by the other segment — do not report it as missing.
- Mark a requirement as a real gap (MISSING) only if NO segment covers it.
- If a spec section references another spec that is not indexed, surface a referenced_spec_warning; never fabricate its content.

result enum: COMPLIANT | NON_COMPLIANT | NOT_COVERED_IN_THIS_DOCUMENT | MISSING | UNCLEAR

Output ONLY valid JSON:
{
  "findings": [ { "parameter": "...", "result": "...", "spec_section": "...", "rationale": "..." } ],
  "referenced_spec_warnings": [ { "referenced_spec_no": "...", "message": "..." } ]
}"""


def build_aggregation_user_prompt(segment_findings: list[dict]) -> str:
    return (
        "Reconcile the following per-segment findings into one JSON result set "
        "per the rules.\n\nSEGMENT_FINDINGS:\n"
        + json.dumps(segment_findings, ensure_ascii=False, indent=2)
    )
