"""
Purpose: Run the periodic GPS polling job on a fixed schedule inside the FastAPI process.
Inputs: A configured ingestion service and the polling interval from application settings.
Outputs: APScheduler lifecycle management and one serialized polling job.
Invariants: Only one polling job may run at a time to avoid duplicate position writes.
Debugging: APScheduler logs will show skipped runs, misfires, and uncaught exceptions.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.location_service import LocationIngestionService

logger = logging.getLogger(__name__)


class PollingScheduler:
    """Own and manage the background polling scheduler."""

    def __init__(self, ingestion_service: LocationIngestionService, poll_interval_seconds: int) -> None:
        self.ingestion_service = ingestion_service
        self.poll_interval_seconds = poll_interval_seconds
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        if self.scheduler.running:
            return

        self.scheduler.add_job(
            self._run_polling_job,
            trigger=IntervalTrigger(seconds=self.poll_interval_seconds),
            id="poll_xplora_locations",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=self.poll_interval_seconds,
        )
        self.scheduler.start()
        logger.info("Polling scheduler started", extra={"interval_seconds": self.poll_interval_seconds})

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Polling scheduler stopped")

    def _run_polling_job(self) -> None:
        """Wrap the ingestion call so scheduler errors stay visible in logs."""

        logger.debug("Starting scheduled polling job")
        self.ingestion_service.poll_once()
