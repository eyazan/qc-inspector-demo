from app.core.config import settings
from app.core.logging import get_logger
from app.services.clients.http import build_client

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
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

        with build_client(self._timeout_seconds) as client:
            response = client.post(self._endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]
