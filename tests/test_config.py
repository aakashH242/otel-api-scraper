from pathlib import Path

import pytest
import yaml

from otel_api_scraper import config as cfg


def write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def minimal_source(scrape_type: str = "instant") -> dict:
    return {
        "name": "demo",
        "frequency": "1min",
        "baseUrl": "http://example.com",
        "endpoint": "/status",
        "scrape": {"type": scrape_type},
    }


def test_load_config_resolves_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("API_KEY", "secret123")
    data = {
        "scraper": {"otelCollectorEndpoint": "http://collector:4317"},
        "sources": [
            {
                **minimal_source(),
                "auth": {
                    "type": "apikey",
                    "keyName": "X-API-Key",
                    "keyValue": "${API_KEY}",
                },
            }
        ],
    }
    path = write_config(tmp_path, data)
    loaded = cfg.load_config(path)
    auth = loaded.sources[0].auth
    assert auth is not None
    assert getattr(auth, "keyValue") == "secret123"


def test_range_scrape_requires_range_keys(tmp_path: Path):
    data = {
        "scraper": {"otelCollectorEndpoint": "http://collector:4317"},
        "sources": [
            {
                **minimal_source(scrape_type="range"),
            }
        ],
    }
    path = write_config(tmp_path, data)
    with pytest.raises(ValueError):
        cfg.load_config(path)


def test_fingerprint_backend_alias_redis(tmp_path: Path):
    data = {
        "scraper": {
            "otelCollectorEndpoint": "http://collector:4317",
            "fingerprintStore": {"backend": "redis"},
        },
        "sources": [minimal_source()],
    }
    path = write_config(tmp_path, data)
    loaded = cfg.load_config(path)
    assert loaded.scraper.fingerprintStore.backend == "valkey"


def test_oauth_validation_requires_token_or_runtime():
    with pytest.raises(ValueError):
        cfg.OAuthAuthConfig(
            type="oauth",
            token=None,
            username=None,
            password=None,
            getTokenEndpoint=None,
            tokenKey=None,
        )


def test_range_keys_helpers():
    rk = cfg.RangeKeys(unit="days", startKey="start", endKey="end")
    assert rk.is_relative() is True
    assert rk.has_explicit_bounds() is True

    rk2 = cfg.RangeKeys()
    assert rk2.is_relative() is False
    assert rk2.has_explicit_bounds() is False


def test_scrape_config_validates_parallel_window_and_concurrency():
    with pytest.raises(ValueError):
        cfg.ScrapeConfig(
            type="instant", parallelWindow=cfg.ParallelWindow(unit="minutes", value=5)
        )
    with pytest.raises(ValueError):
        cfg.ScrapeConfig(type="instant", maxConcurrency=0)
    # Should allow rangeKeys on instant without raising (covers 'pass' branch).
    rk = cfg.RangeKeys(startKey="s", endKey="e")
    cfg.ScrapeConfig(type="instant", rangeKeys=rk)


def test_scraper_settings_concurrency_validation():
    with pytest.raises(ValueError):
        cfg.ScraperSettings(
            otelCollectorEndpoint="http://collector", maxGlobalConcurrency=0
        )
    with pytest.raises(ValueError):
        cfg.ScraperSettings(
            otelCollectorEndpoint="http://collector", defaultSourceConcurrency=0
        )


def test_fingerprint_redis_config_promotes_valkey():
    cfg_obj = cfg.FingerprintStoreConfig(
        backend="sqlite",
        redis=cfg.FingerprintStoreValkey(host="redis-host", port=1234, db=2, ssl=True),
    )
    assert cfg_obj.valkey.host == "redis-host"
    assert cfg_obj.valkey.port == 1234
    assert cfg_obj.valkey.db == 2
    assert cfg_obj.valkey.ssl is True


def test_load_config_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        cfg.load_config(missing)
