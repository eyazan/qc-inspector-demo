from app.core.config import settings
from app.core.constants import normalize_result
from app.core.logging import get_logger
from app.prompts import prompts
from app.providers.factory import get_llm_provider
from app.services.ocr.models import DocumentSegment
from app.utils.json_utils import parse_json_or_default

logger = get_logger(__name__)


class ComparisonService:
    def __init__(self):
        self._llm = get_llm_provider(settings.comparison_timeout_seconds)

    def compare(self, segment: DocumentSegment, specification: str) -> list[dict]:
        """Return STRUCTURED findings for one segment (JSON, with citations)."""
        user_prompt = prompts.build_comparison_user(segment.to_dict(), specification)
        raw = self._llm.complete(prompts.segment_comparison_system, user_prompt)
        data = parse_json_or_default(raw, {"findings": []})
        findings = data.get("findings", []) if isinstance(data, dict) else []
        return [self._normalize(f, segment) for f in findings if isinstance(f, dict)]

    def _normalize(self, finding: dict, segment: DocumentSegment) -> dict:
        region_ids = finding.get("vendor_region_ids") or []
        if isinstance(region_ids, str):
            region_ids = [region_ids]
        return {
            "parameter": finding.get("parameter") or "(belirtilmemis)",
            "result": normalize_result(finding.get("result")),
            "severity": (finding.get("severity") or "MEDIUM").upper(),
            "spec_section": finding.get("spec_section"),
            "spec_evidence": finding.get("spec_evidence"),
            "vendor_page": finding.get("vendor_page"),
            "vendor_region_ids": region_ids,
            "vendor_evidence": finding.get("vendor_evidence"),
            "rationale": finding.get("rationale") or "",
            "doc_type": segment.doc_type,
        }
