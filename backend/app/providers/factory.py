"""Provider factory — selects implementations from config only.

Swapping a model/provider is an .env change (ACTIVE_*_PROVIDER), never a code
edit. RUN_MODE=mock forces every provider to its mock so the full pipeline can
be smoke-tested offline (no GPU host, no SAP, no vLLM).
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.layout.base import LayoutProvider
from app.providers.llm.base import LlmProvider
from app.providers.ocr.base import OcrProvider

logger = get_logger(__name__)


def _mock_forced() -> bool:
    return (settings.run_mode or "real").lower() == "mock"


def get_layout_provider() -> LayoutProvider:
    provider = "mock" if _mock_forced() else settings.active_layout_provider
    if provider == "mock":
        from app.providers.layout.mock_provider import MockLayoutProvider

        return MockLayoutProvider()
    from app.providers.layout.paddlex_doclayout_provider import (
        PaddlexDocLayoutProvider,
    )

    return PaddlexDocLayoutProvider()


def get_ocr_provider() -> OcrProvider:
    provider = "mock" if _mock_forced() else settings.active_ocr_provider
    if provider == "mock":
        from app.providers.ocr.mock_provider import MockOcrProvider

        return MockOcrProvider()
    from app.providers.ocr.paddleocr_vl_provider import PaddleOcrVlProvider

    return PaddleOcrVlProvider()


def get_llm_provider(timeout_seconds: int) -> LlmProvider:
    provider = "mock" if _mock_forced() else settings.active_llm_provider
    if provider == "mock":
        from app.providers.llm.mock_provider import MockLlmProvider

        return MockLlmProvider()
    from app.providers.llm.openai_compatible_provider import (
        OpenAiCompatibleLlmProvider,
    )

    return OpenAiCompatibleLlmProvider(timeout_seconds)
