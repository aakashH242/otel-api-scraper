"""APScheduler wiring for periodic scrapes."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import config as cfg
from .scraper_engine import ScraperEngine
from .utils import parse_frequency

logger = logging.getLogger(__name__)


class ScraperScheduler:
    """Schedules periodic scrape jobs for all sources."""

    def __init__(self, app_config: cfg.AppConfig, engine: ScraperEngine) -> None:
        """Create scheduler with application config and engine."""
        self.app_config = app_config
        self.engine = engine
        self.scheduler = AsyncIOScheduler()
        self._allow_overlap = app_config.scraper.allowOverlapScans

    def start(self) -> None:
        """Start the scheduler and register jobs."""
        logger.debug("Starting scheduler with overlap=%s", self._allow_overlap)
        for source in self.app_config.sources:
            interval = parse_frequency(source.frequency)

            # APScheduler wants an int (and > 0) for misfire_grace_time.
            seconds = int(interval.total_seconds())
            if seconds <= 0:
                raise ValueError(
                    f"Invalid frequency '{source.frequency}' for source '{source.name}': "
                    f"computed interval {interval} -> {seconds} seconds"
                )

            trigger = IntervalTrigger(seconds=seconds)
            allow_overlap = self._allow_overlap or getattr(
                source, "allowOverlapScans", False
            )

            self.scheduler.add_job(
                self._run_source,
                trigger=trigger,
                args=[source],
                id=source.name,
                coalesce=not allow_overlap,
                max_instances=999 if allow_overlap else 1,
                misfire_grace_time=seconds,
            )

            logger.info(
                "Scheduled source '%s' with interval=%ss (frequency=%s)",
                source.name,
                seconds,
                source.frequency,
            )
            logger.debug(
                "Job settings for %s overlap=%s coalesce=%s max_instances=%s",
                source.name,
                allow_overlap,
                not allow_overlap,
                999 if allow_overlap else 1,
            )

        self.scheduler.start()
        logger.info("Scheduler started with %s sources", len(self.app_config.sources))

    async def _run_source(self, source: cfg.SourceConfig) -> None:
        """Job wrapper to run a single source scrape."""
        await self.engine.scrape_source(source)

    async def shutdown(self, wait: bool = True) -> None:
        """Shut down scheduler."""
        # This is sync, but it's fine to call inside an async function.
        self.scheduler.shutdown(wait=wait)
        logger.info("Scheduler shut down (wait=%s)", wait)

    async def run_all_once(self) -> None:
        """Trigger a one-time scrape for all sources."""
        await asyncio.gather(
            *(self.engine.scrape_source(src) for src in self.app_config.sources)
        )
