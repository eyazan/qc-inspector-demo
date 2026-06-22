"""Spec structure parsing — identity, section/clause tree, cross-references.

Deterministic (regex) so it runs without an LLM and on noisy OCR text. Designed
against the real AMS4911-style specs: dense "Applicable Documents" lists and
numbered sections like "3.1 Composition", "3.5 Tensile Properties".
"""

import re

# Known spec-code families. Order matters: more specific patterns first.
_SPEC_FAMILIES = [
    r"AMS\s?\d{3,5}[A-Z]?",
    r"AIMS\s?\d{2}-\d{2}-\d{3}",
    r"ABS\s?\d{3,5}[A-Z]?",
    r"DIN\s?\d{3,6}",
    r"ASTM\s?[A-Z]\d{1,4}(?:/[A-Z]\d{1,4}M?)?",
    r"AS\s?\d{3,5}",
    r"ARP\s?\d{3,5}",
    r"E\d{1,4}(?:/E\d{1,4}M?)?",  # ASTM E-series shorthand (E8, E290)
    r"S-\d{2,5}[A-Z]?",
    r"PWA\s?\d{2,5}",
]
_SPEC_RE = re.compile(r"\b(" + "|".join(_SPEC_FAMILIES) + r")\b")

_REVISION_RE = re.compile(r"\bREV(?:ISION)?\.?\s*([A-Z]{1,3}|\d{1,3})\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,3})\s+([^\d\n][^\n]{1,90})")

# Label-based spec number: most spec docs print "Spec No / Specification No /
# Specification Number" on the first page with the code next to it. This is the
# most general signal (works for arbitrary specs, not just known families).
_SPEC_LABEL_RE = re.compile(
    r"\bSPEC(?:IFICATION)?\.?\s*(?:NO\.?|NUMBER|NUM\.?|#)\s*[:.#\-]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9\-_./]{1,39})",
    re.IGNORECASE,
)


def normalize(spec_no: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (spec_no or "").upper())


def extract_spec_no_from_label(text: str) -> str | None:
    """Spec code printed next to a 'Spec No / Specification No' label, if any.

    Requires a digit in the value (spec numbers carry digits) to avoid matching
    stray words after the label.
    """
    m = _SPEC_LABEL_RE.search(text or "")
    if not m:
        return None
    cand = m.group(1).strip().rstrip(".,;:-/")
    if re.search(r"\d", cand) and 2 <= len(cand) <= 40:
        return cand
    return None


def extract_identity(text: str, file_name: str = "") -> tuple[str | None, str | None]:
    """Best-effort (spec_no, revision) from spec text, falling back to filename.

    Priority: explicit 'Spec No' label on the page -> known spec-code family
    (AMS/ABS/ASTM...) -> spec code in the filename.
    """
    spec_no = extract_spec_no_from_label(text)
    if not spec_no:
        m = _SPEC_RE.search(text or "")
        if m:
            spec_no = re.sub(r"\s+", "", m.group(1))
    if not spec_no and file_name:
        fm = _SPEC_RE.search(file_name)
        if fm:
            spec_no = re.sub(r"\s+", "", fm.group(1))

    revision = None
    rm = _REVISION_RE.search(text or "")
    if rm:
        revision = rm.group(1).upper()
    return spec_no, revision


def parse_sections(pages: list[str]) -> list[dict]:
    """Parse numbered sections across pages. pages[i] is page i+1's text."""
    sections: list[dict] = []
    current: dict | None = None
    for page_index, page_text in enumerate(pages):
        page_number = page_index + 1
        for raw_line in (page_text or "").splitlines():
            line = raw_line.rstrip()
            heading = _SECTION_RE.match(line)
            if heading:
                if current:
                    current["text"] = current["text"].strip()
                    sections.append(current)
                current = {
                    "section_no": heading.group(1),
                    "title": heading.group(2).strip(),
                    "page_number": page_number,
                    "text": "",
                }
            elif current is not None and line.strip():
                current["text"] += line.strip() + "\n"
    if current:
        current["text"] = current["text"].strip()
        sections.append(current)
    return sections


def detect_references(pages: list[str], own_spec_no: str | None) -> list[dict]:
    """Find references to OTHER specs; one record per distinct referenced spec."""
    own_norm = normalize(own_spec_no) if own_spec_no else ""
    seen: set[str] = set()
    refs: list[dict] = []
    for page_index, page_text in enumerate(pages):
        page_number = page_index + 1
        text = page_text or ""
        for m in _SPEC_RE.finditer(text):
            code = re.sub(r"\s+", "", m.group(1))
            norm = normalize(code)
            if not norm or norm == own_norm or norm in seen:
                continue
            seen.add(norm)
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            context = re.sub(r"\s+", " ", text[start:end]).strip()
            refs.append(
                {
                    "referenced_spec_no": code,
                    "context": context,
                    "page_number": page_number,
                    "indexed": False,
                }
            )
    return refs
