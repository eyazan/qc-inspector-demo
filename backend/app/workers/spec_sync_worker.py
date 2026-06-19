"""
Spec Sync Worker — periyodik spec dizini tarama + OCR.

Belirli araliklarla data/specs dizinini tarar, yeni/guncellenmis spec
PDF'lerini OCR'dan gecirip parse eder ve onbellege (DB) yazar. Boylece
vendor upload geldiginde spec zaten hazirdir.

Not: Bu basit threading tabanli zamanlayici. Production'da APScheduler
veya harici cron + endpoint tercih edilebilir.
"""

import threading
import time

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def start_spec_sync_worker() -> None:
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()


def _loop() -> None:
    interval = settings.spec_sync_interval_seconds
    while True:
        try:
            _sync_once()
        except Exception as error:  # noqa: BLE001
            logger.error("Spec sync hatasi: %s", error)
        time.sleep(interval)


def _sync_once() -> None:
    """
    data/specs altindaki spec dosyalarini tarar.
    (Iskelet: gercek OCR + parse cagrisi entegrasyon noktasi.)
    """
    spec_dir = settings.spec_source_dir
    if not spec_dir.exists():
        return
    spec_files = list(spec_dir.glob("*.pdf")) + list(spec_dir.glob("*.md"))
    logger.info("Spec sync: %s spec dosyasi tarandi", len(spec_files))
    # Gercek OCR/parse entegrasyonu pipeline_service ile ortak kullanilabilir.