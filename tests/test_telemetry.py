import asyncio
from unittest.mock import MagicMock

import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper.telemetry import (
    CallbackOptions,
    GaugeAggregator,
    Telemetry,
    TelemetrySink,
    SeverityNumber,
)


def make_source():
    return cfg.SourceConfig(
        name="svc",
        frequency="1min",
        baseUrl="http://example.com",
        endpoint="/items",
        scrape=cfg.ScrapeConfig(type="instant"),
    )


class FakeCounter:
    def __init__(self):
        self.adds = []

    def add(self, amount, attributes=None):
        self.adds.append((amount, attributes))


class FakeHistogram:
    def __init__(self):
        self.records = []

    def record(self, value, attributes=None):
        self.records.append((value, attributes))


class FakeGauge:
    def __init__(self):
        self.values = []

    def set_values(self, values):
        self.values = values

    def __call__(self, *args, **kwargs):
        return self


class FakeMeter:
    def __init__(self):
        self.counters = {}
        self.histograms = {}
        self.gauges = {}

    def create_counter(self, name, unit):
        c = FakeCounter()
        self.counters[name] = c
        return c

    def create_histogram(self, name, unit):
        h = FakeHistogram()
        self.histograms[name] = h
        return h

    def create_observable_gauge(self, name, callbacks, unit):
        g = FakeGauge()
        self.gauges[name] = (g, callbacks)
        return g


class FakeProvider:
    def __init__(self):
        self.force_flush_called = False
        self.shutdown_called = False
        self.loggers = {}
        self.force_flush_result = None

    def force_flush(self):
        self.force_flush_called = True
        return self.force_flush_result

    def shutdown(self):
        self.shutdown_called = True

        async def done():
            return None

        return done()

    def get_logger(self, name):
        logger = FakeLogger()
        self.loggers[name] = logger
        return logger


class FakeLogger:
    def __init__(self):
        self.emitted = []

    def emit(self, **kwargs):
        self.emitted.append(kwargs)


def telemetry_with_fakes(dry_run=False):
    def setup(self):
        self.meter_provider = FakeProvider()
        self.logger_provider = FakeProvider()
        self.meter = FakeMeter()

    t = Telemetry.__new__(Telemetry)
    t._setup_otel = setup.__get__(t, Telemetry)  # type: ignore[method-assign]
    Telemetry.__init__(
        t, cfg.ScraperSettings(otelCollectorEndpoint="http://collector", dryRun=dry_run)
    )
    return t


def test_record_attributes_and_severity():
    t = telemetry_with_fakes(dry_run=True)
    src = make_source()
    src.attributes = [cfg.AttributeConfig(name="region", dataKey="meta.region")]
    labels = [cfg.MetricLabel(name="id_label", dataKey="id")]
    record = {"meta": {"region": "us"}, "id": "123", "status": "warn"}
    attrs = t._record_attributes(record, src, labels)
    assert attrs["region"] == "us" and attrs["id_label"] == "123"

    field = cfg.LogStatusField(
        name="status",
        info=cfg.LogStatusRule(value="ok"),
        warning=cfg.LogStatusRule(value="warn"),
        error=cfg.LogStatusRule(value="err"),
    )
    sev_err, text_err = t._resolve_severity({"status": "err"}, field)
    assert sev_err == SeverityNumber.ERROR and text_err == "ERROR"
    sev_info, text_info = t._resolve_severity({}, None)
    assert sev_info == SeverityNumber.INFO and text_info == "INFO"


def test_resolve_severity_warning(monkeypatch):
    from otel_api_scraper import telemetry as tmod

    monkeypatch.setattr(
        tmod,
        "SeverityNumber",
        type("SN", (), {"INFO": "INFO", "WARNING": "WARNING", "ERROR": "ERROR"}),
    )
    t = telemetry_with_fakes(dry_run=True)
    field = cfg.LogStatusField(
        name="status",
        warning=cfg.LogStatusRule(value="warn"),
    )
    sev, txt = t._resolve_severity({"status": "warn"}, field)
    assert sev == "WARNING" and txt == "WARNING"


def test_emit_metrics_non_dry_run(monkeypatch):
    t = telemetry_with_fakes(dry_run=False)
    src = make_source()
    src.gaugeReadings = [cfg.GaugeReading(name="g", dataKey="v", unit="1")]
    src.counterReadings = [cfg.CounterReading(name="c", valueKey="cval", unit="1")]
    src.histogramReadings = [
        cfg.HistogramReading(name="h", dataKey="hval", unit="ms", buckets=[1.0])
    ]
    src.attributes = [cfg.AttributeConfig(name="region", dataKey="meta.region")]
    src.counterReadings[0].fixedValue = None
    records = [{"v": "2", "cval": "3", "hval": "4", "meta": {"region": "us"}}]

    t.emit_metrics(src, records)

    assert t.gauges[("svc", "g")].values[0][0] == 2.0
    assert t.meter.counters["c"].adds[0][0] == 3.0
    assert t.meter.histograms["h"].records[0][0] == 4.0
    assert t.meter_provider.force_flush_called is True


def test_emit_metrics_dry_run(monkeypatch, caplog):
    caplog.set_level("INFO")
    t = telemetry_with_fakes(dry_run=True)
    t.sink = MagicMock()
    src = make_source()
    t.emit_metrics(src, [{"id": 1}])
    t.sink.emit_metrics.assert_called_once()


def test_emit_metrics_handles_missing_and_bad_values():
    t = telemetry_with_fakes(dry_run=False)
    src = make_source()
    src.gaugeReadings = [cfg.GaugeReading(name="g", dataKey="missing", unit="1")]
    src.counterReadings = [cfg.CounterReading(name="c", valueKey="bad", unit="1")]
    src.histogramReadings = [
        cfg.HistogramReading(name="h", dataKey="strval", unit="ms", buckets=[1.0])
    ]
    records = [{"bad": "notnum", "strval": "oops"}]
    t.emit_metrics(src, records)
    # counter should default to 1 when conversion fails
    assert t.meter.counters["c"].adds[0][0] == 1
    # histogram skip invalid value, so no records
    assert t.meter.histograms["h"].records == []


def test_emit_logs_paths(monkeypatch):
    t = telemetry_with_fakes(dry_run=True)
    t.sink = MagicMock()
    src = make_source()
    src.emitLogs = False
    t.emit_logs(src, [{"id": 1}])
    t.sink.emit_logs.assert_not_called()

    src.emitLogs = True
    t.emit_logs(src, [{"id": 1}])
    t.sink.emit_logs.assert_called_once()


def test_emit_logs_real(monkeypatch):
    t = telemetry_with_fakes(dry_run=False)
    logger_calls = []

    class FakeLogger:
        def emit(self, **kwargs):
            logger_calls.append(kwargs)

    t._get_logger = lambda name: FakeLogger()
    t._force_flush_logs = MagicMock()
    src = make_source()
    src.logStatusField = cfg.LogStatusField(
        name="level",
        info=cfg.LogStatusRule(value="info"),
        warning=cfg.LogStatusRule(value="warn"),
        error=cfg.LogStatusRule(value="err"),
    )
    t.emit_logs(src, [{"level": "err"}])
    assert logger_calls and logger_calls[0]["severity_number"] == SeverityNumber.ERROR
    t._force_flush_logs.assert_called_once()


def test_emit_logs_error_branch(monkeypatch):
    t = telemetry_with_fakes(dry_run=False)
    t._get_logger = lambda name: (_ for _ in ()).throw(RuntimeError("log error"))
    t._force_flush_logs = MagicMock()
    src = make_source()
    t.emit_logs(src, [{"level": "err"}])


def test_record_self_scrape_dry_run_and_real():
    src = make_source()
    t = telemetry_with_fakes(dry_run=True)
    t.self_enabled = True
    t.record_self_scrape(src.name, "success", 1.2, 3)

    t2 = telemetry_with_fakes(dry_run=False)
    t2.self_enabled = True
    t2.record_self_scrape(src.name, "error", 2.5, 4)
    assert t2.meter.counters["scraper_runs_total"].adds[0][0] == 1
    assert t2.meter.histograms["scraper_run_duration_seconds"].records[0][0] == 2.5
    assert "scraper.self" in t2.logger_provider.loggers


def test_record_self_scrape_disabled_and_dry_run():
    t = telemetry_with_fakes(dry_run=False)
    t.self_enabled = False
    t.record_self_scrape("svc", "success", 1.0, 1)  # returns early

    t2 = telemetry_with_fakes(dry_run=True)
    t2.self_enabled = True
    t2.record_self_scrape("svc", "success", 1.0, 1)  # dry-run logging path
    t2._emit_self_log("svc", "success", 1.0, 1)  # direct call to cover dry-run return


@pytest.mark.asyncio
async def test_shutdown_cancels_tasks(monkeypatch):
    t = telemetry_with_fakes(dry_run=False)
    fut = asyncio.Future()
    t._emit_tasks.add(fut)

    async def fake_gather(*tasks, return_exceptions=False):
        fake_gather.called = True
        for task in tasks:
            if not task.done():
                task.cancel()
        return []

    fake_gather.called = False
    monkeypatch.setattr("otel_api_scraper.telemetry.asyncio.gather", fake_gather)
    await t.shutdown()
    assert fake_gather.called
    assert t.logger_provider.shutdown_called
    assert t.meter_provider.shutdown_called


def test_force_flush_helpers(monkeypatch):
    t = telemetry_with_fakes(dry_run=False)
    called = {}

    async def awaitable():
        called["task"] = True

    t.meter_provider.force_flush_result = awaitable()
    t.logger_provider.force_flush_result = awaitable()

    monkeypatch.setattr(
        "asyncio.create_task", lambda coro: called.setdefault("created", True)
    )
    t._force_flush_metrics()
    t._force_flush_logs()
    assert called["created"] is True


def test_force_flush_handles_exceptions(monkeypatch):
    t = telemetry_with_fakes(dry_run=False)

    def bad_flush():
        raise RuntimeError("flush fail")

    t.meter_provider.force_flush = bad_flush
    t.logger_provider.force_flush = bad_flush
    t._force_flush_metrics()
    t._force_flush_logs()


def test_sink_and_gauge_callback(caplog):
    caplog.set_level("INFO")
    sink = TelemetrySink()
    sink.emit_metrics("svc", {"records": 1})
    sink.emit_logs("svc", [{}])

    fake_meter = FakeMeter()
    agg = GaugeAggregator(fake_meter, "g", "1")
    agg.set_values([(1.0, {"a": "b"})])
    obs = agg._callback(CallbackOptions())
    assert obs[0].value == 1.0


def test_get_logger_dry_run(monkeypatch):
    t = telemetry_with_fakes(dry_run=True)
    logger = t._get_logger("svc")
    assert logger.name.startswith("drylog.")


def test_emit_metrics_error_branches(monkeypatch, caplog):
    caplog.set_level("WARNING")
    t = telemetry_with_fakes(dry_run=False)
    t._force_flush_metrics = lambda: (_ for _ in ()).throw(RuntimeError("flush error"))
    src = make_source()
    src.gaugeReadings = [cfg.GaugeReading(name="g", dataKey="bad", unit="1")]
    src.histogramReadings = [
        cfg.HistogramReading(name="h", dataKey=None, unit="ms", buckets=[1.0])
    ]
    records = [{"bad": "notnumber"}]
    t.emit_metrics(src, records)
    assert any("Metric emission failed" in msg for msg in caplog.messages)


def test_emit_attribute_metrics_unmapped_value(caplog):
    caplog.set_level("DEBUG")
    t = telemetry_with_fakes(dry_run=False)
    src = make_source()
    src.attributes = [
        cfg.AttributeConfig(
            name="region",
            dataKey="meta.region",
            asMetric=cfg.AttributeAsMetric(
                metricName="region_metric", valueMapping={"other": 1.0}
            ),
        )
    ]
    records = [{"meta": {"region": "us"}}]
    t._emit_attribute_metrics(src, records)
    assert ("svc", "region_metric") in t.counters


def test_resolve_severity_info_branch():
    t = telemetry_with_fakes(dry_run=True)
    field = cfg.LogStatusField(name="status", info=cfg.LogStatusRule(value="ok"))
    sev, txt = t._resolve_severity({"status": "ok"}, field)
    assert sev == SeverityNumber.INFO and txt == "INFO"


def test_resolve_severity_default_when_no_match():
    t = telemetry_with_fakes(dry_run=True)
    field = cfg.LogStatusField(
        name="status",
        info=cfg.LogStatusRule(value="info"),
        warning=cfg.LogStatusRule(value="warn"),
        error=cfg.LogStatusRule(value="err"),
    )
    sev, txt = t._resolve_severity({"status": "other"}, field)
    assert sev == SeverityNumber.INFO and txt == "INFO"


def test_emit_attribute_metrics(monkeypatch):
    t = telemetry_with_fakes(dry_run=False)
    src = make_source()
    src.attributes = [
        cfg.AttributeConfig(
            name="region",
            dataKey="meta.region",
            asMetric=cfg.AttributeAsMetric(
                metricName="region_metric", valueMapping={"us": 1.0}
            ),
        )
    ]
    records = [{"meta": {"region": "us"}}]
    t._emit_attribute_metrics(src, records)
    assert t.meter.counters["region_metric"].adds[0][0] == 1.0


def test_setup_otel_inits_exporters(monkeypatch):
    created = {}

    class DummyExp:
        def __init__(self, *args, **kwargs):
            created["exp"] = kwargs

    class DummyReader:
        def __init__(self, exporter):
            created["reader"] = exporter

    class DummyMeterProvider(FakeProvider):
        def __init__(self, resource=None, metric_readers=None):
            super().__init__()
            created["metric_readers"] = metric_readers

    class DummyLoggerProvider(FakeProvider):
        def __init__(self, resource=None):
            super().__init__()
            self.processors = []

        def add_log_record_processor(self, proc):
            self.processors.append(proc)

    class DummyProcessor:
        def __init__(self, exporter):
            created["log_exporter"] = exporter

    monkeypatch.setattr("otel_api_scraper.telemetry.GrpcMetricExporter", DummyExp)
    monkeypatch.setattr("otel_api_scraper.telemetry.HttpMetricExporter", DummyExp)
    monkeypatch.setattr(
        "otel_api_scraper.telemetry.PeriodicExportingMetricReader", DummyReader
    )
    monkeypatch.setattr("otel_api_scraper.telemetry.MeterProvider", DummyMeterProvider)
    monkeypatch.setattr(
        "otel_api_scraper.telemetry.LoggerProvider", DummyLoggerProvider
    )
    monkeypatch.setattr(
        "otel_api_scraper.telemetry.BatchLogRecordProcessor", DummyProcessor
    )
    monkeypatch.setattr(
        "otel_api_scraper.telemetry.set_logger_provider",
        lambda prov: created.setdefault("logger_provider", prov),
    )
    monkeypatch.setattr(
        "otel_api_scraper.telemetry.metrics.set_meter_provider",
        lambda prov: created.setdefault("meter_provider", prov),
    )
    monkeypatch.setattr(
        "otel_api_scraper.telemetry.metrics.get_meter",
        lambda name, version=None: FakeMeter(),
    )

    Telemetry(
        cfg.ScraperSettings(
            otelCollectorEndpoint="http://collector", enforceTls=False, dryRun=False
        )
    )

    assert "meter_provider" in created and "logger_provider" in created
    assert created["metric_readers"]
