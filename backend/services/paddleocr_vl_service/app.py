"""PaddleOCR-VL OCR service — OpenAI-compatible /v1/chat/completions.

This is the REMOTE OCR service from the production topology. It runs on a GPU
host (Colab T4 for dev, H200 in prod), NOT inside the application backend. The
backend reaches it via OCR_SERVICE_URL + bearer token (ACTIVE_OCR_PROVIDER=
paddleocr_vl). Locally it can run on CPU for wiring tests, but the heavy
inference is meant for the GPU host.

Auth: Authorization: Bearer <OCR_SERVICE_BEARER_TOKEN> (if the env var is set).
Reuses the proven model loader in app.providers.ocr.paddleocr_vl_local_provider
(transformers 4.55 compat + correct image sizing).

Run:
    uvicorn services.paddleocr_vl_service.app:app --host 0.0.0.0 --port 8102
"""

import base64
import os
import re
import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.providers.ocr.paddleocr_vl_local_provider import PaddleOcrVlLocalProvider

app = FastAPI(title="PaddleOCR-VL Service", version="1.0.0")
_provider = PaddleOcrVlLocalProvider()
_DATA_URI = re.compile(r"^data:image/[^;]+;base64,(.*)$", re.DOTALL)


def _check_auth(authorization: str | None) -> None:
    expected = os.getenv("OCR_SERVICE_BEARER_TOKEN") or os.getenv("OCR_BEARER_KEY")
    if not expected:
        return  # auth disabled (dev)
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


def _extract_image_bytes(body: dict) -> bytes:
    for msg in body.get("messages", []):
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image_url":
                    url = (part.get("image_url") or {}).get("url", "")
                    m = _DATA_URI.match(url)
                    if m:
                        return base64.b64decode(m.group(1))
    raise HTTPException(status_code=400, detail="No base64 image_url found in messages")


class ChatBody(BaseModel):
    model: str | None = None
    messages: list
    temperature: float | None = 0.0


@app.get("/health")
def health():
    return {"status": "ok", "service": "paddleocr-vl"}


@app.get("/health/ready")
def ready():
    # Touch the model lazily; report whether weights load.
    try:
        PaddleOcrVlLocalProvider._load()
        return {"status": "ready"}
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"model not ready: {err}")


@app.post("/v1/chat/completions")
def chat_completions(body: ChatBody, authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    image = _extract_image_bytes(body.model_dump())
    text, _conf = _provider.recognize(image)
    now = int(time.time())
    return {
        "id": f"ocr-{now}",
        "object": "chat.completion",
        "created": now,
        "model": body.model or "paddleocr-vl-16",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
    }
