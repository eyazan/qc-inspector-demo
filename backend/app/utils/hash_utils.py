"""Content hashing for spec change detection (config-driven algorithm)."""

import hashlib
from pathlib import Path

from app.core.config import settings

_CHUNK = 1 << 20  # 1 MiB


def file_hash(path: Path, algorithm: str | None = None) -> str:
    algo = (algorithm or settings.spec_hash_algorithm or "sha256").lower()
    digest = hashlib.new(algo)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_hash(text: str, algorithm: str | None = None) -> str:
    algo = (algorithm or settings.spec_hash_algorithm or "sha256").lower()
    return hashlib.new(algo, (text or "").encode("utf-8")).hexdigest()
