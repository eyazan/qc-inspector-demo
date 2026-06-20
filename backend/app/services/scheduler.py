"""Optional scheduled spec indexing.

If SPEC_INDEX_SCHEDULE (cron) is set and APScheduler is installed, schedule a
background job that submits a spec_index job to the queue (separate lifecycle
from the vendor request path). No-op otherwise — external cron calling
scripts/schedule_spec_indexing.py remains a valid alternative.
"""

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_scheduler = None


def start_scheduler() -> bool:
    """Returns True if a schedule was installed."""
    global _scheduler
    cron = (settings.spec_index_schedule or "").strip()
    if not cron:
        return False
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("SPEC_INDEX_SCHEDULE set but apscheduler not installed; skipping")
        return False

    def _run():
        from app.jobs.factory import get_job_queue

        job = get_job_queue().submit("spec_index", {"mode": settings.spec_index_mode})
        logger.info("Scheduled spec indexing submitted: %s", job.id)

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_run, CronTrigger.from_crontab(cron), id="spec_index")
    _scheduler.start()
    logger.info("Spec indexing scheduled: %s", cron)
    return True


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
