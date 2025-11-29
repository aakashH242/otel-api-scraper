import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, ANY

import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper import runner


def minimal_app_config(enable_admin=False) -> cfg.AppConfig:
    scraper = cfg.ScraperSettings(
        otelCollectorEndpoint="http://collector",
        enableAdminApi=enable_admin,
        adminSecretEnv=None if enable_admin else None,
    )
    source = cfg.SourceConfig(
        name="svc",
        frequency="1min",
        baseUrl="http://example.com",
        endpoint="/items",
        scrape=cfg.ScrapeConfig(type="instant"),
    )
    return cfg.AppConfig(scraper=scraper, sources=[source])


@pytest.mark.asyncio
async def test_cleanup_loop_runs_and_handles_errors(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    calls = {"cleanup": 0}

    class Store:
        async def cleanup(self):
            calls["cleanup"] += 1
            if calls["cleanup"] == 1:
                raise Exception("fail once")

    async def fake_sleep(interval):
        # allow first iteration then stop loop
        if calls["cleanup"] > 0:
            raise asyncio.CancelledError()
        return None

    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    store = Store()
    telemetry = MagicMock()
    await runner._cleanup_loop(store, 1, telemetry, "backend")
    assert calls["cleanup"] == 1
    assert any("Cleanup loop error" in msg for msg in caplog.messages)
    telemetry.record_cleanup.assert_called()


@pytest.mark.asyncio
async def test_cleanup_loop_logs_success(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    calls = {"cleanup": 0}

    class Store:
        async def cleanup(self):
            calls["cleanup"] += 1

    async def fake_sleep(interval):
        if calls["cleanup"] >= 1:
            raise asyncio.CancelledError()
        return None

    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    telemetry = MagicMock()
    await runner._cleanup_loop(Store(), 1, telemetry, "backend")

    assert calls["cleanup"] == 1
    telemetry.record_cleanup.assert_called()
    assert any("Ran fingerprint cleanup cycle" in msg for msg in caplog.messages)


@pytest.mark.asyncio
async def test_cleanup_loop_records_cleaned_count(monkeypatch):
    class Store:
        async def cleanup(self):
            return 3

    async def fake_sleep(interval):
        if getattr(fake_sleep, "called", False):
            raise asyncio.CancelledError()
        fake_sleep.called = True
        return None

    telemetry = MagicMock()
    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    await runner._cleanup_loop(Store(), 1, telemetry, "backend")
    telemetry.record_cleanup.assert_called_with(
        "fingerprint_cleanup", "backend", ANY, 3
    )


@pytest.mark.asyncio
async def test_async_main_happy_path(monkeypatch):
    app_config = minimal_app_config()
    mock_store = AsyncMock()
    mock_state_store = AsyncMock()
    mock_pipeline = MagicMock()
    mock_telemetry = AsyncMock()
    mock_telemetry.record_cleanup = MagicMock()
    mock_http = AsyncMock()
    mock_engine = MagicMock()
    mock_scheduler = MagicMock()
    mock_scheduler.run_all_once = AsyncMock()
    mock_scheduler.shutdown = AsyncMock()

    async def fake_cleanup_loop(store, interval, telemetry, backend):
        return None

    async def fake_sleep(seconds):
        # trigger cancellation path immediately
        raise asyncio.CancelledError()

    monkeypatch.setattr(runner, "load_config", lambda path: app_config)
    monkeypatch.setattr(runner, "build_store", lambda cfg_obj: mock_store)
    monkeypatch.setattr(runner, "build_state_store", lambda cfg_obj: mock_state_store)
    monkeypatch.setattr(runner, "RecordPipeline", lambda store, cfg_obj: mock_pipeline)
    monkeypatch.setattr(runner, "Telemetry", lambda cfg_obj: mock_telemetry)
    monkeypatch.setattr(
        runner, "AsyncHttpClient", lambda max_conc, enforce_tls: mock_http
    )
    monkeypatch.setattr(runner, "ScraperEngine", lambda *args, **kwargs: mock_engine)
    monkeypatch.setattr(
        runner, "ScraperScheduler", lambda *args, **kwargs: mock_scheduler
    )
    monkeypatch.setattr(runner, "_cleanup_loop", fake_cleanup_loop)
    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)

    await runner.async_main("config.yaml")

    mock_store.cleanup_orphans.assert_awaited_once()
    mock_scheduler.start.assert_called_once()
    mock_scheduler.run_all_once.assert_awaited_once()
    mock_scheduler.shutdown.assert_awaited_once()
    mock_http.close.assert_awaited_once()
    mock_telemetry.shutdown.assert_awaited_once()
    mock_store.close.assert_awaited_once()
    mock_state_store.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_main_admin_api_env_validation(monkeypatch):
    app_config = minimal_app_config(enable_admin=True)
    app_config.scraper.adminSecretEnv = None
    monkeypatch.setattr(runner, "load_config", lambda path: app_config)
    with pytest.raises(ValueError):
        await runner.async_main("config.yaml")

    app_config.scraper.adminSecretEnv = "ADMIN_SECRET"
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    with pytest.raises(ValueError):
        await runner.async_main("config.yaml")


def test_main_handles_file_not_found(monkeypatch, capsys):
    monkeypatch.setenv("SCRAPER_CONFIG", "/missing.yaml")

    def fake_run(coro):
        coro.close()
        raise FileNotFoundError("missing")

    monkeypatch.setattr(runner.asyncio, "run", fake_run)
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 1
    assert "Config file not found" in capsys.readouterr().err


def test_main_re_raises_other_errors(monkeypatch):
    monkeypatch.setenv("SCRAPER_CONFIG", "config.yaml")

    def fake_run(coro):
        coro.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(runner.asyncio, "run", fake_run)
    with pytest.raises(RuntimeError):
        runner.main()


@pytest.mark.asyncio
async def test_admin_api_done_callback_raises(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    app_config = minimal_app_config(enable_admin=True)
    app_config.scraper.adminSecretEnv = "ADMIN_SECRET"
    monkeypatch.setenv("ADMIN_SECRET", "secret")

    # configure dependencies
    admin_app = object()
    monkeypatch.setattr(runner, "load_config", lambda path: app_config)
    monkeypatch.setattr(runner, "build_store", lambda cfg_obj: AsyncMock())
    monkeypatch.setattr(runner, "build_state_store", lambda cfg_obj: AsyncMock())
    monkeypatch.setattr(runner, "RecordPipeline", lambda store, cfg_obj: MagicMock())
    mock_telemetry = AsyncMock()
    mock_telemetry.record_cleanup = MagicMock()
    monkeypatch.setattr(runner, "Telemetry", lambda cfg_obj: mock_telemetry)
    monkeypatch.setattr(
        runner, "AsyncHttpClient", lambda max_conc, enforce_tls: AsyncMock()
    )
    monkeypatch.setattr(runner, "ScraperEngine", lambda *args, **kwargs: MagicMock())
    mock_scheduler = MagicMock()
    mock_scheduler.run_all_once = AsyncMock()
    mock_scheduler.shutdown = AsyncMock()
    mock_scheduler.start = MagicMock()
    monkeypatch.setattr(
        runner, "ScraperScheduler", lambda *args, **kwargs: mock_scheduler
    )

    async def fake_cleanup(*args, **kwargs):
        return None

    monkeypatch.setattr(runner, "_cleanup_loop", fake_cleanup)
    monkeypatch.setattr(
        runner.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError())
    )

    class FakeServer:
        async def serve(self):
            return None

    class FakeConfig:
        def __init__(self, *_, **__):
            pass

    monkeypatch.setattr(runner, "build_admin_app", lambda *args, **kwargs: admin_app)
    monkeypatch.setattr(runner.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(runner.uvicorn, "Server", lambda cfg: FakeServer())

    await runner.async_main("config.yaml")


def test_main_loads_dotenv(monkeypatch, tmp_path):
    called = {}

    def fake_run(coro):
        coro.close()
        called["run"] = True

    monkeypatch.setenv("SCRAPER_CONFIG", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(
        runner, "load_dotenv", lambda: called.setdefault("dotenv", True)
    )
    monkeypatch.setattr(runner.asyncio, "run", fake_run)
    runner.main()
    assert called["dotenv"] is True
    assert called["run"] is True


@pytest.mark.asyncio
async def test_async_main_with_admin_api(monkeypatch):
    app_config = minimal_app_config(enable_admin=True)
    app_config.scraper.adminSecretEnv = "ADMIN_SECRET"
    app_config.scraper.servicePort = 9000
    monkeypatch.setenv("ADMIN_SECRET", "secret")

    mock_store = AsyncMock()
    mock_state_store = AsyncMock()
    mock_pipeline = MagicMock()
    mock_telemetry = AsyncMock()
    mock_telemetry.record_cleanup = MagicMock()
    mock_http = AsyncMock()
    mock_engine = MagicMock()
    mock_scheduler = MagicMock()
    mock_scheduler.run_all_once = AsyncMock()
    mock_scheduler.shutdown = AsyncMock()

    async def fake_cleanup_loop(store, interval, telemetry, backend):
        return None

    async def fake_sleep(seconds):
        raise asyncio.CancelledError()

    class FakeServer:
        async def serve(self):
            return None

    class FakeConfig:
        def __init__(self, *args, **kwargs):
            self.args = args

    monkeypatch.setattr(runner, "load_config", lambda path: app_config)
    monkeypatch.setattr(runner, "build_store", lambda cfg_obj: mock_store)
    monkeypatch.setattr(runner, "build_state_store", lambda cfg_obj: mock_state_store)
    monkeypatch.setattr(runner, "RecordPipeline", lambda store, cfg_obj: mock_pipeline)
    monkeypatch.setattr(runner, "Telemetry", lambda cfg_obj: mock_telemetry)
    monkeypatch.setattr(
        runner, "AsyncHttpClient", lambda max_conc, enforce_tls: mock_http
    )
    monkeypatch.setattr(runner, "ScraperEngine", lambda *args, **kwargs: mock_engine)
    monkeypatch.setattr(
        runner, "ScraperScheduler", lambda *args, **kwargs: mock_scheduler
    )
    monkeypatch.setattr(runner, "_cleanup_loop", fake_cleanup_loop)
    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(runner, "build_admin_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(runner.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(runner.uvicorn, "Server", lambda cfg: FakeServer())

    await runner.async_main("config.yaml")

    mock_scheduler.start.assert_called_once()
    mock_scheduler.run_all_once.assert_awaited_once()
    mock_scheduler.shutdown.assert_awaited_once()
    mock_store.cleanup_orphans.assert_awaited_once()
