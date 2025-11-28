from datetime import datetime, timezone

import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper.state import (
    MemoryStateStore,
    SqliteStateStore,
    ValkeyStateStore,
    build_state_store,
)


@pytest.mark.asyncio
async def test_memory_state_store_roundtrip():
    store = MemoryStateStore()
    assert await store.get_last_success("svc") is None
    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await store.set_last_success("svc", when)
    assert await store.get_last_success("svc") == when
    await store.close()


@pytest.mark.asyncio
async def test_sqlite_state_store_roundtrip(tmp_path):
    path = tmp_path / "state.db"
    store = SqliteStateStore(str(path))
    assert await store.get_last_success("svc") is None
    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await store.set_last_success("svc", when)
    value = await store.get_last_success("svc")
    assert value == when
    await store.close()


class FakeValkey:
    def __init__(self, *args, **kwargs):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_valkey_state_store_roundtrip(monkeypatch):
    import importlib

    fake_module = type("M", (), {"Valkey": FakeValkey, "Redis": None})
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)
    store = ValkeyStateStore(cfg.FingerprintStoreValkey())
    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await store.set_last_success("svc", when)
    assert await store.get_last_success("svc") == when
    await store.close()


@pytest.mark.asyncio
async def test_valkey_state_store_missing_client(monkeypatch):
    import importlib

    fake_module = type("M", (), {"Valkey": None, "Redis": None})
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)
    with pytest.raises(RuntimeError):
        ValkeyStateStore(cfg.FingerprintStoreValkey())


@pytest.mark.asyncio
async def test_valkey_state_store_bad_value(monkeypatch):
    import importlib

    fake_module = type("M", (), {"Valkey": FakeValkey, "Redis": None})
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)
    store = ValkeyStateStore(cfg.FingerprintStoreValkey())
    # set invalid isoformat string
    store.client.data[store._key("svc")] = "not-a-date"
    assert await store.get_last_success("svc") is None
    await store.close()


def test_build_state_store_variants(monkeypatch, tmp_path):
    sqlite_cfg = cfg.FingerprintStoreConfig(
        backend="sqlite",
        sqlite=cfg.FingerprintStoreSqlite(path=str(tmp_path / "state.db")),
    )
    store_sqlite = build_state_store(sqlite_cfg)
    assert isinstance(store_sqlite, SqliteStateStore)

    # valkey fallback to memory on exception
    monkeypatch.setattr(
        "otel_api_scraper.state.ValkeyStateStore",
        lambda cfg_obj: (_ for _ in ()).throw(RuntimeError("no valkey")),
    )
    valkey_cfg = cfg.FingerprintStoreConfig(backend="valkey")
    store_valkey = build_state_store(valkey_cfg)
    assert isinstance(store_valkey, MemoryStateStore)
