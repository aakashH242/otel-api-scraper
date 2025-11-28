from fastapi.testclient import TestClient

from otel_api_scraper import config as cfg
from otel_api_scraper.admin_api import build_admin_app


def _sample_app_config():
    scraper = cfg.ScraperSettings(otelCollectorEndpoint="http://collector")
    source_base = dict(
        frequency="5m",
        scrape=cfg.ScrapeConfig(type="instant"),
        endpoint="/items",
        baseUrl="https://api.example.com",
    )
    sources = [
        cfg.SourceConfig(name="alpha", **source_base),
        cfg.SourceConfig(name="bravo", **source_base | {"endpoint": "/bravo"}),
    ]
    return cfg.AppConfig(scraper=scraper, sources=sources)


class FakeEngine:
    def __init__(self):
        self.scraped = None

    async def scrape_source(self, source):
        self.scraped = source


def test_health_endpoint():
    engine = FakeEngine()
    app = build_admin_app(_sample_app_config(), engine)
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_list_sources():
    engine = FakeEngine()
    app_config = _sample_app_config()
    app = build_admin_app(app_config, engine)
    with TestClient(app) as client:
        resp = client.get("/sources")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) == 2
        assert payload[0]["name"] == "alpha"
        assert payload[1]["frequency"] == "5m"


def test_get_source_success_and_not_found():
    engine = FakeEngine()
    app_config = _sample_app_config()
    app = build_admin_app(app_config, engine)
    with TestClient(app) as client:
        ok = client.get("/sources/alpha")
        assert ok.status_code == 200
        assert ok.json()["name"] == "alpha"

        missing = client.get("/sources/missing")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Source not found"


def test_run_source_triggers_engine_or_404():
    engine = FakeEngine()
    app_config = _sample_app_config()
    app = build_admin_app(app_config, engine)
    with TestClient(app) as client:
        resp = client.post("/sources/alpha/scrape")
        assert resp.status_code == 200
        assert resp.json() == {"status": "triggered"}
        assert engine.scraped.name == "alpha"

        missing = client.post("/sources/missing/scrape")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Source not found"
