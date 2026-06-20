"""Spec indexing pipeline (2B) CLI — standalone, idempotent.

    python scripts/index_specs.py --mode full
    python scripts/index_specs.py --mode incremental
    python scripts/index_specs.py --spec-name AMS4911
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.spec_indexing_service import SpecIndexingService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the spec indexing pipeline.")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    parser.add_argument("--spec-name", default=None, help="Index only specs matching this name")
    args = parser.parse_args()

    summary = SpecIndexingService().run(mode=args.mode, spec_name=args.spec_name)
    # Print the per-file outcomes plus a compact summary line.
    for r in summary["results"]:
        print(
            f"  {r.get('file'):40s} {r.get('action'):10s} "
            f"spec={r.get('spec_no')} rev={r.get('revision')} "
            f"sections={r.get('sections')} refs={r.get('references')} src={r.get('text_source')}"
        )
    print(
        json.dumps(
            {k: summary[k] for k in ("mode", "discovered", "indexed", "skipped", "failed")},
            ensure_ascii=False,
        )
    )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
