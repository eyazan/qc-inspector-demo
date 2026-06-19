from app.core.config import settings
from app.core.logging import get_logger
from app.prompts import prompts
from app.providers.factory import get_llm_provider
from app.services.ocr.models import DocumentSegment

logger = get_logger(__name__)


class ComparisonService:
    def __init__(self):
        self._llm = get_llm_provider(settings.comparison_timeout_seconds)

    def compare(self, segment: DocumentSegment, specification: str) -> str:
        user_prompt = prompts.build_comparison_user(segment.to_dict(), specification)
        return self._llm.complete(prompts.segment_comparison_system, user_prompt)
