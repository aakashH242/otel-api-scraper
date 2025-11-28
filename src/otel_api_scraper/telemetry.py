"""Telemetry initialization and emitters."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Tuple

from opentelemetry import metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as GrpcMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter as GrpcLogExporter,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as HttpMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http._log_exporter import (
    OTLPLogExporter as HttpLogExporter,
)
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

try:
    from opentelemetry._logs.severity import SeverityNumber  # type: ignore
except ImportError:  # pragma: no cover
    from opentelemetry.sdk._logs._internal.severity import SeverityNumber  # type: ignore

from . import config as cfg
from .utils import lookup_path, matches

logger = logging.getLogger(__name__)


class TelemetrySink:
    """Logs would-be telemetry payloads when dryRun is enabled."""

    def emit_metrics(self, source: str, summary: Dict[str, Any]) -> None:
        """Log metric summary."""
        logger.info("[dry-run] metrics for %s: %s", source, summary)

    def emit_logs(self, source: str, records: List[Dict[str, Any]]) -> None:
        """Log log-emission summary."""
        logger.info("[dry-run] logs for %s count=%s", source, len(records))


class GaugeAggregator:
    """Stores the most recent gauge values for observable gauges."""

    def __init__(self, meter, name: str, unit: str):
        """Create an observable gauge aggregator.

        Args:
            meter: OTEL meter instance.
            name: Gauge name.
            unit: Gauge unit.
        """
        self.values: List[Tuple[float, Dict[str, Any]]] = []
        self.gauge = meter.create_observable_gauge(
            name=name,
            callbacks=[self._callback],
            unit=unit,
        )

    def set_values(self, values: List[Tuple[float, Dict[str, Any]]]) -> None:
        """Update cached gauge values."""
        self.values = values

    def _callback(self, options: CallbackOptions):
        """APIs called by OTEL when collecting gauge data."""
        return [Observation(value=v, attributes=attrs) for v, attrs in self.values]


class Telemetry:
    """Telemetry manager handling OTLP exporters and emitters."""

    def __init__(self, config: cfg.ScraperSettings):
        """Initialize telemetry pipeline.

        Args:
            config: Scraper settings containing OTEL configuration.
        """
        self.config = config
        self.dry_run = config.dryRun
        self.resource = Resource(
            attributes={
                ResourceAttributes.SERVICE_NAME: config.serviceName,
            }
        )
        self.sink = TelemetrySink()
        self.meter_provider = None
        self.logger_provider = None
        self.meter = None
        self.self_enabled = config.enableSelfTelemetry
        self.self_counters: Dict[str, Any] = {}
        self.self_histograms: Dict[str, Any] = {}
        self.loggers: Dict[str, Any] = {}
        self.counters: Dict[Tuple[str, str], Any] = {}
        self.histograms: Dict[Tuple[str, str], Any] = {}
        self.gauges: Dict[Tuple[str, str], GaugeAggregator] = {}
        self.attribute_metrics: Dict[str, Any] = {}
        self._emit_tasks: set[asyncio.Task] = set()
        self.self_gauges: Dict[str, GaugeAggregator] = {}
        if not self.dry_run:
            self._setup_otel()
        else:
            logger.info("Telemetry running in dry-run mode. Exporters not initialized.")

    def _setup_otel(self) -> None:
        """Initialize OTLP exporters and providers."""
        metric_exporter = (
            GrpcMetricExporter(
                endpoint=self.config.otelCollectorEndpoint,
                insecure=not self.config.enforceTls,
            )
            if self.config.otelTransport == "grpc"
            else HttpMetricExporter(
                endpoint=f"{self.config.otelCollectorEndpoint}/v1/metrics"
            )
        )
        reader = PeriodicExportingMetricReader(metric_exporter)
        self.meter_provider = MeterProvider(
            resource=self.resource, metric_readers=[reader]
        )
        metrics.set_meter_provider(self.meter_provider)
        self.meter = metrics.get_meter(__name__, version="0.1.0")

        log_exporter = (
            GrpcLogExporter(
                endpoint=self.config.otelCollectorEndpoint,
                insecure=not self.config.enforceTls,
            )
            if self.config.otelTransport == "grpc"
            else HttpLogExporter(
                endpoint=f"{self.config.otelCollectorEndpoint}/v1/logs"
            )
        )
        self.logger_provider = LoggerProvider(resource=self.resource)
        self.logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(log_exporter)
        )
        set_logger_provider(self.logger_provider)

    def _get_logger(self, source: str):
        """Get or create OTEL logger for a source."""
        if source not in self.loggers:
            if self.dry_run:
                self.loggers[source] = logging.getLogger(f"drylog.{source}")
            else:
                self.loggers[source] = self.logger_provider.get_logger(source)
        return self.loggers[source]

    def _counter(self, source: str, name: str, unit: str):
        """Get or create a counter instrument."""
        key = (source, name)
        if key not in self.counters:
            self.counters[key] = self.meter.create_counter(name=name, unit=unit)
        return self.counters[key]

    def _histogram(self, source: str, name: str, unit: str):
        """Get or create a histogram instrument."""
        key = (source, name)
        if key not in self.histograms:
            self.histograms[key] = self.meter.create_histogram(name=name, unit=unit)
        return self.histograms[key]

    def _gauge(self, source: str, name: str, unit: str) -> GaugeAggregator:
        """Get or create an observable gauge aggregator."""
        key = (source, name)
        if key not in self.gauges:
            self.gauges[key] = GaugeAggregator(self.meter, name=name, unit=unit)
        return self.gauges[key]

    def emit_metrics(
        self, source: cfg.SourceConfig, records: List[Dict[str, Any]]
    ) -> None:
        """Emit metrics for a source based on configured mappings."""
        if self.dry_run:
            self.sink.emit_metrics(source.name, {"records": len(records)})
            return
        logger.debug(
            "Emitting metrics for source %s (%s records)", source.name, len(records)
        )
        try:
            for gauge_def in source.gaugeReadings:
                values = []
                for record in records:
                    val = (
                        gauge_def.fixedValue
                        if gauge_def.fixedValue is not None
                        else lookup_path(record, gauge_def.dataKey)
                    )
                    if val is None:
                        continue
                    try:
                        numeric_val = float(val)
                    except Exception:
                        continue
                    attrs = self._record_attributes(record, source)
                    values.append((numeric_val, attrs))
                agg = self._gauge(source.name, gauge_def.name, gauge_def.unit)
                agg.set_values(values)

            for counter_def in source.counterReadings:
                counter = self._counter(source.name, counter_def.name, counter_def.unit)
                for record in records:
                    amount = (
                        counter_def.fixedValue
                        if counter_def.fixedValue is not None
                        else (
                            lookup_path(record, counter_def.valueKey)
                            if counter_def.valueKey
                            else 1
                        )
                    )
                    try:
                        amount = float(amount)
                    except Exception:
                        amount = 1
                    attrs = self._record_attributes(record, source, None)
                    counter.add(amount, attributes=attrs)

            for hist_def in source.histogramReadings:
                hist = self._histogram(source.name, hist_def.name, hist_def.unit)
                for record in records:
                    val = (
                        hist_def.fixedValue
                        if hist_def.fixedValue is not None
                        else lookup_path(record, hist_def.dataKey)
                    )
                    if val is None:
                        continue
                    try:
                        val = float(val)
                    except Exception:
                        continue
                    attrs = self._record_attributes(record, source, None)
                    hist.record(val, attributes=attrs)

            self._emit_attribute_metrics(source, records)
            logger.debug("Metrics emitted for source %s", source.name)
            self._force_flush_metrics()
        except Exception as exc:
            logger.warning("Metric emission failed for source %s: %s", source.name, exc)

    def _emit_attribute_metrics(
        self, source: cfg.SourceConfig, records: List[Dict[str, Any]]
    ) -> None:
        """Emit optional attribute-derived metrics."""
        for attr in source.attributes:
            if not attr.asMetric:
                continue
            metric_name = attr.asMetric.metricName or attr.name
            counter = self._counter(source.name, metric_name, attr.asMetric.unit)
            mapping = attr.asMetric.valueMapping
            for record in records:
                val = lookup_path(record, attr.dataKey)
                mapped = mapping.get(str(val))
                if mapped is None:
                    continue
                counter.add(
                    float(mapped), attributes={"source": source.name, attr.name: val}
                )
        logger.debug("Completed attribute metric emission for source %s", source.name)

    def emit_logs(
        self, source: cfg.SourceConfig, records: List[Dict[str, Any]]
    ) -> None:
        """Emit logs for a source."""
        if not source.emitLogs:
            logger.debug(
                "Log emission skipped for source %s (emitLogs=false)", source.name
            )
            return
        if self.dry_run:
            self.sink.emit_logs(source.name, records)
            return
        logger.debug(
            "Emitting logs for source %s (%s records)", source.name, len(records)
        )
        try:
            otel_logger = self._get_logger(source.name)
            timestamp = int(time.time() * 1e9)
            for record in records:
                severity, severity_text = self._resolve_severity(
                    record, source.logStatusField
                )
                attrs = self._record_attributes(record, source)
                body = {"source": source.name, "record": record}

                # Use Logger.emit(...) instead of constructing LogRecord directly
                otel_logger.emit(
                    timestamp=timestamp,
                    observed_timestamp=timestamp,
                    severity_number=severity,
                    severity_text=severity_text,
                    body=body,
                    attributes=attrs,
                )
            logger.debug("Logs emitted for source %s", source.name)
            self._force_flush_logs()
        except Exception as exc:
            logger.warning("Log emission failed for source %s: %s", source.name, exc)

    def record_self_scrape(
        self,
        source_name: str,
        status: str,
        duration_seconds: float,
        record_count: int,
        api_type: str | None = None,
    ) -> None:
        """Emit self-telemetry metrics/logs for a scrape execution."""
        if not self.self_enabled:
            return
        api_attr = api_type or "unknown"
        logger.debug(
            "Recording self telemetry for source=%s status=%s duration=%.3fs records=%s api_type=%s",
            source_name,
            status,
            duration_seconds,
            record_count,
            api_attr,
        )
        if self.dry_run:
            logger.info(
                "[dry-run] self-telemetry source=%s status=%s duration=%.3fs records=%s api_type=%s",
                source_name,
                status,
                duration_seconds,
                record_count,
                api_attr,
            )
            return
        run_counter = self._self_counter("scraper_runs_total", "1")
        duration_hist = self._self_histogram("scraper_run_duration_seconds", "s")
        records_counter = self._self_counter("scraper_records_emitted_total", "1")
        attrs = {"source": source_name, "status": status, "api_type": api_attr}
        run_counter.add(1, attributes=attrs)
        duration_hist.record(float(duration_seconds), attributes=attrs)
        records_counter.add(float(record_count), attributes=attrs)
        self._self_gauge("scraper_last_run_duration_seconds", "s").set_values(
            [(float(duration_seconds), attrs)]
        )
        self._self_gauge("scraper_last_records_emitted", "1").set_values(
            [(float(record_count), attrs)]
        )
        self._emit_self_log(source_name, status, duration_seconds, record_count)

    def record_dedupe(
        self, source_name: str, api_type: str, hits: int, misses: int, total: int
    ) -> None:
        """Emit deduplication hit/miss counters and hit-rate gauge."""
        if not self.self_enabled or self.dry_run:
            return
        attrs = {"source": source_name, "api_type": api_type or "unknown"}
        self._self_counter("scraper_dedupe_hits_total", "1").add(
            float(hits), attributes=attrs
        )
        self._self_counter("scraper_dedupe_misses_total", "1").add(
            float(misses), attributes=attrs
        )
        self._self_counter("scraper_dedupe_total", "1").add(
            float(total), attributes=attrs
        )
        hit_rate = float(hits) / float(total) if total else 0.0
        self._self_gauge("scraper_dedupe_hit_rate", "1").set_values([(hit_rate, attrs)])

    def record_cleanup(
        self,
        job: str,
        backend: str,
        duration_seconds: float,
        cleaned: int | None = None,
    ) -> None:
        """Emit cleanup job metrics (duration, cleaned count if available)."""
        if not self.self_enabled or self.dry_run:
            return
        attrs = {"job": job, "backend": backend}
        self._self_histogram("scraper_cleanup_duration_seconds", "s").record(
            float(duration_seconds), attributes=attrs
        )
        self._self_gauge("scraper_cleanup_last_duration_seconds", "s").set_values(
            [(float(duration_seconds), attrs)]
        )
        if cleaned is not None:
            self._self_counter("scraper_cleanup_items_total", "1").add(
                float(cleaned), attributes=attrs
            )
            self._self_gauge("scraper_cleanup_last_items", "1").set_values(
                [(float(cleaned), attrs)]
            )

    def _emit_self_log(
        self, source_name: str, status: str, duration_seconds: float, record_count: int
    ) -> None:
        """Emit a log record describing a scrape execution."""
        if self.dry_run:
            return
        otel_logger = self._get_logger("scraper.self")
        timestamp = int(time.time() * 1e9)
        body = {
            "source": source_name,
            "status": status,
            "duration_seconds": duration_seconds,
            "record_count": record_count,
        }

        severity = SeverityNumber.INFO if status == "success" else SeverityNumber.ERROR
        severity_text = "INFO" if status == "success" else "ERROR"

        otel_logger.emit(
            timestamp=timestamp,
            observed_timestamp=timestamp,
            severity_number=severity,
            severity_text=severity_text,
            body=body,
            attributes={"component": "scraper"},
        )

    def _self_counter(self, name: str, unit: str):
        """Get or create a self-telemetry counter."""
        if name not in self.self_counters:
            self.self_counters[name] = self.meter.create_counter(name=name, unit=unit)
        return self.self_counters[name]

    def _self_histogram(self, name: str, unit: str):
        """Get or create a self-telemetry histogram."""
        if name not in self.self_histograms:
            self.self_histograms[name] = self.meter.create_histogram(
                name=name, unit=unit
            )
        return self.self_histograms[name]

    def _self_gauge(self, name: str, unit: str) -> GaugeAggregator:
        """Get or create a self-telemetry gauge aggregator."""
        if name not in self.self_gauges:
            self.self_gauges[name] = GaugeAggregator(self.meter, name=name, unit=unit)
        return self.self_gauges[name]

    def _record_attributes(
        self,
        record: Dict[str, Any],
        source: cfg.SourceConfig,
        extra_labels: List[cfg.MetricLabel] | None = None,
    ) -> Dict[str, Any]:
        """Build OTEL attributes from configured attributes and labels."""
        attrs = {"source": source.name}
        for attr in source.attributes:
            val = lookup_path(record, attr.dataKey)
            if val is not None:
                attrs[attr.name] = val
        if extra_labels:
            for label in extra_labels:
                val = lookup_path(record, label.dataKey)
                if val is not None:
                    attrs[label.name] = val
        return attrs

    def _resolve_severity(
        self, record: Dict[str, Any], field_cfg: cfg.LogStatusField | None
    ) -> Tuple[SeverityNumber, str]:
        """Derive log severity from record and logStatusField config."""
        if not field_cfg:
            return SeverityNumber.INFO, "INFO"
        status_val = lookup_path(record, field_cfg.name)
        if field_cfg.error and matches(
            field_cfg.error.matchType, status_val, field_cfg.error.value
        ):
            return SeverityNumber.ERROR, "ERROR"
        if field_cfg.warning and matches(
            field_cfg.warning.matchType, status_val, field_cfg.warning.value
        ):
            return SeverityNumber.WARNING, "WARNING"
        if field_cfg.info and matches(
            field_cfg.info.matchType, status_val, field_cfg.info.value
        ):
            return SeverityNumber.INFO, "INFO"
        return SeverityNumber.INFO, "INFO"

    async def shutdown(self) -> None:
        """Flush and shutdown OTEL providers."""
        for task in list(self._emit_tasks):
            if not task.done():
                task.cancel()
        if self._emit_tasks:
            await asyncio.gather(*self._emit_tasks, return_exceptions=True)
        if self.logger_provider:
            result = self.logger_provider.shutdown()
            if hasattr(result, "__await__"):
                await result
        if self.meter_provider:
            result = self.meter_provider.shutdown()
            if hasattr(result, "__await__"):
                await result

    def _force_flush_metrics(self) -> None:
        if self.meter_provider and hasattr(self.meter_provider, "force_flush"):
            try:
                result = self.meter_provider.force_flush()
                if hasattr(result, "__await__"):
                    asyncio.create_task(result)
            except Exception as exc:
                logger.debug("Metric force_flush failed: %s", exc)

    def _force_flush_logs(self) -> None:
        if self.logger_provider and hasattr(self.logger_provider, "force_flush"):
            try:
                result = self.logger_provider.force_flush()
                if hasattr(result, "__await__"):
                    asyncio.create_task(result)
            except Exception as exc:
                logger.debug("Log force_flush failed: %s", exc)
