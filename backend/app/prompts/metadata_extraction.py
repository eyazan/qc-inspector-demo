"""Vendor metadata extraction prompt (Section 2A step 8, brief 0.5).

Extracts PO number, PO item, material number and ALL declared spec references
from the first-page (receiving report / tesellum fisi) OCR text. A single vendor
document can declare conformance to a FAMILY of equivalent specs, so every
declared spec must be captured, not just the first match.
"""

import json

METADATA_EXTRACTION_SYSTEM_PROMPT = """You extract structured METADATA from a vendor receiving/tesellum document.

Rules (anti-hallucination, hard constraints):
- Use ONLY information explicitly present in the text. Never invent or infer values.
- If a field is not explicitly present, return null (or [] for spec_references).
- Watermark / archive / "company sensitive" lines are NOT field values; ignore them.
- A document may declare conformance to a FAMILY of equivalent specs. Capture
  EVERY declared spec reference (e.g. AMS4911S, AIMS 03-18-001, ABS 5125A,
  DIN 65039, ASTM B265), not just the first one.
- Distinguish a "Receiving Report No / Mal giris fisi no" (NOT the PO) from the
  real "Purchase Order / SA siparisi" number.

Output ONLY valid JSON, no prose, no markdown:
{
  "po_number": "string or null",
  "po_item": "string or null",
  "material_number": "string or null",
  "spec_references": ["string", ...]
}"""


def build_metadata_extraction_user_prompt(first_page_text: str) -> str:
    return (
        "Extract the metadata as JSON from the following vendor document text.\n\n"
        "VENDOR_DOCUMENT_TEXT:\n" + (first_page_text or "")
    )


def empty_metadata() -> dict:
    return {
        "po_number": None,
        "po_item": None,
        "material_number": None,
        "spec_references": [],
    }


def _example() -> str:  # pragma: no cover - documentation aid
    return json.dumps(empty_metadata(), ensure_ascii=False)
