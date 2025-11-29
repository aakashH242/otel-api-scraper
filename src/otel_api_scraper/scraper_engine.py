"""Core scraping engine: window computation, HTTP calls, and processing."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple


from . import config as cfg
from .http_client import AsyncHttpClient, AuthStrategy, build_auth_strategy
from .pipeline import RecordPipeline
from .state import StateStore
from .telemetry import Telemetry
from .utils import (
    build_query_string,
    extract_records,
    format_datetime,
    parse_datetime,
    parse_frequency,
    ShapeMismatch,
    utc_now,
    window_slices,
)

logger = logging.getLogger(__name__)


class ScraperEngine:
    """Coordinates scraping, processing, and telemetry emission."""

    def __init__(
        self,
        app_config: cfg.AppConfig,
        http_client: AsyncHttpClient,
        pipeline: RecordPipeline,
        telemetry: Telemetry,
        state_store: StateStore,
    ):
        """Initialize scraper engine components."""
        self.config = app_config
        self.http_client = http_client
        self.pipeline = pipeline
        self.telemetry = telemetry
        self.state_store = state_store
        self.source_semaphores: Dict[str, asyncio.Semaphore] = {}

    def _source_semaphore(self, source: cfg.SourceConfig) -> asyncio.Semaphore:
        """Get or create per-source concurrency semaphore."""
        if source.name not in self.source_semaphores:
            limit = (
                source.scrape.maxConcurrency
                or self.config.scraper.defaultSourceConcurrency
            )
            self.source_semaphores[source.name] = asyncio.Semaphore(limit)
        return self.source_semaphores[source.name]

    async def scrape_source(self, source: cfg.SourceConfig) -> None:
        """Scrape a source, process records, and emit telemetry."""
        start_time = utc_now()
        status = "success"
        all_records: List[dict[str, Any]] = []
        api_type = source.scrape.type
        try:
            last_success = await self.state_store.get_last_success(source.name)
            if last_success is None and not source.runFirstScrape:
                await self.state_store.set_last_success(source.name, start_time)
                logger.info(
                    "Skipping initial scrape for %s (runFirstScrape=false); recorded now as last_success",
                    source.name,
                )
                return
            windows = await self._compute_windows(source, start_time, last_success)
            logger.debug("Computed %s windows for source %s", len(windows), source.name)
            auth_strategy = build_auth_strategy(source.auth)
            sem = self._source_semaphore(source)

            async def run_window(window: Tuple[datetime, datetime] | None):
                """Execute scrape for a single window."""
                async with sem:
                    try:
                        logger.debug(
                            "Fetching window %s for source %s", window, source.name
                        )
                        records, raw_payload = await self._fetch_window(
                            source, window, auth_strategy
                        )
                        logger.debug(
                            "Fetched %s raw records for source %s window %s",
                            len(records),
                            source.name,
                            window,
                        )
                        processed = await self.pipeline.run(records, source)
                        return processed, False, raw_payload
                    except ShapeMismatch as exc:
                        logger.error(
                            "Shape mismatch for source %s: %s", source.name, exc
                        )
                        return [], True, None
                    except Exception as exc:
                        logger.exception(
                            "Error scraping source %s: %s", source.name, exc
                        )
                        return [], True, None

            results = await asyncio.gather(*[run_window(w) for w in windows])
            had_errors = False
            telemetry_batches: List[Tuple[List[dict[str, Any]], Any]] = []
            for chunk in results:
                if isinstance(chunk, tuple) and len(chunk) == 3:
                    records, errored, raw_payload = chunk
                    had_errors = had_errors or errored
                    if records:
                        all_records.extend(records)
                        telemetry_batches.append((records, raw_payload))
                else:  # pragma: no cover - defensive
                    all_records.extend(chunk)
            status = "error" if had_errors else "success"
            if telemetry_batches:
                await self._emit_telemetry_async(source, telemetry_batches)
            else:
                logger.debug(
                    "No records to emit for source %s after filters/dedup", source.name
                )
            await self.state_store.set_last_success(source.name, start_time)
        finally:
            duration = (utc_now() - start_time).total_seconds()
            stats = getattr(self.pipeline, "last_stats", None) or {
                "hits": 0,
                "misses": 0,
                "total": 0,
            }
            self.telemetry.record_self_scrape(
                source.name, status, duration, len(all_records), api_type=api_type
            )
            self.telemetry.record_dedupe(
                source.name,
                api_type,
                hits=stats.get("hits", 0),
                misses=stats.get("misses", 0),
                total=stats.get("total", 0),
            )
            logger.info(
                "Scrape complete for %s: records=%s status=%s",
                source.name,
                len(all_records),
                status,
            )

    async def _emit_telemetry_async(
        self,
        source: cfg.SourceConfig,
        batches: List[Tuple[List[dict[str, Any]], Any]],
    ) -> None:
        """Emit metrics/logs in background tasks to avoid blocking scrapes."""
        loop = asyncio.get_running_loop()

        async def emit():
            for records, raw_payload in batches:
                try:
                    self.telemetry.emit_metrics(source, records, raw_payload)
                except Exception as exc:
                    logger.warning(
                        "Metric emission failed for source %s: %s", source.name, exc
                    )
                try:
                    self.telemetry.emit_logs(source, records, raw_payload)
                except Exception as exc:
                    logger.warning(
                        "Log emission failed for source %s: %s", source.name, exc
                    )

        task = loop.create_task(emit())
        self.telemetry._emit_tasks.add(task)
        task.add_done_callback(lambda t: self.telemetry._emit_tasks.discard(t))

    async def _compute_windows(
        self, source: cfg.SourceConfig, now: datetime, last_success: datetime | None
    ) -> List[Tuple[datetime, datetime] | None]:
        """Compute scrape windows for a source."""
        if source.scrape.type == "instant":
            return [None]
        rk = source.scrape.rangeKeys
        assert rk
        start_time = last_success
        time_fmt = (
            rk.dateFormat
            if rk.dateFormat
            else source.scrape.timeFormat
            if source.scrape.timeFormat
            else self.config.scraper.defaultTimeFormat
        )
        if start_time is None:
            if rk.firstScrapeStart:
                start_time = parse_datetime(rk.firstScrapeStart, time_fmt)
            else:
                start_time = now - parse_frequency(source.frequency)
        end_time = now
        if source.scrape.parallelWindow:
            unit = source.scrape.parallelWindow.unit
            value = source.scrape.parallelWindow.value
            delta = self._parallel_delta(unit, value)
            return window_slices(start_time, end_time, delta)
        return [(start_time, end_time)]

    def _parallel_delta(self, unit: str, value: int) -> timedelta:
        """Convert parallelWindow unit/value to timedelta."""
        if unit == "minutes":
            return timedelta(minutes=value)
        if unit == "hours":
            return timedelta(hours=value)
        if unit == "days":
            return timedelta(days=value)
        raise ValueError(f"Unsupported parallelWindow unit {unit}")

    def _uses_root_payload(self, source: cfg.SourceConfig) -> bool:
        """Return True if any metric/log config references $root.* paths."""

        def needs_root(path: str | None) -> bool:
            return isinstance(path, str) and path.startswith("$root.")

        for gauge in source.gaugeReadings:
            if needs_root(gauge.dataKey):
                return True
        for counter in source.counterReadings:
            if needs_root(counter.dataKey):
                return True
        for hist in source.histogramReadings:
            if needs_root(hist.dataKey):
                return True
        for attr in source.attributes:
            if needs_root(attr.dataKey):
                return True
        if source.logStatusField and needs_root(source.logStatusField.name):
            return True
        return False

    async def _fetch_window(
        self,
        source: cfg.SourceConfig,
        window: Tuple[datetime, datetime] | None,
        auth_strategy: AuthStrategy | None,
    ) -> Tuple[List[dict[str, Any]], Any]:
        """Fetch data for a given window from the source API."""
        url = self.http_client.build_url(source.baseUrl, source.endpoint)
        scrape_cfg = source.scrape
        headers = {**scrape_cfg.extraHeaders}
        if auth_strategy:
            headers.update(await auth_strategy.headers(self.http_client.client))
        params: Dict[str, Any] = {}
        raw_params: Dict[str, str] = {}
        body: Dict[str, Any] = {}

        time_fmt = (
            scrape_cfg.rangeKeys.dateFormat
            if scrape_cfg.rangeKeys and scrape_cfg.rangeKeys.dateFormat
            else scrape_cfg.timeFormat or self.config.scraper.defaultTimeFormat
        )

        if scrape_cfg.type == "range" and window:
            start, end = window
            rk = scrape_cfg.rangeKeys
            assert rk
            if rk.has_explicit_bounds():
                start_val = format_datetime(start, time_fmt)
                end_val = format_datetime(end, time_fmt)
                if scrape_cfg.urlEncodeTimeKeys:
                    params[rk.startKey] = start_val
                    params[rk.endKey] = end_val
                else:
                    raw_params[rk.startKey] = start_val
                    raw_params[rk.endKey] = end_val
            elif rk.is_relative():
                params["unit"] = rk.unit
                value = rk.value
                if isinstance(value, str) and value == "from-config":
                    freq_delta = parse_frequency(source.frequency)
                    derived = int(
                        freq_delta.total_seconds() // self._unit_seconds(rk.unit)
                    )
                    if rk.takeNegative:
                        derived = -abs(derived)
                    value = derived
                params["value"] = value

        for key, val in scrape_cfg.extraArgs.items():
            if isinstance(val, dict) and "noEncodeValue" in val:
                raw_params[key] = val["noEncodeValue"]
            else:
                params[key] = val

        method = scrape_cfg.httpMethod.upper()
        if method == "GET":
            query = build_query_string(params, raw_params)
            full_url = url + (("?" + query) if query else "")
            response = await self.http_client.request(method, full_url, headers=headers)
        else:
            body.update(params)
            body.update(raw_params)
            response = await self.http_client.request(
                method, url, headers=headers, json=body
            )
        response.raise_for_status()
        payload = response.json()
        if self._uses_root_payload(source) and not isinstance(payload, dict):
            raise ShapeMismatch("Root-scoped lookups require an object payload")
        return extract_records(payload, source.dataKey), payload

    def _unit_seconds(self, unit: str | None) -> int:
        """Return number of seconds for a relative unit."""
        if unit == "minutes":
            return 60
        if unit == "hours":
            return 3600
        if unit == "days":
            return 86400
        if unit == "weeks":
            return 604800
        if unit == "months":
            return 2592000
        return 1
