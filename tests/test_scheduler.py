import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper.scheduler import ScraperScheduler


class DummyEngine:
    def __init__(self):
        self.ran = []

    async def scrape_source(self, source):
        self.ran.append(source.name)


def sample_app_config(overlap=False):
    scraper = cfg.ScraperSettings(
        otelCollectorEndpoint="http://collector", allowOverlapScans=overlap
    )
    base_source = dict(
        frequency="2min",
        scrape=cfg.ScrapeConfig(type="instant"),
        endpoint="/x",
        baseUrl="https://api.example.com",
    )
    sources = [
        cfg.SourceConfig(name="a", **base_source),
        cfg.SourceConfig(name="b", allowOverlapScans=True, **base_source),
    ]
    return cfg.AppConfig(scraper=scraper, sources=sources)


def test_scheduler_start_registers_jobs_and_handles_overlap(monkeypatch):
    engine = DummyEngine()
    app_config = sample_app_config(overlap=False)
    scheduler = ScraperScheduler(app_config, engine)

    calls = []

    def fake_add_job(
        func, trigger, args, id, coalesce, max_instances, misfire_grace_time
    ):
        calls.append(
            dict(
                func=func,
                trigger=trigger,
                args=args,
                id=id,
                coalesce=coalesce,
                max_instances=max_instances,
                misfire_grace_time=misfire_grace_time,
            )
        )

    scheduler.scheduler.add_job = fake_add_job
    started = False

    def fake_start():
        nonlocal started
        started = True

    scheduler.scheduler.start = fake_start

    scheduler.start()

    assert started is True
    assert len(calls) == 2
    # Source a inherits allowOverlapScans=False from global
    first = calls[0]
    assert first["id"] == "a"
    assert first["coalesce"] is True
    assert first["max_instances"] == 1
    assert first["misfire_grace_time"] == 120
    # Source b overrides overlap
    second = calls[1]
    assert second["id"] == "b"
    assert second["coalesce"] is False
    assert second["max_instances"] == 999


def test_scheduler_invalid_frequency_raises(monkeypatch):
    engine = DummyEngine()
    scraper = cfg.ScraperSettings(otelCollectorEndpoint="http://collector")
    source = cfg.SourceConfig(
        name="bad",
        frequency="0min",
        scrape=cfg.ScrapeConfig(type="instant"),
        endpoint="/x",
        baseUrl="https://api.example.com",
    )
    app_config = cfg.AppConfig(scraper=scraper, sources=[source])
    scheduler = ScraperScheduler(app_config, engine)

    with pytest.raises(ValueError):
        scheduler.start()


@pytest.mark.asyncio
async def test_run_all_once_triggers_engine():
    engine = DummyEngine()
    app_config = sample_app_config()
    scheduler = ScraperScheduler(app_config, engine)

    await scheduler.run_all_once()

    assert set(engine.ran) == {"a", "b"}


@pytest.mark.asyncio
async def test_shutdown_invokes_scheduler_shutdown(monkeypatch):
    engine = DummyEngine()
    app_config = sample_app_config()
    scheduler = ScraperScheduler(app_config, engine)

    called = {}

    def fake_shutdown(wait=True):
        called["wait"] = wait

    scheduler.scheduler.shutdown = fake_shutdown

    await scheduler.shutdown(wait=False)

    assert called["wait"] is False


@pytest.mark.asyncio
async def test_run_source_invokes_engine():
    engine = DummyEngine()
    app_config = sample_app_config()
    scheduler = ScraperScheduler(app_config, engine)

    await scheduler._run_source(app_config.sources[0])
    assert engine.ran == ["a"]
