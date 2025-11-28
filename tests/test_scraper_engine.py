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
    src.scrape.runFirstScrape = False

    await engine.scrape_source(src)

    state_store.set_last_success.assert_awaited_once()
    pipeline.run.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_source_success_and_error_paths(monkeypatch):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("otel_api_scraper.scraper_engine.utc_now", lambda: now)
    state_store = AsyncMock()
    state_store.get_last_success.return_value = now - timedelta(minutes=5)
    pipeline = AsyncMock()
    pipeline.run.side_effect = [ShapeMismatch("bad"), [{"id": 2}]]
    telemetry = MagicMock()
    telemetry.record_self_scrape = MagicMock()
    telemetry.record_dedupe = MagicMock()
    telemetry.emit_metrics = MagicMock()
    telemetry.emit_logs = MagicMock()
    telemetry._emit_tasks = set()
    http = MagicMock()
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)
    src = make_source()
    # Avoid actual fetch/telemetry by patching
    engine._compute_windows = AsyncMock(return_value=[None, None])
    engine._fetch_window = AsyncMock(side_effect=[[{"id": 1}], [{"id": 2}]])
    engine._emit_telemetry_async = AsyncMock()

    await engine.scrape_source(src)

    assert engine._fetch_window.await_count == 2
    engine._emit_telemetry_async.assert_awaited_once()
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
    records = await engine._fetch_window(src, (now, now), auth)

    http.request.assert_awaited_once()
    assert "Bearer t" in http.request.await_args.kwargs["headers"].get(
        "Authorization", "Bearer t"
    )
    assert records == {"data": []}


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
    records = await engine._fetch_window(src, (now, now), None)

    http.request.assert_awaited_once()
    assert records == [1]


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
    object.__setattr__(
        rk, "secondFirstScrapeStart", "mark"
    )  # inject optional attr for branch coverage
    src = make_source(scrape_type="range", range_keys=rk, url_encode=False)
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)

    now = datetime.now(timezone.utc)
    await engine._fetch_window(src, (now, now), None)

    assert captured_params["value"] < 0
    http.request.assert_awaited_once()
    state_store.get_last_success.assert_awaited()


@pytest.mark.asyncio
async def test_scrape_source_handles_generic_exception(monkeypatch):
    state_store = AsyncMock()
    state_store.get_last_success.return_value = datetime.now(timezone.utc)
    pipeline = AsyncMock()
    telemetry = MagicMock()
    telemetry.record_self_scrape = MagicMock()
    telemetry.record_dedupe = MagicMock()
    telemetry._emit_tasks = set()
    http = MagicMock()
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)
    src = make_source()

    engine._compute_windows = AsyncMock(return_value=[None])
    engine._fetch_window = AsyncMock(side_effect=Exception("boom"))
    engine._emit_telemetry_async = AsyncMock()

    await engine.scrape_source(src)

    telemetry.record_self_scrape.assert_called()
    telemetry.record_dedupe.assert_called()
    engine._emit_telemetry_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_scrape_source_accepts_non_tuple_results(monkeypatch):
    state_store = AsyncMock()
    state_store.get_last_success.return_value = datetime.now(timezone.utc)
    pipeline = AsyncMock()
    telemetry = MagicMock()
    telemetry.record_self_scrape = MagicMock()
    telemetry.record_dedupe = MagicMock()
    telemetry._emit_tasks = set()
    http = MagicMock()
    engine = ScraperEngine(app_cfg(), http, pipeline, telemetry, state_store)
    src = make_source()

    async def fake_gather(*coros, **kwargs):
        for coro in coros:
            await coro
        return [[{"id": 1}]]

    monkeypatch.setattr("otel_api_scraper.scraper_engine.asyncio.gather", fake_gather)
    engine._compute_windows = AsyncMock(return_value=[None])
    engine._fetch_window = AsyncMock(return_value=[{"id": 1}])
    engine._emit_telemetry_async = AsyncMock()

    await engine.scrape_source(src)

    engine._emit_telemetry_async.assert_awaited_once()
    telemetry.record_dedupe.assert_called()


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

    await engine._emit_telemetry_async(src, records)
    await asyncio.gather(*list(telemetry._emit_tasks))
    await asyncio.sleep(0)  # allow callback to discard

    assert telemetry._emit_tasks == set()
    assert any(
        "Metric emission failed" in msg or "Log emission failed" in msg
        for msg in caplog.messages
    )
