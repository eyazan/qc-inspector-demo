"""Local PaddleOCR-VL provider — in-process via transformers (OPTIONAL).

Production topology keeps OCR remote (paddleocr_vl). This provider is for local
testing on a machine with enough disk/RAM, selected via
ACTIVE_OCR_PROVIDER=paddleocr_vl_local. All paths/devices come from config
(ocr_local_*). Heavy deps (torch/transformers) are imported lazily so the module
loads even when they are absent; a clear error is raised only if actually used.

Weights: scripts/download_models.py --ocr (pulls OCR_LOCAL_MODEL_HF_REPO into
OCR_LOCAL_MODEL_DIR). Same OCR provider interface as the remote one.
"""

import io
import threading

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.ocr.base import OcrProvider

logger = get_logger(__name__)

_TASK_PROMPT = "OCR:"


class PaddleOcrVlLocalProvider(OcrProvider):
    name = "paddleocr_vl_local"

    _model = None
    _processor = None
    _lock = threading.Lock()

    def recognize(self, region_image_png: bytes) -> tuple[str, float | None]:
        from PIL import Image

        model, processor = self._load()
        import torch

        image = Image.open(io.BytesIO(region_image_png)).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": _TASK_PROMPT},
                ],
            }
        ]
        try:
            target_device = next(model.parameters()).device
        except StopIteration:
            target_device = settings.ocr_local_device or "cpu"
        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(target_device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs, max_new_tokens=settings.ocr_local_max_new_tokens
            )
        gen = outputs[0][inputs["input_ids"].shape[-1]:]
        text = processor.decode(gen, skip_special_tokens=True)
        return text.strip(), None

    @classmethod
    def _load(cls):
        if cls._model is not None and cls._processor is not None:
            return cls._model, cls._processor
        with cls._lock:
            if cls._model is not None and cls._processor is not None:
                return cls._model, cls._processor
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoProcessor
            except ImportError as err:  # pragma: no cover
                raise RuntimeError(
                    "paddleocr_vl_local icin torch+transformers gerekli. "
                    "pip install -r requirements-ml.txt"
                ) from err

            model_dir = settings.ocr_local_model_dir
            device = settings.ocr_local_device
            dtype = getattr(torch, settings.ocr_local_dtype, torch.float32)
            logger.info("PaddleOCR-VL (lokal) yukleniyor: %s (device=%s)", model_dir, device)

            processor = AutoProcessor.from_pretrained(
                model_dir, trust_remote_code=True, use_fast=False
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_dir, trust_remote_code=True, torch_dtype=dtype
            )
            if device and device != "cpu" and not (
                device == "cuda" and not torch.cuda.is_available()
            ):
                model = model.to(device)
            cls._model = model.eval()
            cls._processor = processor
            logger.info("PaddleOCR-VL (lokal) hazir: %s", model.__class__.__name__)
            return cls._model, cls._processor
