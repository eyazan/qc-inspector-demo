"""Remote OCR engine wire contract: OpenAI-compatible request/parse, auth header,
batch concurrency, per-region failure isolation. Model is NOT loaded — only the
HTTP path is exercised via MockTransport."""

import base64

import httpx

import app.services.clients.http as http_mod
from app.services.ocr.ocr_engine import OcrEngine, _auth_headers


def _mock(handler):
    def _factory(timeout_seconds):
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout_seconds)
    return _factory


def test_recognize_parses_openai_response(monkeypatch):
    http_mod._breakers.clear()
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "AMS4911 Rev T"}}]
        })

    monkeypatch.setattr(http_mod, "build_client", _mock(handler))
    monkeypatch.setattr(http_mod.settings, "ocr_bearer_key", "tok", raising=False)
    monkeypatch.setattr("app.services.ocr.ocr_engine.settings.ocr_bearer_key", "tok", raising=False)

    text, conf = OcrEngine().recognize(b"PNGDATA")
    assert text == "AMS4911 Rev T"
    assert seen["auth"] == "Bearer tok"


def test_recognize_batch_isolates_failures(monkeypatch):
    http_mod._breakers.clear()

    def handler(request):
        body = request.content.decode()
        # Fail only the region whose base64 decodes to b"BAD".
        if base64.b64encode(b"BAD").decode() in body:
            return httpx.Response(500)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(http_mod, "build_client", _mock(handler))
    monkeypatch.setattr(http_mod.settings, "retry_backoff_seconds", 0.0, raising=False)
    monkeypatch.setattr(http_mod.settings, "retry_count", 0, raising=False)

    results = OcrEngine().recognize_batch([b"GOOD1", b"BAD", b"GOOD2"])
    assert results[0] == ("ok", None)
    assert results[1] == ("", None)   # failed region degrades, does not crash
    assert results[2] == ("ok", None)


def test_auth_scheme_basic(monkeypatch):
    monkeypatch.setattr("app.services.ocr.ocr_engine.settings.ocr_auth_scheme", "basic", raising=False)
    monkeypatch.setattr("app.services.ocr.ocr_engine.settings.ocr_basic_user", "u", raising=False)
    monkeypatch.setattr("app.services.ocr.ocr_engine.settings.ocr_basic_password", "p", raising=False)
    h = _auth_headers()
    assert h["Authorization"].startswith("Basic ")
