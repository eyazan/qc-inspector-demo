from app.core.config import settings
from app.core.logging import get_logger
from app.prompts import prompts
from app.providers.factory import get_llm_provider
from app.services.ocr.models import DocumentSegment, OcrRegion
from app.utils.json_utils import parse_json_or_default

logger = get_logger(__name__)


class SegmentationService:
    def __init__(self):
        self._llm = get_llm_provider(settings.segmentation_timeout_seconds)

    def segment(self, regions: list[OcrRegion]) -> list[DocumentSegment]:
        region_dicts = [region.to_dict() for region in regions]
        region_index = {region.region_id: region for region in regions}

        user_prompt = prompts.build_segmentation_user(region_dicts)
        raw = self._llm.complete(prompts.segmentation_system, user_prompt)
        parsed = parse_json_or_default(raw, {"segments": []})

        segments: list[DocumentSegment] = []
        for entry in parsed.get("segments", []) if isinstance(parsed, dict) else []:
            content = self._collect_content(entry.get("region_ids", []), region_index)
            if not content:
                continue
            segments.append(
                DocumentSegment(
                    doc_type=entry.get("doc_type", "other"),
                    page_range=entry.get("page_range", []),
                    metadata=entry.get("metadata", {}),
                    content=content,
                )
            )

        # Robustness: if the model returned malformed/empty output, don't crash —
        # fall back to a single "other" segment with all regions so comparison
        # still runs (Section 4: JSON-repair/parsing fallback).
        if not segments and regions:
            logger.warning("Segmentasyon ciktisi bos/bozuk; tek 'other' segmente dusuluyor")
            pages = sorted({r.page_number for r in regions})
            segments.append(
                DocumentSegment(
                    doc_type="other",
                    page_range=[pages[0], pages[-1]] if pages else [],
                    metadata={},
                    content=[r.to_dict() for r in regions],
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
