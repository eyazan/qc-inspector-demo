"""Remote LLM client (OpenAI-compatible chat/completions).

Works with any OpenAI-compatible endpoint (vLLM/Qwen, Together, Fireworks,
OpenRouter, Gemini-OpenAI). Hardening (retries/backoff/circuit-breaker/timeout/
token-safe logging) lives in clients/http.post_json.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.services.clients.http import post_json

logger = get_logger(__name__)


class LlmClient:
    def __init__(self, timeout_seconds: int):
        self._timeout_seconds = timeout_seconds
        self._endpoint = settings.llm_base_url.rstrip("/") + "/chat/completions"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        suffix = settings.llm_no_think_suffix
        content = user_prompt + suffix if suffix else user_prompt

        payload = {
            "model": settings.llm_model,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        }
        headers = {}
        if settings.llm_api_key and settings.llm_api_key != "not-needed":
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        data = post_json(
            self._endpoint, payload, headers=headers, timeout_seconds=self._timeout_seconds
        )
        return data["choices"][0]["message"]["content"]
