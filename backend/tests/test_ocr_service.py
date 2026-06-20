"""OCR HTTP service contract (services/paddleocr_vl_service): OpenAI-compatible
request parsing, bearer auth, image extraction. The model is stubbed so no
weights load — only the service wire contract is tested."""

import base64
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    import services.paddleocr_vl_service.app as svc

    monkeypatch.setattr(svc._provider, "recognize", lambda b: ("STUB TEXT", None))
    return svc, TestClient(svc.app)


def _img_payload():
    data = base64.b64encode(b"PNGBYTES").decode()
    return {
        "model": "paddleocr-vl-16",
        "messages": [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
                {"type": "text", "text": "OCR:"},
            ]}
        ],
    }


def test_health(client):
    _, c = client
    assert c.get("/health").json()["status"] == "ok"


def test_chat_completions_openai_shape(client, monkeypatch):
    svc, c = client
    monkeypatch.delenv("OCR_SERVICE_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("OCR_BEARER_KEY", raising=False)
    r = c.post("/v1/chat/completions", json=_img_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "STUB TEXT"
    assert body["object"] == "chat.completion"


def test_auth_enforced(client, monkeypatch):
    svc, c = client
    monkeypatch.setenv("OCR_SERVICE_BEARER_TOKEN", "sekret")
    assert c.post("/v1/chat/completions", json=_img_payload()).status_code == 401
    ok = c.post("/v1/chat/completions", json=_img_payload(),
                headers={"Authorization": "Bearer sekret"})
    assert ok.status_code == 200


def test_missing_image_400(client):
    _, c = client
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400
