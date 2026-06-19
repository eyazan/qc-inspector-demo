import json

from app.core.config import settings
from app.core.logging import get_logger
from app.prompts import prompts
from app.providers.factory import get_llm_provider
from app.services.ocr.models import DocumentSegment, OcrRegion

logger = get_logger(__name__)


class SegmentationService:
    def __init__(self):
        self._llm = get_llm_provider(settings.segmentation_timeout_seconds)

    def segment(self, regions: list[OcrRegion]) -> list[DocumentSegment]:
        region_dicts = [region.to_dict() for region in regions]
        region_index = {region.region_id: region for region in regions}

        user_prompt = prompts.build_segmentation_user(region_dicts)
        raw = self._llm.complete(prompts.segmentation_system, user_prompt)
        parsed = self._parse_json(raw)

        segments: list[DocumentSegment] = []
        for entry in parsed.get("segments", []):
            content = self._collect_content(entry.get("region_ids", []), region_index)
            segments.append(
                DocumentSegment(
                    doc_type=entry.get("doc_type", "other"),
                    page_range=entry.get("page_range", []),
                    metadata=entry.get("metadata", {}),
                    content=content,
                )
            )
        return segments

    def _collect_content(
        self, region_ids: list[str], region_index: dict[str, OcrRegion]
    ) -> list[dict]:
        content = []
        for region_id in region_ids:
            region = region_index.get(region_id)
            if region is not None:
                content.append(region.to_dict())
        return content

    def _parse_json(self, raw: str) -> dict:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip().strip("`").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                return json.loads(cleaned[start : end + 1])
            raise
