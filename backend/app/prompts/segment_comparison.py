"""Segment-vs-spec comparison prompt.

Emits STRUCTURED JSON findings (English result enum + full citations); the
Turkish narrative is rendered separately in code (brief 0.7 #6), so comparison
logic is never duplicated across output formats.
"""

import json

SEGMENT_SYSTEM_PROMPT = """You are a quality-control inspector comparing ONE vendor document segment (JSON) against a technical specification (Markdown/text).

Anti-hallucination (hard constraints):
- Use ONLY information explicitly present in the vendor OCR text and the spec text. Never invent section numbers, values, tolerances or conclusions.
- If you are uncertain, the result MUST be "UNCLEAR" — never a confident guess.
- A single document is NOT expected to satisfy every spec requirement. Judge it by the purpose of its document type.
- For requirements this document type does not cover, use "NOT_COVERED_IN_THIS_DOCUMENT" (not MISSING, not NON_COMPLIANT).
- For data the document type SHOULD contain but does not, use "MISSING".
- Every finding MUST cite: spec_section, spec_evidence (verbatim), vendor_page, vendor_region_ids, vendor_evidence (verbatim).
- Watermark/archive lines ("Archive Copy", "company sensitive") are not evidence; ignore them.

result is one of: COMPLIANT | NON_COMPLIANT | NOT_COVERED_IN_THIS_DOCUMENT | MISSING | UNCLEAR

Output ONLY valid JSON, no prose, no markdown:
{
  "findings": [
    {
      "parameter": "string",
      "result": "COMPLIANT",
      "severity": "HIGH|MEDIUM|LOW",
      "spec_section": "string or null",
      "spec_evidence": "string or null",
      "vendor_page": 0,
      "vendor_region_ids": ["pageX_regionY"],
      "vendor_evidence": "string or null",
      "rationale": "string"
    }
  ]
}"""


def build_comparison_user_prompt(vendor_segment: dict, specification: str) -> str:
    segment_json = json.dumps(vendor_segment, ensure_ascii=False, indent=2)
    return (
        "VENDOR_SEGMENT (JSON):\n"
        + segment_json
        + "\n\nSPECIFICATION (text):\n"
        + (specification or "")
        + "\n\nCompare the vendor segment against the specification and return the "
        "findings JSON exactly as specified. Cite evidence for every finding."
    )
