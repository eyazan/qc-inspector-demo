"""Schedulable wrapper for the spec indexing pipeline (2B).

Designed to be driven by an external scheduler (cron / Airflow / Task Scheduler)
rather than an in-process loop, so the vendor API and the indexer have separate
lifecycles. SPEC_INDEX_SCHEDULE is informational (the cron expression to install).

Example crontab (run incremental every night at 02:00):
    0 2 * * *  cd /path/to/backend && .venv/bin/python scripts/schedule_spec_indexing.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.services.spec_indexing_service import SpecIndexingService  # noqa: E402


def main() -> int:
    configure_logging()
    logger = get_logger("schedule_spec_indexing")
    mode = settings.spec_index_mode or "incremental"
    logger.info("Scheduled spec indexing basliyor (mode=%s)", mode)
    summary = SpecIndexingService().run(mode=mode)
    logger.info(
        "Scheduled spec indexing bitti: discovered=%s indexed=%s skipped=%s failed=%s",
        summary["discovered"], summary["indexed"], summary["skipped"], summary["failed"],
    )
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
