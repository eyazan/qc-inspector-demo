"""Self-contained PaddleOCR-VL 1.6 server (OpenAI-compatible) for Google Colab
or any GPU host. No repo dependency — only pip packages + the HF model.

Exposes POST /v1/chat/completions (image_url data URI + text) and GET /health.
Auth: Authorization: Bearer <OCR_SERVICE_BEARER_TOKEN> when that env var is set.

Colab usage (T4/A100 GPU runtime):
    !pip install -q "transformers==4.55.0" torch torchvision accelerate einops \
        sentencepiece pillow fastapi "uvicorn[standard]" huggingface_hub
    import os
    os.environ["OCR_LOCAL_MODEL_DIR"] = "PaddlePaddle/PaddleOCR-VL-1.6"  # HF id ok
    os.environ["OCR_LOCAL_DEVICE"] = "cuda"
    os.environ["OCR_LOCAL_DTYPE"] = "bfloat16"
    os.environ["OCR_SERVICE_BEARER_TOKEN"] = "dev-ocr-token"
    # then run this file; expose with cloudflared (see colab/README.md)
"""

import base64
import io
import os
import re
import threading
import time

import torch
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from PIL import Image
from pydantic import BaseModel

MODEL_DIR = os.getenv("OCR_LOCAL_MODEL_DIR", "PaddlePaddle/PaddleOCR-VL-1.6")
DEVICE = os.getenv("OCR_LOCAL_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
DTYPE = getattr(torch, os.getenv("OCR_LOCAL_DTYPE", "bfloat16"), torch.float32)
MAX_NEW_TOKENS = int(os.getenv("OCR_LOCAL_MAX_NEW_TOKENS", "2048"))
MAX_PIXELS = int(os.getenv("OCR_LOCAL_MAX_PIXELS", str(1280 * 28 * 28)))
TOKEN = os.getenv("OCR_SERVICE_BEARER_TOKEN") or os.getenv("OCR_BEARER_KEY")

_model = None
_processor = None
_lock = threading.Lock()
_DATA_URI = re.compile(r"^data:image/[^;]+;base64,(.*)$", re.DOTALL)


def _patch_causal_mask():
    import inspect

    from transformers import masking_utils

    orig = masking_utils.create_causal_mask
    if "inputs_embeds" in inspect.signature(orig).parameters:
        return

    def _w(*a, **k):
        if "inputs_embeds" in k and "input_embeds" not in k:
            k["input_embeds"] = k.pop("inputs_embeds")
        return orig(*a, **k)

    masking_utils.create_causal_mask = _w


def _load():
    global _model, _processor
    if _model is not None:
        return _model, _processor
    with _lock:
        if _model is not None:
            return _model, _processor
        from transformers import AutoModelForCausalLM, AutoProcessor

        _patch_causal_mask()
        proc = AutoProcessor.from_pretrained(MODEL_DIR, trust_remote_code=True, use_fast=False)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_DIR, trust_remote_code=True, torch_dtype=DTYPE
        )
        if DEVICE != "cpu":
            model = model.to(DEVICE)
        _model, _processor = model.eval(), proc
        return _model, _processor


def _ocr(image: Image.Image) -> str:
    model, proc = _load()
    messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": "OCR:"}]}]
    try:
        min_pixels = proc.image_processor.min_pixels
    except Exception:  # noqa: BLE001
        min_pixels = None
    kwargs = dict(add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
    if min_pixels is not None:
        kwargs["images_kwargs"] = {"size": {"shortest_edge": min_pixels, "longest_edge": MAX_PIXELS}}
    inputs = proc.apply_chat_template(messages, **kwargs).to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
    return proc.decode(out[0][inputs["input_ids"].shape[-1]:-1]).strip()


app = FastAPI(title="PaddleOCR-VL Colab Server")


class ChatBody(BaseModel):
    model: str | None = None
    messages: list
    temperature: float | None = 0.0


@app.get("/health")
def health():
    return {"status": "ok", "device": DEVICE}


@app.post("/v1/chat/completions")
def chat(body: ChatBody, authorization: str | None = Header(default=None)):
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="bad token")
    data = body.model_dump()
    img_bytes = None
    for m in data.get("messages", []):
        if isinstance(m.get("content"), list):
            for part in m["content"]:
                if part.get("type") == "image_url":
                    mt = _DATA_URI.match((part.get("image_url") or {}).get("url", ""))
                    if mt:
                        img_bytes = base64.b64decode(mt.group(1))
    if img_bytes is None:
        raise HTTPException(status_code=400, detail="no image")
    text = _ocr(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
    now = int(time.time())
    return {
        "id": f"ocr-{now}", "object": "chat.completion", "created": now,
        "model": body.model or "paddleocr-vl-16",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8102")))
