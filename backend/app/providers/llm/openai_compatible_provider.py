"""OpenAI-compatible LLM provider — REMOTE Qwen on vLLM.

Delegates to the existing LlmClient (chat/completions). Timeout is per-call so
segmentation/comparison/aggregation keep their distinct budgets.
"""

from app.providers.llm.base import LlmProvider
from app.services.clients.llm_client import LlmClient


class OpenAiCompatibleLlmProvider(LlmProvider):
    name = "openai_compatible"

    def __init__(self, timeout_seconds: int):
        self._client = LlmClient(timeout_seconds)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self._client.complete(system_prompt, user_prompt)
