"""Download PP-DocLayoutV3 from Hugging Face into LAYOUT_MODEL_DIR (config-driven).

Repo id, target dir and HF cache all come from config/.env — nothing machine
specific is hardcoded. PaddleOCR-VL is REMOTE and is intentionally NOT pulled.

    python scripts/download_models.py
    python scripts/download_models.py --repo PaddlePaddle/PP-DocLayoutV3_safetensors
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402


def _download(repo: str, target_dir: str, cache_dir: str | None) -> None:
    from huggingface_hub import snapshot_download

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {repo} -> {target} (cache={cache_dir or 'default'})")
    path = snapshot_download(repo_id=repo, local_dir=str(target), cache_dir=cache_dir)
    print(f"Done: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download models from Hugging Face.")
    parser.add_argument("--repo", default=settings.layout_model_hf_repo, help="Layout HF repo id")
    parser.add_argument("--dir", default=settings.layout_model_dir, help="Layout target dir")
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Also download the LOCAL PaddleOCR-VL model (optional; remote OCR needs no download)",
    )
    parser.add_argument("--ocr-only", action="store_true", help="Download only the local OCR model")
    args = parser.parse_args()

    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print("huggingface_hub not installed. pip install -r requirements.txt", file=sys.stderr)
        return 1

    cache_dir = str(settings.hf_cache_dir) if settings.hf_cache_dir else None

    if not args.ocr_only:
        _download(args.repo, args.dir, cache_dir)

    if args.ocr or args.ocr_only:
        _download(settings.ocr_local_model_hf_repo, settings.ocr_local_model_dir, cache_dir)
    else:
        print("Note: PaddleOCR-VL is remote-only by default. Use --ocr for the LOCAL provider.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
