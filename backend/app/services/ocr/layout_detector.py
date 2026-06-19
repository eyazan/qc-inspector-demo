"""
Layout Detector — DocLayout (PP-DocLayoutV3) bu makinede LOKAL calisir.

Orijinal yapi korundu: senkron `detect(page_image_png, page_number) -> list[LayoutRegion]`
imzasi AYNEN ayni; sadece icerik uzak HTTP yerine lokal paddlex predict.
Boylece ocr_pipeline.py hic degismeden calisir.

Model bir kez yuklenir (modul-seviyesi cache). paddlex modeli thread-affinite
oldugundan, tek-worker'li bir executor ile predict'ler hep ayni thread'de
calistirilir (farkli thread 'EagerParamBase' hatasi verir).
"""

import io
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr.models import LayoutRegion

logger = get_logger(__name__)

# Lokal paddlex modeli icin modul-seviyesi cache (tek yukleme)
_local_model = None
_local_model_lock = threading.Lock()

# paddlex modeli THREAD-AFFINITE: ayni thread'de olusturulup cagrilmali.
# Tek-worker executor -> tum predict'ler HEP ayni thread'de calisir.
_paddle_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paddle")


def _get_local_model():
    """PP-DocLayoutV3'u paddlex ile bir kez yukle, sonra cache'den dondur."""
    global _local_model
    if _local_model is None:
        with _local_model_lock:
            if _local_model is None:  # double-checked locking
                from paddlex import create_model

                logger.info(
                    "DocLayout lokal model yukleniyor: %s", settings.layout_model_dir
                )
                # Dusuk esigi model olustururken de vermeyi dene: bazi paddlex
                # surumleri esigi create_model'de alir, bazilari predict'te.
                try:
                    _local_model = create_model(
                        model_name=settings.layout_model_name,
                        model_dir=settings.layout_model_dir,
                        threshold=settings.layout_score_threshold,
                    )
                except TypeError:
                    _local_model = create_model(
                        model_name=settings.layout_model_name,
                        model_dir=settings.layout_model_dir,
                    )
                logger.info("DocLayout lokal model hazir")
    return _local_model


def _predict_local(page_image_png: bytes):
    """PNG byte -> numpy array -> paddlex predict. Tek paddle thread'inde calisir."""
    model = _get_local_model()
    image = Image.open(io.BytesIO(page_image_png)).convert("RGB")
    array = np.array(image)  # H x W x 3 (RGB)

    # ONEMLI: dusuk threshold ver ki model BASTAN cok bolge uretsin. threshold
    # verilmezse model kendi varsayilan ic esigini (~0.5) kullanir, az bolge doner.
    threshold = settings.layout_score_threshold
    try:
        results = list(model.predict(array, threshold=threshold))
    except TypeError:
        # Bu paddlex surumu threshold parametresini predict'te kabul etmiyorsa
        # parametresiz cagir (esik create_model'de verilmis olabilir).
        results = list(model.predict(array))
    return results


def _result_to_boxes(results) -> list[dict]:
    """paddlex predict sonucundan kutu listesi cikar (surum-toleransli)."""
    boxes: list[dict] = []
    for res in results:
        # paddlex DetResult genelde dict-benzeri; 'boxes' anahtari altinda liste.
        data = None
        if isinstance(res, dict):
            data = res.get("boxes")
        if data is None:
            data = getattr(res, "boxes", None)
        if data is None and hasattr(res, "json"):
            try:
                data = res.json.get("boxes")
            except Exception:  # noqa: BLE001
                data = None
        if not data:
            continue
        for item in data:
            if isinstance(item, dict):
                coordinate = item.get("coordinate") or item.get("bbox")
                label = item.get("label") or item.get("category") or "paragraph"
                score = item.get("score")
            else:
                coordinate = getattr(item, "coordinate", None) or getattr(item, "bbox", None)
                label = getattr(item, "label", "paragraph")
                score = getattr(item, "score", None)
            if not coordinate:
                continue
            boxes.append(
                {"bbox": [float(c) for c in coordinate], "label": str(label), "score": score}
            )
    return boxes


class LayoutDetector:
    """DocLayout istemcisi — LOKAL paddlex (PP-DocLayoutV3)."""

    def __init__(self):
        # Orijinal alan korundu (uyumluluk); lokal modda kullanilmiyor.
        self._timeout = settings.layout_timeout_seconds

    def detect(self, page_image_png: bytes, page_number: int) -> list[LayoutRegion]:
        # paddlex predict'i HEP ayni paddle thread'inde calistir (thread-affinity).
        future = _paddle_executor.submit(_predict_local, page_image_png)
        results = future.result()
        raw_boxes = _result_to_boxes(results)

        regions: list[LayoutRegion] = []
        for index, item in enumerate(raw_boxes):
            regions.append(
                LayoutRegion(
                    region_id=f"page{page_number}_region{index}",
                    bbox=item["bbox"],
                    page_number=page_number,
                    region_type=item.get("label", "paragraph"),
                    score=item.get("score"),
                )
            )
        logger.info("Sayfa %s: %s bolge tespit edildi (lokal)", page_number, len(regions))
        return regions
