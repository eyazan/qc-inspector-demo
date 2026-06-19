"""LLM provider interface.

Same contract whether the backend is remote Qwen-on-vLLM (OpenAI-compatible) or
a mock. Selected via ACTIVE_LLM_PROVIDER.
"""

from abc import ABC, abstractmethod


class LlmProvider(ABC):
    name: str = "base"
    is_mock: bool = False

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model completion text for the given system/user prompts."""
        raise NotImplementedError
