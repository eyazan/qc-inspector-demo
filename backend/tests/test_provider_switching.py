"""Provider + config switching is configuration-only (no model loads at select).
Validates the factory honors ACTIVE_* and that production-name config aliases
resolve to the canonical fields."""

import importlib

import app.providers.factory as factory
from app.core.config import get_settings


def test_ocr_provider_switch(monkeypatch):
    monkeypatch.setattr(factory.settings, "active_ocr_provider", "paddleocr_vl", raising=False)
    assert factory.get_ocr_provider().name == "paddleocr_vl"
    monkeypatch.setattr(factory.settings, "active_ocr_provider", "paddleocr_vl_local", raising=False)
    assert factory.get_ocr_provider().name == "paddleocr_vl_local"


def test_llm_provider_switch(monkeypatch):
    monkeypatch.setattr(factory.settings, "active_llm_provider", "openai_compatible", raising=False)
    assert factory.get_llm_provider(60).name == "openai_compatible"


def test_layout_provider_switch():
    # Selecting does not load the model (LayoutDetector loads lazily on detect()).
    assert factory.get_layout_provider().name == "paddlex_doclayout"


def test_spec_store_switch(monkeypatch):
    monkeypatch.setattr(factory.settings, "active_spec_store", "sqlite", raising=False)
    assert factory.get_spec_store().name == "sqlite"


def test_config_aliases(monkeypatch):
    # New production names map onto the canonical fields.
    monkeypatch.setenv("OCR_SERVICE_BEARER_TOKEN", "secret-tok")
    monkeypatch.setenv("LLM_SERVICE_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
    monkeypatch.setenv("MAX_CONCURRENCY", "9")
    get_settings.cache_clear()
    s = get_settings()
    assert s.ocr_bearer_key == "secret-tok"
    assert s.llm_base_url == "https://llm.example/v1"
    assert s.llm_model == "Qwen/Qwen2.5-3B-Instruct"
    assert s.ocr_max_concurrency == 9
    get_settings.cache_clear()
