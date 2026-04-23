import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .delivery import run_delivery_cycle
from .alerts import alert

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def job_daily_digest():
    """Triggered by APScheduler every morning."""
    logger.info("⏰ Starting scheduled daily digest job...")
    try:
        run_delivery_cycle(verbose=True)
        logger.info("✅ Scheduled job completed successfully.")
    except Exception as e:
        logger.error(f"❌ Scheduled job failed: {e}", exc_info=True)
        alert("Daily digest job failed", detail=f"{type(e).__name__}: {e}", exc=e)

def start_scheduler():
    """Initializes and starts the blocking scheduler."""
    scheduler = BlockingScheduler()
    
    # Target: 7 AM IST (Indian Standard Time)
    # IST is UTC+5:30
    tz = pytz.timezone('Asia/Kolkata')
    
    trigger = CronTrigger(hour=7, minute=0, timezone=tz)
    scheduler.add_job(job_daily_digest, trigger, id='daily_digest', name='7 AM IST Digest')
    
    logger.info(f"🚀 Scheduler started. Next run at 07:00 AM IST daily.")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Scheduler stopped.")

if __name__ == "__main__":
    start_scheduler()
