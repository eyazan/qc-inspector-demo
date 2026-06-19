"""
Spec Parser — spec markdown'i bir kez yapisal requirement listesine cevirir.

RAG yerine bu yaklasim: spec'in TAMAMI parse edilir, hicbir madde kaybolmaz.
Cikan kompakt liste her vendor segmentiyle karsilastirmada kullanilir.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.spec_parsing import (
    SPEC_PARSING_SYSTEM_PROMPT,
    build_spec_parsing_user_prompt,
)
from app.services.clients.llm_client import LlmClient

logger = get_logger(__name__)


class SpecParser:
    def __init__(self):
        self._llm = LlmClient(settings.spec_parse_timeout_seconds)

    def parse(self, spec_markdown: str) -> list[dict]:
        if not spec_markdown.strip():
            return []

        # Mock modu: LLM cagirmadan, markdown'dan regex ile requirement cikar.
        if settings.layout_mode == "mock":
            reqs = _regex_parse(spec_markdown)
            logger.info("Spec (mock/regex) %s gereksinim cikarildi", len(reqs))
            return reqs

        user_prompt = build_spec_parsing_user_prompt(spec_markdown)
        try:
            parsed = self._llm.complete_json(SPEC_PARSING_SYSTEM_PROMPT, user_prompt)
        except Exception as error:  # noqa: BLE001
            logger.error("Spec parse hatasi: %s", error)
            # LLM erisilemezse regex fallback (bos donmektense kismi sonuc)
            return _regex_parse(spec_markdown)

        requirements = parsed.get("requirements", [])
        cleaned = []
        for req in requirements:
            if not req.get("parameter"):
                continue
            cleaned.append(
                {
                    "section_ref": req.get("section_ref"),
                    "parameter": req["parameter"],
                    "limit_type": req.get("limit_type", "exact"),
                    "value_min": _to_float(req.get("value_min")),
                    "value_max": _to_float(req.get("value_max")),
                    "value_exact": _to_float(req.get("value_exact")),
                    "unit": req.get("unit"),
                    "raw_text": req.get("raw_text"),
                    "category": req.get("category", "other"),
                }
            )
        logger.info("Spec'ten %s gereksinim cikarildi", len(cleaned))
        return cleaned


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# LLM'siz (mock/fallback) basit spec parse — markdown satirlarindan
# "min/max/aralik + birim" ifadelerini regex ile cikarir.
import re as _re

_UNIT = r"(MPa|N/mm2|ksi|psi|GPa|HB|HV|HRC|%|mm)"
_NUM = r"(\d+(?:[.,]\d+)?)"

_PATTERNS = [
    # "minimum 380 MPa" / "min 380 MPa"
    (_re.compile(rf"min(?:imum)?\s+{_NUM}\s*{_UNIT}", _re.I), "min"),
    # "maksimum 0.20 %" / "max 0.20 %" / "0.20 max"
    (_re.compile(rf"mak(?:simum)?\s+{_NUM}\s*{_UNIT}", _re.I), "max"),
    (_re.compile(rf"max(?:imum)?\s+{_NUM}\s*{_UNIT}", _re.I), "max"),
    # "250-380 HB" / "250 - 380 HB"
    (_re.compile(rf"{_NUM}\s*[-â€“]\s*{_NUM}\s*{_UNIT}", _re.I), "range"),
]

# Parametre adi tahmini icin anahtar kelimeler
_PARAM_HINTS = {
    "tensile": "Tensile Strength", "cekme": "Tensile Strength",
    "yield": "Yield Strength", "akma": "Yield Strength",
    "hardness": "Hardness", "sertlik": "Hardness",
    "carbon": "Carbon", "karbon": "Carbon",
    "manganese": "Manganese", "mangan": "Manganese",
    "elongation": "Elongation", "uzama": "Elongation",
}


def _guess_param(context: str) -> str:
    low = context.lower()
    for key, name in _PARAM_HINTS.items():
        if key in low:
            return name
    return context.strip()[:60] or "Parameter"


def _regex_parse(markdown: str) -> list[dict]:
    requirements = []
    section = None
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Bolum numarasi tespiti (orn "### 3.5.1 Cekme")
        sec = _re.match(r"#*\s*(\d+(?:\.\d+)*)", line)
        if sec:
            section = sec.group(1)

        for pattern, limit_type in _PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            param = _guess_param(line)
            if limit_type == "range":
                req = {
                    "section_ref": section, "parameter": param, "limit_type": "range",
                    "value_min": _to_float(m.group(1)), "value_max": _to_float(m.group(2)),
                    "value_exact": None, "unit": m.group(3), "raw_text": line,
                    "category": "mechanical",
                }
            else:
                req = {
                    "section_ref": section, "parameter": param, "limit_type": limit_type,
                    "value_min": _to_float(m.group(1)) if limit_type == "min" else None,
                    "value_max": _to_float(m.group(1)) if limit_type == "max" else None,
                    "value_exact": None, "unit": m.group(2), "raw_text": line,
                    "category": "mechanical",
                }
            requirements.append(req)
            break  # satir basina tek requirement
    return requirements
