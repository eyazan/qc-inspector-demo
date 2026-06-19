"""
Pipeline durum yonetimi.

Orijinal PipelineState SINIFI AYNEN korundu (davranis ayni). Tek ekleme:
artik birden cok run ayni anda izlenebilsin diye run_id bazli bir registry var.
Frontend status'u /api/processing-status/{run_id} ile run_id bazli sorgu yapiyor.

- pipeline_state  : orijinal global instance (geriye uyumluluk; tekil akislar icin)
- get_run_state(run_id) : o run'a ait PipelineState (yoksa olusturur)
- registry, iki asamali akista (upload + comparison) ayni run_id'yi paylasir.
"""

import threading
from datetime import datetime
from typing import Optional


class PipelineState:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._reset_unlocked()
        # status alani: awaiting_comparison / completed / failed / processing
        self.status: str = "idle"

    def _reset_unlocked(self) -> None:
        self.is_processing = False
        self.current_step = ""
        self.progress = 0
        self.logs: list[str] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.run_id: Optional[str] = None
        self.status = "idle"

    def begin(self, run_id: Optional[str] = None) -> None:
        with self._lock:
            self._reset_unlocked()
            self._cancel_event.clear()
            self.is_processing = True
            self.start_time = datetime.now()
            self.run_id = run_id
            self.status = "processing"
            self.current_step = "Islem baslatildi"
            self.logs.append("Islem baslatildi")

    def update(self, step: str, progress: int) -> None:
        with self._lock:
            self.current_step = step
            self.progress = progress
            self.logs.append(step)

    def log(self, message: str) -> None:
        with self._lock:
            self.logs.append(message)

    def finish(self, run_id: Optional[str], message: str, status: str = "completed") -> None:
        with self._lock:
            self.is_processing = False
            self.progress = 100
            self.current_step = message
            self.run_id = run_id
            self.status = status
            self.end_time = datetime.now()
            self.logs.append(message)

    def pause_for_comparison(self, run_id: Optional[str], message: str) -> None:
        """Asama 1 (yukleme) bitti; karsilastirma bekleniyor. is_processing=False
        ama status=awaiting_comparison (frontend onizleme ekranina gecer)."""
        with self._lock:
            self.is_processing = False
            self.progress = 100
            self.current_step = message
            self.run_id = run_id
            self.status = "awaiting_comparison"
            self.end_time = datetime.now()
            self.logs.append(message)

    def resume(self, message: str = "Karsilastirma baslatildi") -> None:
        """Asama 2 (karsilastirma) basliyor; ayni run yeniden islemeye gecer."""
        with self._lock:
            self._cancel_event.clear()
            self.is_processing = True
            self.status = "processing"
            self.end_time = None
            self.current_step = message
            self.logs.append(message)

    def fail(self, message: str) -> None:
        with self._lock:
            self.is_processing = False
            self.status = "failed"
            self.current_step = message
            self.end_time = datetime.now()
            self.logs.append(message)

    def request_cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            self.is_processing = False
            self.status = "failed"
            self.current_step = "Islem iptal edildi"
            self.end_time = datetime.now()
            self.logs.append("Islem iptal edildi")

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def snapshot(self) -> dict:
        with self._lock:
            elapsed = 0
            if self.start_time is not None:
                reference = self.end_time or datetime.now()
                elapsed = int((reference - self.start_time).total_seconds())
            return {
                "is_processing": self.is_processing,
                "current_step": self.current_step,
                "progress": self.progress,
                "logs": list(self.logs),
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "end_time": self.end_time.isoformat() if self.end_time else None,
                "elapsed_seconds": elapsed,
                "run_id": self.run_id,
                "status": self.status,
            }


# Orijinal global instance (geriye uyumluluk icin korundu)
pipeline_state = PipelineState()


# --- run_id bazli registry ---
_registry: dict[str, PipelineState] = {}
_registry_lock = threading.Lock()


def get_run_state(run_id: str) -> PipelineState:
    """run_id'ye ait PipelineState'i dondur; yoksa olustur."""
    with _registry_lock:
        state = _registry.get(run_id)
        if state is None:
            state = PipelineState()
            state.run_id = run_id
            _registry[run_id] = state
        return state


def drop_run_state(run_id: str) -> None:
    with _registry_lock:
        _registry.pop(run_id, None)
