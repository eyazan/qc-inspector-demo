"""LLM provider interface.

Any OpenAI-compatible endpoint (Qwen-on-vLLM, Ollama, Gemini). Selected via
ACTIVE_LLM_PROVIDER.
"""

from abc import ABC, abstractmethod


class LlmProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model completion text for the given system/user prompts."""
        raise NotImplementedError
