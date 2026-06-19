from app.core.config import settings
from app.core.logging import get_logger
from app.prompts import prompts
from app.services.clients.llm_client import LlmClient

logger = get_logger(__name__)


class AggregationService:
    def __init__(self):
        self._llm = LlmClient(settings.aggregation_timeout_seconds)

    def aggregate(self, segment_reports: list[dict]) -> str:
        user_prompt = prompts.build_aggregation_user(segment_reports)
        return self._llm.complete(prompts.final_aggregation_system, user_prompt)
