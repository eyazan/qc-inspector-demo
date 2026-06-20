"""Shared enums/vocab. Result enum stays English in code (Section 4); Turkish is
purely a rendering layer for the human-readable narrative (brief 0.7 #6)."""

# Comparison result enum (Section 4).
RESULT_COMPLIANT = "COMPLIANT"
RESULT_NON_COMPLIANT = "NON_COMPLIANT"
RESULT_NOT_COVERED = "NOT_COVERED_IN_THIS_DOCUMENT"
RESULT_MISSING = "MISSING"
RESULT_UNCLEAR = "UNCLEAR"

RESULTS = [
    RESULT_COMPLIANT,
    RESULT_NON_COMPLIANT,
    RESULT_NOT_COVERED,
    RESULT_MISSING,
    RESULT_UNCLEAR,
]

# English -> Turkish narrative labels (rendering only).
RESULT_TR = {
    RESULT_COMPLIANT: "UYUMLU",
    RESULT_NON_COMPLIANT: "UYUMSUZ",
    RESULT_NOT_COVERED: "BU BELGEDE KAPSANMIYOR",
    RESULT_MISSING: "EKSIK",
    RESULT_UNCLEAR: "BELIRSIZ",
}

# Substantive results outrank NOT_COVERED/MISSING during cross-document
# reconciliation (a gap in one segment may be covered by another).
RESULT_PRIORITY = {
    RESULT_NON_COMPLIANT: 5,
    RESULT_COMPLIANT: 4,
    RESULT_UNCLEAR: 3,
    RESULT_MISSING: 2,
    RESULT_NOT_COVERED: 1,
}

# Frontend (InspectorReport / report_service) status vocabulary. The UI knows
# COMPLIANT | NON_COMPLIANT | PARTIAL | MISSING | NOT_COVERED. Map the internal
# result enum onto it (UNCLEAR -> PARTIAL, NOT_COVERED_IN_THIS_DOCUMENT -> NOT_COVERED).
RESULT_TO_FRONTEND = {
    RESULT_COMPLIANT: "COMPLIANT",
    RESULT_NON_COMPLIANT: "NON_COMPLIANT",
    RESULT_NOT_COVERED: "NOT_COVERED",
    RESULT_MISSING: "MISSING",
    RESULT_UNCLEAR: "PARTIAL",
}


def to_frontend_status(result: str) -> str:
    """Map internal/override result onto the frontend status vocabulary."""
    if not result:
        return "PARTIAL"
    r = str(result).strip().upper()
    if r in RESULT_TO_FRONTEND.values():
        return r  # already frontend vocab (e.g. an override new_status)
    return RESULT_TO_FRONTEND.get(normalize_result(r), "PARTIAL")


# Error pipeline stages (Section 5).
STAGES = [
    "file_upload",
    "pdf_render",
    "layout_detection",
    "ocr",
    "deduplication",
    "metadata_extraction",
    "sap_spec_fetch",
    "spec_lookup",
    "segmentation",
    "comparison",
    "final_aggregation",
    "spec_indexing",
]


def normalize_result(value: str) -> str:
    """Map a model's result string onto the canonical enum; default UNCLEAR."""
    if not value:
        return RESULT_UNCLEAR
    v = str(value).strip().upper().replace(" ", "_")
    if v in RESULTS:
        return v
    aliases = {
        "NOT_COVERED": RESULT_NOT_COVERED,
        "NOT_COVERED_IN_DOCUMENT": RESULT_NOT_COVERED,
        "PARTIAL": RESULT_UNCLEAR,
        "UYUMLU": RESULT_COMPLIANT,
        "UYUMSUZ": RESULT_NON_COMPLIANT,
    }
    return aliases.get(v, RESULT_UNCLEAR)
