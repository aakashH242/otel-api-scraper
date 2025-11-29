import types
from datetime import datetime, timedelta

import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper.fingerprints import (
    FingerprintStore,
    MemoryFingerprintStore,
    SqliteFingerprintStore,
    ValkeyFingerprintStore,
    build_store,
)


@pytest.mark.asyncio
async def test_memory_store_contains_expiry_and_eviction(monkeypatch):
    current = datetime(2025, 1, 1)

    def now():
        return current

    monkeypatch.setattr("otel_api_scraper.fingerprints.utc_now", now)
    store = MemoryFingerprintStore(max_entries=2)

    assert not await store.contains("h1", "src", ttl_seconds=5)
    await store.touch("h1", "src", ttl_seconds=5)
    assert await store.contains("h1", "src", ttl_seconds=5)

    current = current + timedelta(seconds=10)
    assert not await store.contains("h1", "src", ttl_seconds=5)

    await store.touch("h1", "src", ttl_seconds=5)
    current = current + timedelta(seconds=1)
    await store.touch("h2", "src", ttl_seconds=5)
    current = current + timedelta(seconds=1)
    await store.touch("h3", "src", ttl_seconds=5)

    assert len(store.store["src"]) == 2
    assert "h1" not in store.store["src"]

    store.store["old"] = {"stale": current}
    await store.cleanup_orphans({"src"})
    assert "old" not in store.store
    await store.cleanup()


@pytest.mark.asyncio
async def test_sqlite_store_contains_touch_cleanup_and_capacity(tmp_path, monkeypatch):
    current = datetime(2025, 1, 1)

    def now():
        return current

    monkeypatch.setattr("otel_api_scraper.fingerprints.utc_now", now)
    db_path = tmp_path / "fp.db"
    store = SqliteFingerprintStore(str(db_path), max_entries=2)

    assert not await store.contains("h1", "svc", ttl_seconds=5)
    await store.touch("h1", "svc", ttl_seconds=5)
    assert await store.contains("h1", "svc", ttl_seconds=5)

    current = current + timedelta(seconds=10)
    assert not await store.contains("h1", "svc", ttl_seconds=5)

    current = current + timedelta(seconds=1)
    await store.touch("h1", "svc", ttl_seconds=5)
    current = current + timedelta(seconds=1)
    await store.touch("h2", "svc", ttl_seconds=5)
    current = current + timedelta(seconds=1)
    await store.touch("h3", "svc", ttl_seconds=5)

    db = await store._ensure()
    async with db.execute(
        "SELECT hash FROM fingerprints WHERE source=?", ("svc",)
    ) as cursor:
        rows = await cursor.fetchall()
        hashes = {r[0] for r in rows}
        assert len(hashes) == 2
        assert "h1" not in hashes

    await store.cleanup()
    await store.close()


@pytest.mark.asyncio
async def test_sqlite_cleanup_orphans(tmp_path, monkeypatch):
    current = datetime(2025, 1, 1)

    def now():
        return current

    monkeypatch.setattr("otel_api_scraper.fingerprints.utc_now", now)
    db_path = tmp_path / "fp_orphans.db"
    store = SqliteFingerprintStore(str(db_path), max_entries=5)

    await store.touch("a", "keep", ttl_seconds=10)
    await store.touch("b", "drop", ttl_seconds=10)

    await store.cleanup_orphans({"keep"})

    db = await store._ensure()
    async with db.execute("SELECT DISTINCT source FROM fingerprints") as cursor:
        sources = {row[0] for row in await cursor.fetchall()}
        assert sources == {"keep"}

    await store.close()


class DummyStore(FingerprintStore):
    async def contains(
        self, fp_hash: str, source: str, ttl_seconds: int
    ) -> bool:  # pragma: no cover - trivial
        return False

    async def touch(
        self, fp_hash: str, source: str, ttl_seconds: int
    ) -> None:  # pragma: no cover - trivial
        return None

    async def cleanup(self) -> None:  # pragma: no cover - trivial
        return None


@pytest.mark.asyncio
async def test_base_store_default_methods():
    store = DummyStore()
    assert await store.cleanup_orphans(set()) is None
    assert await store.close() is None


class FakeValkey:
    def __init__(self, *_, **__):
        self.data = {}
        self.zsets = {}

    async def exists(self, key):
        return int(key in self.data)

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def zadd(self, key, mapping):
        zset = self.zsets.setdefault(key, {})
        zset.update(mapping)

    async def zcard(self, key):
        return len(self.zsets.get(key, {}))

    async def zrange(self, key, start, stop):
        zset = self.zsets.get(key, {})
        items = sorted(zset.items(), key=lambda kv: kv[1])
        # emulate slice semantics inclusive of stop index
        return [m for m, _ in items[start : stop + 1 if stop != -1 else None]]

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
            self.zsets.pop(key, None)

    async def zrem(self, key, *members):
        zset = self.zsets.get(key, {})
        for member in members:
            zset.pop(member, None)

    async def mget(self, *keys):
        return [self.data.get(k) for k in keys]

    async def scan(self, cursor="0", match=None, count=None):
        keys = [
            k
            for k in self.zsets.keys()
            if not match or k.startswith(match.replace("*", ""))
        ]
        return "0", keys

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_valkey_store_touch_trim_cleanup_and_orphans(monkeypatch):
    import importlib

    fake_module = types.SimpleNamespace(Valkey=FakeValkey, Redis=None)
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)

    cfg_obj = cfg.FingerprintStoreValkey()
    store = ValkeyFingerprintStore(cfg_obj, max_entries=2)

    assert not await store.contains("a", "svc", ttl_seconds=5)
    await store.touch("a", "svc", ttl_seconds=5)
    await store.touch("b", "svc", ttl_seconds=5)
    await store.touch("c", "svc", ttl_seconds=5)

    index_key = store._index_key("svc")
    assert len(store.client.zsets[index_key]) == 2
    assert await store.contains("b", "svc", ttl_seconds=5)

    # Remove one value to trigger cleanup of missing entries from index.
    missing_key = store._key("svc", "c")
    store.client.data.pop(missing_key, None)
    await store.cleanup()
    assert "c" not in store.client.zsets[index_key]

    # Add another source and ensure cleanup_orphans removes it.
    await store.touch("x", "other", ttl_seconds=5)
    await store.cleanup_orphans({"svc"})
    assert store._index_key("other") not in store.client.zsets
    await store.close()


@pytest.mark.asyncio
async def test_valkey_cleanup_handles_errors(monkeypatch):
    import importlib

    fake_module = types.SimpleNamespace(Valkey=FakeValkey, Redis=None)
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)

    store = ValkeyFingerprintStore(cfg.FingerprintStoreValkey(), max_entries=2)
    store.sources = {"svc"}

    async def zrange_raises(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(store.client, "zrange", zrange_raises)
    await store.cleanup()  # covers exception path

    async def zrange_empty(*args, **kwargs):
        return []

    monkeypatch.setattr(store.client, "zrange", zrange_empty)
    await store.cleanup()  # covers empty members path

    async def zrange_ok(*args, **kwargs):
        return ["a"]

    async def mget_raises(*args, **kwargs):
        raise RuntimeError("mget fail")

    monkeypatch.setattr(store.client, "zrange", zrange_ok)
    monkeypatch.setattr(store.client, "mget", mget_raises)
    await store.cleanup()  # covers mget exception path

    async def scan_raises(*args, **kwargs):
        raise RuntimeError("scan fail")

    monkeypatch.setattr(store.client, "scan", scan_raises)
    await store.cleanup_orphans({"svc"})  # covers scan exception path

    async def scan_ok(cursor="0", match=None, count=None):
        return "0", ["fp_index:bad"]

    async def zrange_orphan_raises(*args, **kwargs):
        raise RuntimeError("zrange fail")

    monkeypatch.setattr(store.client, "scan", scan_ok)
    monkeypatch.setattr(store.client, "zrange", zrange_orphan_raises)
    await store.cleanup_orphans(set())  # covers orphan zrange exception path
    await store.close()


@pytest.mark.asyncio
async def test_build_store_variants(tmp_path, monkeypatch):
    sqlite_cfg = cfg.FingerprintStoreConfig(
        backend="sqlite",
        sqlite=cfg.FingerprintStoreSqlite(path=str(tmp_path / "fp.sqlite")),
        maxEntriesPerSource=1,
    )
    store_sqlite = build_store(sqlite_cfg)
    assert isinstance(store_sqlite, SqliteFingerprintStore)

    monkeypatch.setattr(
        "otel_api_scraper.fingerprints.ValkeyFingerprintStore",
        lambda cfg_obj, max_entries: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    valkey_cfg = cfg.FingerprintStoreConfig(backend="valkey")
    store_valkey = build_store(valkey_cfg)
    assert isinstance(store_valkey, MemoryFingerprintStore)

    await store_sqlite.close()


@pytest.mark.asyncio
async def test_valkey_missing_client_class_raises(monkeypatch):
    import importlib

    fake_module = types.SimpleNamespace()  # no Valkey/Redis
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)

    with pytest.raises(RuntimeError):
        ValkeyFingerprintStore(cfg.FingerprintStoreValkey(), max_entries=1)


@pytest.mark.asyncio
async def test_valkey_password_env(monkeypatch):
    import importlib
    import os

    fake_module = types.SimpleNamespace(Valkey=FakeValkey, Redis=None)
    real_import = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "valkey.asyncio":
            return fake_module
        return real_import(name, package=package)

    monkeypatch.setattr("importlib.import_module", fake_import_module)
    import otel_api_scraper.fingerprints as fp

    setattr(fp, "os", os)
    monkeypatch.setenv("VALKEY_PASS", "secret")

    cfg_obj = cfg.FingerprintStoreValkey(password="VALKEY_PASS")
    store = ValkeyFingerprintStore(cfg_obj, max_entries=1)
    await store.close()


def test_build_store_memory_fallback_without_cfg_class():
    dummy_cfg = types.SimpleNamespace(backend="memory", maxEntriesPerSource=2)
    store = build_store(dummy_cfg)  # type: ignore[arg-type]
    assert isinstance(store, MemoryFingerprintStore)


@pytest.mark.asyncio
async def test_sqlite_fingerprint_retry_on_lock(monkeypatch):
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
    store = SqliteFingerprintStore(
        "ignored.db", max_entries=1, lock_retries=3, lock_backoff=0
    )

    async def fake_ensure(self):
        return fake_db

    monkeypatch.setattr(
        store, "_ensure", fake_ensure.__get__(store, SqliteFingerprintStore)
    )

    await store._execute_with_retry(fake_db, "SELECT 1", tuple(), commit=True)

    assert fake_db.calls == 2
    assert fake_db.committed is True


@pytest.mark.asyncio
async def test_sqlite_fingerprint_raises_on_non_lock(monkeypatch):
    import aiosqlite

    class FakeDB:
        async def execute(self, *_args, **_kwargs):
            raise aiosqlite.OperationalError("other failure")

        async def commit(self):
            raise AssertionError("should not commit on failure")

    store = SqliteFingerprintStore("ignored.db", max_entries=1, lock_retries=1)
    fake_db = FakeDB()

    with pytest.raises(aiosqlite.OperationalError):
        await store._execute_with_retry(fake_db, "SQL", tuple(), commit=True)
