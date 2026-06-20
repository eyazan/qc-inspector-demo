"""Remote OCR client (PaddleOCR-VL, OpenAI-compatible chat/completions).

Production hardening lives in clients/http.post_json (retries, backoff, circuit
breaker, timeout, token-safe logging). recognize_batch runs a page's region
crops concurrently (OCR_BATCH_SIZE / OCR_MAX_CONCURRENCY).
"""

import base64
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.core.logging import get_logger
from app.services.clients.http import RemoteServiceError, post_json

logger = get_logger(__name__)

_OCR_INSTRUCTION = "OCR: extract all text from this image. If there is no text, return an empty string."


def _auth_headers() -> dict:
    """OCR auth headers from config (scheme is config-driven: bearer | basic)."""
    scheme = (settings.ocr_auth_scheme or "bearer").lower()
    if scheme == "basic" and settings.ocr_basic_user:
        token = base64.b64encode(
            f"{settings.ocr_basic_user}:{settings.ocr_basic_password}".encode("utf-8")
        ).decode("ascii")
        return {"Authorization": f"Basic {token}"}
    if settings.ocr_bearer_key:
        return {"Authorization": f"Bearer {settings.ocr_bearer_key}"}
    return {}


def _parse_response(data: dict) -> tuple[str, float | None]:
    text = ""
    confidence = None
    choices = data.get("choices") or []
    if choices:
        text = choices[0].get("message", {}).get("content", "") or ""
        logprobs = (choices[0].get("logprobs") or {}).get("content") or []
        if logprobs:
            confidence = sum(p.get("logprob", 0.0) for p in logprobs) / len(logprobs)
    return text, confidence


class OcrEngine:
    def __init__(self):
        self._endpoint = settings.ocr_service_url.rstrip("/") + settings.ocr_recognize_path
        self._timeout = settings.ocr_timeout_seconds

    def _payload(self, region_image_png: bytes) -> dict:
        encoded = base64.b64encode(region_image_png).decode("ascii")
        return {
            "model": settings.ocr_model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                        {"type": "text", "text": _OCR_INSTRUCTION},
                    ],
                }
            ],
            "temperature": 0.0,
        }

    def recognize(self, region_image_png: bytes) -> tuple[str, float | None]:
        data = post_json(
            self._endpoint,
            self._payload(region_image_png),
            headers=_auth_headers(),
            timeout_seconds=self._timeout,
        )
        return _parse_response(data)

    def recognize_batch(self, images: list[bytes]) -> list[tuple[str, float | None]]:
        """Recognize many region crops concurrently. Failures degrade to ('', None)
        per region so one bad region never sinks the whole page."""
        if not images:
            return []
        workers = max(1, min(settings.ocr_max_concurrency, settings.ocr_batch_size, len(images)))

        def _one(img: bytes) -> tuple[str, float | None]:
            try:
                return self.recognize(img)
            except RemoteServiceError as err:
                logger.error("OCR region failed after retries: %s", err)
                return "", None

        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(_one, images))
