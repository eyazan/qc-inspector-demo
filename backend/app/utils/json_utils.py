"""Lenient JSON parsing for LLM output.

Models sometimes wrap JSON in ```code fences``` or add prose around it. These
helpers strip fences and fall back to the outermost {...} / [...] slice before
raising, so a single stray token doesn't fail the whole pipeline.
"""

import json
from typing import Any


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # ```json\n...\n``` -> middle block
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
    return cleaned.strip().strip("`").strip()


def parse_json_lenient(raw: str) -> Any:
    """Parse JSON from a possibly-noisy model response. Raises on total failure."""
    cleaned = _strip_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost object or array.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_ch)
        end = cleaned.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("LLM ciktisi gecerli JSON'a cevrilemedi")


def parse_json_or_default(raw: str, default: Any) -> Any:
    """Like parse_json_lenient but returns `default` instead of raising."""
    try:
        return parse_json_lenient(raw)
    except (ValueError, json.JSONDecodeError):
        return default
