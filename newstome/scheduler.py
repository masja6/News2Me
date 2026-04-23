import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .delivery import run_delivery_cycle, run_hourly_delivery
from .alerts import alert

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def job_hourly_delivery():
    """Fires every hour on the hour. Sends digests to users whose local
    send_hour matches the current hour in their timezone."""
    logger.info("⏰ Hourly delivery tick...")
    try:
        run_hourly_delivery(verbose=True)
        logger.info("✅ Hourly tick completed.")
    except Exception as e:
        logger.error(f"❌ Hourly tick failed: {e}", exc_info=True)
        alert("Hourly delivery tick failed", detail=f"{type(e).__name__}: {e}", exc=e)


def start_scheduler():
    """Initializes and starts the blocking scheduler.

    Fires every hour on the hour (UTC). The per-user fan-out happens inside
    run_hourly_delivery(), which matches each subscriber's local send_hour
    against the current hour in their own timezone."""
    scheduler = BlockingScheduler()
    trigger = CronTrigger(minute=0, timezone=pytz.UTC)
    scheduler.add_job(job_hourly_delivery, trigger, id='hourly_delivery', name='Hourly per-user delivery')
    logger.info("🚀 Scheduler started. Hourly ticks — per-user send_hour honored.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Scheduler stopped.")

if __name__ == "__main__":
    start_scheduler()
