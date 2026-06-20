"""Provider factory — selects implementations from config only (no mocks).

Swapping a model/provider is an .env change (ACTIVE_*_PROVIDER), never a code
edit. This PC: layout=paddlex_doclayout (local), ocr=paddleocr_vl_local (local).
Production PC: ocr=paddleocr_vl (remote). LLM is any OpenAI-compatible endpoint
(Ollama here; vLLM/Qwen or Gemini elsewhere).
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.layout.base import LayoutProvider
from app.providers.llm.base import LlmProvider
from app.providers.ocr.base import OcrProvider
from app.providers.spec_store.base import SpecStore

logger = get_logger(__name__)


def get_layout_provider() -> LayoutProvider:
    from app.providers.layout.paddlex_doclayout_provider import (
        PaddlexDocLayoutProvider,
    )

    if settings.active_layout_provider != "paddlex_doclayout":
        logger.warning(
            "Bilinmeyen layout provider '%s'; paddlex_doclayout kullaniliyor",
            settings.active_layout_provider,
        )
    return PaddlexDocLayoutProvider()


def get_ocr_provider() -> OcrProvider:
    provider = settings.active_ocr_provider
    if provider == "paddleocr_vl_local":
        from app.providers.ocr.paddleocr_vl_local_provider import (
            PaddleOcrVlLocalProvider,
        )

        return PaddleOcrVlLocalProvider()
    from app.providers.ocr.paddleocr_vl_provider import PaddleOcrVlProvider

    if provider != "paddleocr_vl":
        logger.warning(
            "Bilinmeyen OCR provider '%s'; paddleocr_vl (uzak) kullaniliyor", provider
        )
    return PaddleOcrVlProvider()


def get_llm_provider(timeout_seconds: int) -> LlmProvider:
    from app.providers.llm.openai_compatible_provider import (
        OpenAiCompatibleLlmProvider,
    )

    if settings.active_llm_provider != "openai_compatible":
        logger.warning(
            "Bilinmeyen LLM provider '%s'; openai_compatible kullaniliyor",
            settings.active_llm_provider,
        )
    return OpenAiCompatibleLlmProvider(timeout_seconds)


def get_spec_store() -> SpecStore:
    backend = settings.active_spec_store or settings.spec_store_backend
    if backend == "postgres":
        from app.providers.spec_store.postgres_spec_store import PostgresSpecStore

        return PostgresSpecStore()
    from app.providers.spec_store.sqlite_spec_store import SqliteSpecStore

    return SqliteSpecStore()


def get_spec_lookup_strategy():
    """Section 3 lookup chain; only sap_then_local_store is implemented today."""
    from app.providers.spec_lookup.sap_then_local_lookup import SapThenLocalLookup

    strategy = settings.active_spec_lookup_strategy or "sap_then_local_store"
    if strategy != "sap_then_local_store":
        logger.warning(
            "Bilinmeyen spec lookup stratejisi '%s'; sap_then_local_store kullaniliyor",
            strategy,
        )
    return SapThenLocalLookup()
