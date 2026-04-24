"""
One-shot entry point for the Render Cron Job.
Runs every hour; per-user timezone logic inside run_hourly_delivery()
delivers to each subscriber at their preferred local send_hour.
"""
import logging
from newstome.delivery import run_hourly_delivery
from newstome.alerts import alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

if __name__ == "__main__":
    log.info("⏰ Cron tick: running hourly delivery...")
    try:
        run_hourly_delivery(verbose=True)
        log.info("✅ Done.")
    except Exception as e:
        log.error(f"❌ Delivery failed: {e}", exc_info=True)
        alert("Hourly cron delivery failed", detail=f"{type(e).__name__}: {e}", exc=e)
        raise
