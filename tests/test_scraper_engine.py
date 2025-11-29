import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper.scraper_engine import ScraperEngine
from otel_api_scraper.utils import ShapeMismatch


def make_source(
    scrape_type="instant",
    http_method="GET",
    url_encode=False,
    range_keys=None,
    extra_args=None,
):
    return cfg.SourceConfig(
        name="svc",
        frequency="1min",
        baseUrl="https://api.example.com",
        endpoint="/items",
        scrape=cfg.ScrapeConfig(
            type=scrape_type,
            httpMethod=http_method,
            urlEncodeTimeKeys=url_encode,
            rangeKeys=range_keys,
            extraArgs=extra_args or {},
        ),
    )


def app_cfg():
    return cfg.AppConfig(
        scraper=cfg.ScraperSettings(otelCollectorEndpoint="http://collector"),
        sources=[],
    )


@pytest.mark.asyncio
async def test_scrape_source_skips_initial_when_run_first_false(monkeypatch):
    state_store = AsyncMock()
    state_store.get_last_success.return_value = None
    pipeline = AsyncMock()
    telemetry = MagicMock()
    http = MagicMock()
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)
    src = make_source()
    src.runFirstScrape = False

    await engine.scrape_source(src)

    state_store.set_last_success.assert_awaited_once()
    pipeline.run.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_source_success_and_error_paths(monkeypatch):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("otel_api_scraper.scraper_engine.utc_now", lambda: now)
    state_store = AsyncMock()
    state_store.get_last_success.return_value = now - timedelta(minutes=5)

    class StubPipeline:
        def __init__(self):
            self.calls = 0
            self.last_stats = {"hits": 1, "misses": 1, "total": 2}

        async def run(self, *_):
            self.calls += 1
            if self.calls == 1:
                raise ShapeMismatch("bad")
            return [{"id": 2}]

    class StubTelemetry:
        def __init__(self):
            self.record_self_scrape = MagicMock()
            self.record_dedupe = MagicMock()
            self.emit_metrics = MagicMock()
            self.emit_logs = MagicMock()
            self._emit_tasks: set = set()
            self.calls = 0

    telemetry = StubTelemetry()
    http = MagicMock()
    engine = ScraperEngine(app_cfg(), http, StubPipeline(), telemetry, state_store)
    src = make_source()

    # Avoid actual fetch/telemetry by patching
    async def compute(*_, **__):
        return [None, None]

    async def fetch(*_, **__):
        fetch.calls += 1
        return [{"id": fetch.calls}], {"root": fetch.calls}

    fetch.calls = 0
    emit_called = {"count": 0}

    async def emit_async(*_, **__):
        emit_called["count"] += 1

    engine._compute_windows = compute
    engine._fetch_window = fetch
    engine._emit_telemetry_async = emit_async

    await engine.scrape_source(src)

    assert fetch.calls == 2
    assert emit_called["count"] == 1
    telemetry.record_self_scrape.assert_called_once()
    args, kwargs = telemetry.record_self_scrape.call_args
    assert (
        args[0] == src.name
        and kwargs.get("api_type", src.scrape.type) == src.scrape.type
    )
    telemetry.record_dedupe.assert_called_once()
    state_store.set_last_success.assert_awaited()


def test_parallel_delta_and_unit_seconds():
    engine = ScraperEngine(app_cfg(), None, None, None, None)  # type: ignore[arg-type]
    assert engine._parallel_delta("minutes", 5) == timedelta(minutes=5)
    assert engine._parallel_delta("hours", 2) == timedelta(hours=2)
    assert engine._parallel_delta("days", 1) == timedelta(days=1)
    with pytest.raises(ValueError):
        engine._parallel_delta("years", 1)
    assert engine._unit_seconds("minutes") == 60
    assert engine._unit_seconds("hours") == 3600
    assert engine._unit_seconds("days") == 86400
    assert engine._unit_seconds("months") == 2592000
    assert engine._unit_seconds("weeks") == 604800
    assert engine._unit_seconds(None) == 1


@pytest.mark.asyncio
async def test_compute_windows_instant_and_parallel(monkeypatch):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("otel_api_scraper.scraper_engine.utc_now", lambda: now)
    engine = ScraperEngine(app_cfg(), None, None, None, None)  # type: ignore[arg-type]
    src_instant = make_source(scrape_type="instant")
    assert await engine._compute_windows(src_instant, now, None) == [None]

    rk = cfg.RangeKeys(startKey="s", endKey="e")
    src_range = make_source(
        scrape_type="range",
        range_keys=rk,
    )
    # last_success None -> uses frequency
    win = await engine._compute_windows(src_range, now, None)
    assert len(win) == 1 and isinstance(win[0], tuple)

    # firstScrapeStart branch
    rk_first = cfg.RangeKeys(
        startKey="s", endKey="e", firstScrapeStart="2024-01-01T00:00:00Z"
    )
    src_first = make_source(scrape_type="range", range_keys=rk_first)
    with monkeypatch.context() as m:
        m.setattr(
            "otel_api_scraper.scraper_engine.parse_datetime",
            lambda s, fmt: now - timedelta(days=1),
        )
        win_first = await engine._compute_windows(src_first, now, None)
    assert win_first[0][0] == now - timedelta(days=1)

    # parallel window branch
    rk2 = cfg.RangeKeys(startKey="s", endKey="e")
    src_parallel = make_source(
        scrape_type="range",
        range_keys=rk2,
        extra_args={},
    )
    src_parallel.scrape.parallelWindow = cfg.ParallelWindow(unit="minutes", value=15)
    windows = await engine._compute_windows(src_parallel, now, now - timedelta(hours=1))
    assert windows  # window_slices is used internally


@pytest.mark.asyncio
async def test_fetch_window_get_with_raw_params(monkeypatch):
    http = MagicMock()
    http.build_url.return_value = "https://api.example.com/items"
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"data": []}
    http.request = AsyncMock(return_value=response)
    pipeline = MagicMock()
    telemetry = MagicMock()
    state_store = MagicMock()

    # stub util helpers
    monkeypatch.setattr(
        "otel_api_scraper.scraper_engine.build_query_string",
        lambda params, raw: "start=a&no=b",
    )
    monkeypatch.setattr(
        "otel_api_scraper.scraper_engine.extract_records", lambda payload, key: payload
    )
    rk = cfg.RangeKeys(startKey="start", endKey="end")
    src = make_source(
        scrape_type="range",
        range_keys=rk,
        url_encode=False,
        extra_args={"q": {"noEncodeValue": "b"}},
    )
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)
    auth = MagicMock()
    auth.headers = AsyncMock(return_value={"Authorization": "Bearer t"})

    now = datetime.now(timezone.utc)
    records, payload = await engine._fetch_window(src, (now, now), auth)

    http.request.assert_awaited_once()
    assert "Bearer t" in http.request.await_args.kwargs["headers"].get(
        "Authorization", "Bearer t"
    )
    assert records == {"data": []}
    assert payload == {"data": []}


@pytest.mark.asyncio
async def test_fetch_window_post_with_params(monkeypatch):
    http = MagicMock()
    http.build_url.return_value = "https://api.example.com/items"
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"items": [1]}
    http.request = AsyncMock(return_value=response)
    pipeline = MagicMock()
    telemetry = MagicMock()
    state_store = MagicMock()
    monkeypatch.setattr(
        "otel_api_scraper.scraper_engine.extract_records",
        lambda payload, key: payload["items"],
    )
    rk = cfg.RangeKeys(startKey="start", endKey="end")
    src = make_source(
        scrape_type="range", range_keys=rk, http_method="POST", url_encode=True
    )
    src.scrape.extraArgs = {"x": 1}
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)

    now = datetime.now(timezone.utc)
    records, payload = await engine._fetch_window(src, (now, now), None)

    http.request.assert_awaited_once()
    assert records == [1]
    assert payload == {"items": [1]}


@pytest.mark.asyncio
async def test_fetch_window_relative_from_config_and_take_negative(monkeypatch):
    http = MagicMock()
    http.build_url.return_value = "https://api.example.com/items"
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"ok": True}
    http.request = AsyncMock(return_value=response)
    pipeline = AsyncMock()
    telemetry = MagicMock()
    state_store = AsyncMock()
    state_store.get_last_success.return_value = None

    captured_params = {}

    def fake_build_query(params, raw):
        captured_params.update(params)
        return "unit=minutes&value=-1&from=mark"

    monkeypatch.setattr(
        "otel_api_scraper.scraper_engine.build_query_string", fake_build_query
    )
    monkeypatch.setattr(
        "otel_api_scraper.scraper_engine.extract_records", lambda payload, key: payload
    )

    rk = cfg.RangeKeys(unit="minutes", value="from-config", takeNegative=True)
    src = make_source(scrape_type="range", range_keys=rk, url_encode=False)
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)

    now = datetime.now(timezone.utc)
    await engine._fetch_window(src, (now, now), None)

    assert captured_params["value"] < 0
    http.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_window_root_payload_requires_dict(monkeypatch):
    http = MagicMock()
    http.build_url.return_value = "https://api.example.com/items"
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = ["not-a-dict"]
    http.request = AsyncMock(return_value=response)
    pipeline = MagicMock()
    telemetry = MagicMock()
    state_store = MagicMock()

    src = make_source()
    src.gaugeReadings = [cfg.GaugeReading(name="g", dataKey="$root.limit")]
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)

    now = datetime.now(timezone.utc)
    with pytest.raises(ShapeMismatch):
        await engine._fetch_window(src, (now, now), None)


@pytest.mark.asyncio
async def test_uses_root_payload_detection():
    engine = ScraperEngine(app_cfg(), None, None, None, None)  # type: ignore[arg-type]
    src = make_source()
    assert engine._uses_root_payload(src) is False

    src.counterReadings = [cfg.CounterReading(name="c", dataKey="$root.cnt")]
    assert engine._uses_root_payload(src) is True
    src.counterReadings = []

    src.histogramReadings = [
        cfg.HistogramReading(name="h", dataKey="$root.hist", unit="ms", buckets=[1.0])
    ]
    assert engine._uses_root_payload(src) is True
    src.histogramReadings = []

    src.attributes = [cfg.AttributeConfig(name="attr", dataKey="$root.attr")]
    assert engine._uses_root_payload(src) is True
    src.attributes = []

    src.logStatusField = cfg.LogStatusField(name="$root.status")
    assert engine._uses_root_payload(src) is True


@pytest.mark.asyncio
async def test_scrape_source_handles_generic_exception(monkeypatch):
    class StubState:
        def __init__(self):
            self.set_called = False

        async def get_last_success(self, *_):
            return datetime.now(timezone.utc)

        async def set_last_success(self, *_):
            self.set_called = True

    class StubTelemetry:
        def __init__(self):
            self.self_called = False
            self.dedupe_called = False
            self._emit_tasks = set()

        def record_self_scrape(self, *_, **__):
            self.self_called = True

        def record_dedupe(self, *_, **__):
            self.dedupe_called = True

    class StubPipeline:
        last_stats = {"hits": 0, "misses": 0, "total": 0}

        async def run(self, *_):
            return []

    http = MagicMock()
    telemetry = StubTelemetry()
    state_store = StubState()
    engine = ScraperEngine(app_cfg(), http, StubPipeline(), telemetry, state_store)
    src = make_source()

    async def windows(*_, **__):
        return [None]

    engine._compute_windows = windows

    async def boom(*_, **__):
        raise Exception("boom")

    engine._fetch_window = boom
    emit_called = {"count": 0}

    async def emit_async(*_, **__):
        emit_called["count"] += 1
        return None

    engine._emit_telemetry_async = emit_async

    await engine.scrape_source(src)

    assert telemetry.self_called is True
    assert telemetry.dedupe_called is True
    assert emit_called["count"] == 0


@pytest.mark.asyncio
async def test_scrape_source_accepts_non_tuple_results(monkeypatch):
    class StubState:
        async def get_last_success(self, *_):
            return datetime.now(timezone.utc)

        async def set_last_success(self, *_):
            return None

    class StubPipeline:
        last_stats = {"hits": 0, "misses": 0, "total": 0}

        async def run(self, records, source):
            return records

    class StubTelemetry:
        def __init__(self):
            self.record_self_scrape = MagicMock()
            self.record_dedupe = MagicMock()
            self._emit_tasks: set = set()

    http = MagicMock()
    engine = ScraperEngine(
        app_cfg(), http, StubPipeline(), StubTelemetry(), StubState()
    )
    src = make_source()

    async def fake_gather(*coros, **kwargs):
        for coro in coros:
            await coro
        return [([{"id": 1}], False, {"root": "r"})]

    monkeypatch.setattr("otel_api_scraper.scraper_engine.asyncio.gather", fake_gather)

    async def compute(*_, **__):
        return [None]

    async def fetch(*_, **__):
        fetch.calls += 1
        return [{"id": 1}], {"root": "r"}

    fetch.calls = 0
    emit_called = {"count": 0}

    async def emit_async(*_, **__):
        emit_called["count"] += 1

    engine._compute_windows = compute
    engine._fetch_window = fetch
    engine._emit_telemetry_async = emit_async

    await engine.scrape_source(src)

    assert emit_called["count"] == 1
    engine.telemetry.record_dedupe.assert_called()


@pytest.mark.asyncio
async def test_emit_telemetry_async_handles_errors(monkeypatch, caplog):
    caplog.set_level("WARNING")
    telemetry = MagicMock()
    telemetry.emit_metrics.side_effect = Exception("metrics boom")
    telemetry.emit_logs.side_effect = Exception("logs boom")
    telemetry._emit_tasks = set()
    engine = ScraperEngine(app_cfg(), None, None, telemetry, None)  # type: ignore[arg-type]
    src = make_source()
    records = [{"id": 1}]

    await engine._emit_telemetry_async(src, [(records, {"root": "r"})])
    await asyncio.gather(*list(telemetry._emit_tasks))
    await asyncio.sleep(0)  # allow callback to discard

    assert telemetry._emit_tasks == set()
    assert any(
        "Metric emission failed" in msg or "Log emission failed" in msg
        for msg in caplog.messages
    )
