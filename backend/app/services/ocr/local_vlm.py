"""
Lokal PaddleOCR-VL yukleyici (transformers, in-process).

README resmi inference ornegine birebir uyumlu:
  - AutoModelForImageTextToText + AutoProcessor
  - task -> prompt: ocr/table/formula/chart/spotting/seal
  - messages -> apply_chat_template -> generate -> decode

Model BIR KEZ yuklenir (singleton + Lock). CPU'da float32, GPU'da bfloat16.
Generate CPU'da yavastir; demo icin yeterli, servise gecince hizlanir.
"""

import threading

from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# task -> prompt (README PROMPTS ile birebir)
TASK_PROMPTS = {
    "ocr": "OCR:",
    "table": "Table Recognition:",
    "formula": "Formula Recognition:",
    "chart": "Chart Recognition:",
    "spotting": "Spotting:",
    "seal": "OCR:",
}

_model = None
_processor = None
_load_failed = False
_lock = threading.Lock()
_patched = False


def _patch_create_causal_mask() -> None:
    """
    Uyumluluk yamasi: PaddleOCR-VL'in modeling kodu create_causal_mask'i
    'inputs_embeds=' (s'li) kwarg ile cagiriyor, ama yuklu transformers
    (4.55.0) bu fonksiyonu 'input_embeds' (s'siz) parametresiyle tanimliyor.
    Tek harf farki -> 'unexpected keyword argument inputs_embeds' hatasi.

    Bu yama, fonksiyonu sararak 'inputs_embeds' kwarg'ini 'input_embeds'e
    cevirir. Model dosyasina DOKUNMADAN sorunu cozer.
    """
    global _patched
    if _patched:
        return
    import inspect

    from transformers import masking_utils

    orig = masking_utils.create_causal_mask
    params = inspect.signature(orig).parameters
    # Fonksiyon zaten 'inputs_embeds' kabul ediyorsa yamaya gerek yok
    if "inputs_embeds" in params:
        _patched = True
        return

    def _wrapper(*args, **kwargs):
        if "inputs_embeds" in kwargs and "input_embeds" not in kwargs:
            kwargs["input_embeds"] = kwargs.pop("inputs_embeds")
        return orig(*args, **kwargs)

    # Hem masking_utils hem de modeling modulunun import ettigi referansi guncelle
    masking_utils.create_causal_mask = _wrapper
    _patched = True
    logger.info("create_causal_mask uyumluluk yamasi uygulandi (inputs_embeds->input_embeds)")


def _patch_model_module_mask(model) -> None:
    """
    Model modulu 'from transformers.masking_utils import create_causal_mask' ile
    fonksiyonu kendi namespace'ine almis olabilir. O referansi da sarmalanmis
    versiyonla degistir (model modulu zaten import edilmisse garanti icin).
    """
    import sys
    import inspect

    mod = sys.modules.get(type(model).__module__)
    if mod is None:
        return
    fn = getattr(mod, "create_causal_mask", None)
    if fn is None:
        return
    if "inputs_embeds" in inspect.signature(fn).parameters:
        return  # zaten uyumlu

    def _wrapper(*args, **kwargs):
        if "inputs_embeds" in kwargs and "input_embeds" not in kwargs:
            kwargs["input_embeds"] = kwargs.pop("inputs_embeds")
        return fn(*args, **kwargs)

    mod.create_causal_mask = _wrapper
    logger.info("Model modulu create_causal_mask referansi da yamalandi")



def _load():
    """Modeli tek sefer yukle (double-checked locking)."""
    global _model, _processor, _load_failed
    if _model is not None and _processor is not None:
        return _model, _processor
    if _load_failed:
        # Daha once yukleme basarisiz oldu; her region'da tekrar deneme.
        raise RuntimeError("PaddleOCR-VL daha once yuklenemedi (tekrar denenmiyor)")
    with _lock:
        if _model is not None and _processor is not None:
            return _model, _processor
        if _load_failed:
            raise RuntimeError("PaddleOCR-VL daha once yuklenemedi")

        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        # PaddleOCR-VL modeling kodu yuklenmeden ONCE create_causal_mask yamasi.
        # (Model modulu import edilince fonksiyonu kendine alir; yama once gelmeli.)
        _patch_create_causal_mask()

        model_dir = settings.ocr_local_model_dir
        device = settings.ocr_local_device
        dtype_str = settings.ocr_local_dtype
        dtype = getattr(torch, dtype_str, torch.float32)

        logger.info("PaddleOCR-VL yukleniyor: %s (device=%s, dtype=%s)",
                    model_dir, device, dtype_str)

        try:
            processor = AutoProcessor.from_pretrained(
                model_dir, trust_remote_code=True, use_fast=False
            )
            # PaddleOCR-VL ozel bir model sinifi (PaddleOCRVLForConditionalGeneration);
            # AutoModelForImageTextToText tanimaz -> AutoModelForCausalLM + trust_remote_code.
            #
            # ONEMLI: device_map="cuda" (string) modeli duzgun GPU'ya koymayabilir
            # (accelerate dagitim parametresi; bazi katmanlar CPU'da kalabilir).
            # Bunun yerine modeli CPU'da yukleyip ACIKCA .to(device) ile tasiyoruz.
            model = AutoModelForCausalLM.from_pretrained(
                model_dir, trust_remote_code=True, torch_dtype=dtype
            )
            if device and device != "cpu":
                if device == "cuda" and not torch.cuda.is_available():
                    logger.warning("OCR_LOCAL_DEVICE=cuda ama torch.cuda.is_available()=False; CPU'ya dusuluyor")
                    device = "cpu"
                else:
                    model = model.to(device)
                    logger.info("Model %s cihazina tasindi", device)
            model = model.eval()
            # Modelin gercekten hangi cihazda oldugunu DOGRULA ve logla
            try:
                first_param_device = next(model.parameters()).device
                logger.info("PaddleOCR-VL parametre cihazi (DOGRULAMA): %s", first_param_device)
            except StopIteration:
                pass
            # Model modulu create_causal_mask'i kendi namespace'ine import etmis
            # olabilir; oradaki referansi da sarmalanmis versiyona cevir (garanti).
            _patch_model_module_mask(model)
        except Exception:
            _load_failed = True
            raise

        _model = model
        _processor = processor
        logger.info("PaddleOCR-VL yuklendi: %s", model.__class__.__name__)
        return _model, _processor


def recognize_image(image: Image.Image, task: str = "ocr") -> str:
    """Bir PIL Image'i verilen gorev icin metne cevirir (senkron, in-process)."""
    import torch

    model, processor = _load()
    prompt = TASK_PROMPTS.get(task, TASK_PROMPTS["ocr"])

    if image.mode != "RGB":
        image = image.convert("RGB")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    # max_pixels: cok buyuk region'larda bellek/yavaslik onlemek icin sinir
    try:
        min_pixels = processor.image_processor.min_pixels
    except Exception:  # noqa: BLE001
        min_pixels = None

    chat_kwargs = dict(
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    if min_pixels is not None:
        # longest_edge: cok buyuk region'larda CPU'da asiri yavaslamayi onle
        chat_kwargs["images_kwargs"] = {
            "size": {"shortest_edge": min_pixels, "longest_edge": 2048 * 28 * 28}
        }

    # inputs'u MODELIN GERCEK cihazina gonder (settings degil — model nerede olduysa
    # input da orada olmali; aksi halde device mismatch ya da sessiz CPU yavaslama).
    try:
        target_device = next(model.parameters()).device
    except StopIteration:
        target_device = settings.ocr_local_device or "cpu"
    inputs = processor.apply_chat_template(messages, **chat_kwargs).to(target_device)

    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=settings.ocr_local_max_new_tokens)

    # Sadece uretilen kismi al (input uzunlugundan sonrasi)
    gen = outputs[0][inputs["input_ids"].shape[-1]:]
    text = processor.decode(gen, skip_special_tokens=True)
    return text.strip()
