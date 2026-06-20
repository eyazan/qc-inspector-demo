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


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the layout model from Hugging Face.")
    parser.add_argument("--repo", default=settings.layout_model_hf_repo, help="HF repo id")
    parser.add_argument("--dir", default=settings.layout_model_dir, help="Local target dir")
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub not installed. pip install -r requirements.txt", file=sys.stderr)
        return 1

    target = Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)
    cache_dir = str(settings.hf_cache_dir) if settings.hf_cache_dir else None

    print(f"Downloading {args.repo} -> {target} (cache={cache_dir or 'default'})")
    path = snapshot_download(repo_id=args.repo, local_dir=str(target), cache_dir=cache_dir)
    print(f"Done: {path}")
    print("Note: PaddleOCR-VL is remote-only (OCR_SERVICE_URL); not downloaded here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
