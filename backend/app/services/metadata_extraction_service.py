"""LLM-assisted vendor metadata extraction (Section 2A step 8).

Combines an LLM pass (captures ALL declared specs, brief 0.5) with the
deterministic regex parser as a fallback/backstop. The regex parser fills
po/item/material when the LLM omits them; spec references from both are merged.
"""

from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts.metadata_extraction import (
    METADATA_EXTRACTION_SYSTEM_PROMPT,
    build_metadata_extraction_user_prompt,
    empty_metadata,
)
from app.providers.factory import get_llm_provider
from app.utils.json_utils import parse_json_or_default
from app.services.vendor_po_parser import parse_vendor_ids

logger = get_logger(__name__)


@dataclass
class VendorMetadata:
    po_number: str | None = None
    po_item: str | None = None
    material_number: str | None = None
    spec_references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "po_number": self.po_number,
            "po_item": self.po_item,
            "material_number": self.material_number,
            "spec_references": self.spec_references,
        }


def _normalize_specs(specs) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in specs or []:
        if not s:
            continue
        text = str(s).strip()
        key = text.upper().replace(" ", "")
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


class MetadataExtractionService:
    def __init__(self):
        self._llm = get_llm_provider(settings.segmentation_timeout_seconds)

    def extract(self, first_page_text: str, file_name: str = "") -> VendorMetadata:
        llm_data = self._llm_extract(first_page_text)
        regex_ids = parse_vendor_ids(first_page_text, file_name)

        po_number = llm_data.get("po_number") or regex_ids.po_number
        po_item = llm_data.get("po_item") or regex_ids.po_item
        material = llm_data.get("material_number") or regex_ids.material

        specs = list(llm_data.get("spec_references") or [])
        if regex_ids.material:
            specs.append(regex_ids.material)
        specs = _normalize_specs(specs)

        meta = VendorMetadata(
            po_number=po_number or None,
            po_item=po_item or None,
            material_number=material or None,
            spec_references=specs,
        )
        logger.info(
            "Vendor metadata: PO=%s item=%s material=%s specs=%s",
            meta.po_number, meta.po_item, meta.material_number, meta.spec_references,
        )
        return meta

    def _llm_extract(self, first_page_text: str) -> dict:
        if not (first_page_text or "").strip():
            return empty_metadata()
        try:
            raw = self._llm.complete(
                METADATA_EXTRACTION_SYSTEM_PROMPT,
                build_metadata_extraction_user_prompt(first_page_text),
            )
            data = parse_json_or_default(raw, empty_metadata())
            if not isinstance(data, dict):
                return empty_metadata()
            return {**empty_metadata(), **data}
        except Exception as error:  # noqa: BLE001
            logger.warning("LLM metadata cikarimi basarisiz, regex fallback: %s", error)
            return empty_metadata()
