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


@pytest.mark.asyncio
async def test_sqlite_state_store_retries_on_lock(monkeypatch):
    import aiosqlite

    class FakeDB:
        def __init__(self):
            self.calls = 0
            self.committed = False

        async def execute(self, sql, params):
            self.calls += 1
            if self.calls == 1:
                raise aiosqlite.OperationalError("database is locked")
            self.sql = sql
            self.params = params

        async def commit(self):
            self.committed = True

    fake_db = FakeDB()

    async def fake_ensure(self):
        return fake_db

    store = SqliteStateStore("ignored.db")
    monkeypatch.setattr(store, "_ensure", fake_ensure.__get__(store, SqliteStateStore))

    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await store.set_last_success("svc", when)

    assert fake_db.calls == 2
    assert fake_db.committed is True


@pytest.mark.asyncio
async def test_sqlite_state_store_raises_on_non_lock(monkeypatch):
    import aiosqlite

    class FakeDB:
        async def execute(self, sql, params):
            raise aiosqlite.OperationalError("other failure")

        async def commit(self):
            raise AssertionError("should not commit on failure")

    store = SqliteStateStore("ignored.db", lock_retries=1)

    async def fake_ensure(self):
        return FakeDB()

    monkeypatch.setattr(store, "_ensure", fake_ensure.__get__(store, SqliteStateStore))

    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(aiosqlite.OperationalError):
        await store.set_last_success("svc", when)


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

    class FakeValkeyWithPwd(FakeValkey):
        def __init__(self, *args, password=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.pwd = password

    fake_module = type("M", (), {"Valkey": FakeValkeyWithPwd, "Redis": None})
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)
    monkeypatch.setenv("VALKEY_ENV_PWD", "supersecret")
    store = ValkeyStateStore(cfg.FingerprintStoreValkey(password="VALKEY_ENV_PWD"))
    when = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await store.set_last_success("svc", when)
    assert await store.get_last_success("svc") == when
    assert store.client.pwd == "supersecret"
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
    # missing key returns None (covers falsy branch)
    assert await store.get_last_success("missing") is None
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

    import types

    other_cfg = types.SimpleNamespace(
        backend="memory",
        lockRetries=1,
        lockBackoffSeconds=0.1,
        sqlite=cfg.FingerprintStoreSqlite(path=":memory:"),
        valkey=cfg.FingerprintStoreValkey(),
    )
    store_other = build_state_store(other_cfg)  # type: ignore[arg-type]
    assert isinstance(store_other, MemoryStateStore)
