import base64

from app.core.config import settings
from app.core.logging import get_logger
from app.services.clients.http import build_client

logger = get_logger(__name__)


def _auth_headers() -> dict:
    """Build OCR auth headers from config (discrepancy #1: scheme is config-driven)."""
    scheme = (settings.ocr_auth_scheme or "bearer").lower()
    if scheme == "basic" and settings.ocr_basic_user:
        token = base64.b64encode(
            f"{settings.ocr_basic_user}:{settings.ocr_basic_password}".encode("utf-8")
        ).decode("ascii")
        return {"Authorization": f"Basic {token}"}
    if settings.ocr_bearer_key:
        return {"Authorization": f"Bearer {settings.ocr_bearer_key}"}
    return {}


class OcrEngine:
    def __init__(self):
        self._endpoint = (
            settings.ocr_service_url.rstrip("/") + settings.ocr_recognize_path
        )
        self._timeout = settings.ocr_timeout_seconds

    def recognize(self, region_image_png: bytes) -> tuple[str, float | None]:
        encoded = base64.b64encode(region_image_png).decode("ascii")
        
        # PaddleOCR-VL OpenAI-compatible API format
        payload = {
            "model": settings.ocr_model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encoded}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "Extract all text from this image and return it. If no text, return empty string."
                        }
                    ]
                }
            ],
            "temperature": 0.0
        }
        
        headers = _auth_headers()

        with build_client(self._timeout) as client:
            response = client.post(self._endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        # Extract text from OpenAI-compatible response
        text = ""
        if "choices" in data and len(data["choices"]) > 0:
            text = data["choices"][0].get("message", {}).get("content", "")
        
        # Try to extract confidence if available
        confidence = None
        if "choices" in data and len(data["choices"]) > 0:
            choice = data["choices"][0]
            if "logprobs" in choice and choice["logprobs"]:
                # Average logprob as confidence approximation
                logprobs = choice["logprobs"].get("content", [])
                if logprobs:
                    confidence = sum(p["logprob"] for p in logprobs) / len(logprobs)

        return text, confidence
