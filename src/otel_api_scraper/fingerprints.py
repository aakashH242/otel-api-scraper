"""Fingerprint store implementations for delta detection."""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional

import aiosqlite

from . import config as cfg
from .utils import utc_now

logger = logging.getLogger(__name__)


class FingerprintStore(ABC):
    """Abstract fingerprint store for delta detection."""

    @abstractmethod
    async def contains(self, fp_hash: str, source: str, ttl_seconds: int) -> bool:
        """Return True if the fingerprint exists and is within TTL."""

    @abstractmethod
    async def touch(self, fp_hash: str, source: str, ttl_seconds: int) -> None:
        """Insert or refresh a fingerprint entry."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Remove expired entries."""

    async def cleanup_orphans(self, active_sources: set[str]) -> None:
        """Remove fingerprints for sources not in the active config."""
        return None

    async def close(self) -> None:
        """Close underlying resources."""
        return None


class MemoryFingerprintStore(FingerprintStore):
    """Lightweight fallback store for dev/dry-run."""

    def __init__(self, max_entries: int):
        """Create an in-memory fingerprint store.

        Args:
            max_entries: Maximum entries to retain per source.
        """
        self.max_entries = max_entries
        self.store: Dict[str, Dict[str, datetime]] = {}

    async def contains(self, fp_hash: str, source: str, ttl_seconds: int) -> bool:
        """Check memory store for a fingerprint within TTL."""
        now = utc_now()
        source_store = self.store.get(source, {})
        last_seen = source_store.get(fp_hash)
        if not last_seen:
            logger.debug("FP miss (memory) source=%s hash=%s", source, fp_hash)
            return False
        if (now - last_seen).total_seconds() > ttl_seconds:
            source_store.pop(fp_hash, None)
            logger.debug("FP expired (memory) source=%s hash=%s", source, fp_hash)
            return False
        logger.debug("FP hit (memory) source=%s hash=%s", source, fp_hash)
        return True

    async def touch(self, fp_hash: str, source: str, ttl_seconds: int) -> None:
        """Record or update a fingerprint timestamp."""
        now = utc_now()
        source_store = self.store.setdefault(source, {})
        source_store[fp_hash] = now
        logger.debug("FP touch (memory) source=%s hash=%s", source, fp_hash)
        if len(source_store) > self.max_entries:
            # Evict oldest.
            sorted_items = sorted(source_store.items(), key=lambda kv: kv[1])
            for key, _ in sorted_items[: -self.max_entries]:
                source_store.pop(key, None)

    async def cleanup(self) -> None:
        return None

    async def cleanup_orphans(self, active_sources: set[str]) -> None:
        """Drop fingerprints for sources not present in config."""
        for source in list(self.store.keys()):
            if source not in active_sources:
                self.store.pop(source, None)


class SqliteFingerprintStore(FingerprintStore):
    """SQLite-backed fingerprint store."""

    def __init__(
        self,
        path: str,
        max_entries: int,
        lock_retries: int = 5,
        lock_backoff: float = 0.1,
    ):
        """Create a sqlite-backed fingerprint store.

        Args:
            path: Database file path.
            max_entries: Maximum entries per source.
        """
        self.path = path
        self.max_entries = max_entries
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        self.lock_retries = lock_retries
        self.lock_backoff = lock_backoff

    async def _ensure(self) -> aiosqlite.Connection:
        """Ensure the database is initialized."""
        if self._db is None:
            self._db = await aiosqlite.connect(self.path)
            await self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS fingerprints (
                    hash TEXT NOT NULL,
                    source TEXT NOT NULL,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    ttl INTEGER NOT NULL,
                    PRIMARY KEY (hash, source)
                );
                """
            )
            await self._db.commit()
        return self._db

    async def contains(self, fp_hash: str, source: str, ttl_seconds: int) -> bool:
        """Check sqlite for an existing fingerprint within TTL."""
        db = await self._ensure()
        now = int(utc_now().timestamp())
        async with self._lock:
            async with db.execute(
                "SELECT last_seen, ttl FROM fingerprints WHERE hash=? AND source=?",
                (fp_hash, source),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    logger.debug("FP miss (sqlite) source=%s hash=%s", source, fp_hash)
                    return False
                last_seen, row_ttl = row
                effective_ttl = row_ttl or ttl_seconds
                if now - last_seen > effective_ttl:
                    await self._execute_with_retry(
                        db,
                        "DELETE FROM fingerprints WHERE hash=? AND source=?",
                        (fp_hash, source),
                        commit=True,
                    )
                    logger.debug(
                        "FP expired (sqlite) source=%s hash=%s", source, fp_hash
                    )
                    return False
                logger.debug("FP hit (sqlite) source=%s hash=%s", source, fp_hash)
                return True

    async def touch(self, fp_hash: str, source: str, ttl_seconds: int) -> None:
        """Insert or update a fingerprint timestamp."""
        db = await self._ensure()
        now = int(utc_now().timestamp())
        async with self._lock:
            await self._execute_with_retry(
                db,
                """
                INSERT INTO fingerprints(hash, source, first_seen, last_seen, ttl)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(hash, source) DO UPDATE SET last_seen=excluded.last_seen, ttl=excluded.ttl
                """,
                (fp_hash, source, now, now, ttl_seconds),
                commit=True,
            )
            logger.debug("FP touch (sqlite) source=%s hash=%s", source, fp_hash)
            await self._enforce_capacity(db, source)

    async def _enforce_capacity(self, db: aiosqlite.Connection, source: str) -> None:
        """Trim fingerprints beyond max capacity per source."""
        async with db.execute(
            "SELECT COUNT(*) FROM fingerprints WHERE source=?",
            (source,),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > self.max_entries:
                overflow = row[0] - self.max_entries
                await self._execute_with_retry(
                    db,
                    """
                    DELETE FROM fingerprints
                    WHERE hash IN (
                        SELECT hash FROM fingerprints
                        WHERE source=?
                        ORDER BY last_seen ASC
                        LIMIT ?
                    ) AND source=?
                    """,
                    (source, overflow, source),
                    commit=True,
                )

    async def cleanup(self) -> None:
        db = await self._ensure()
        now = int(utc_now().timestamp())
        async with self._lock:
            await self._execute_with_retry(
                db,
                "DELETE FROM fingerprints WHERE last_seen + ttl < ?",
                (now,),
                commit=True,
            )
            logger.debug(
                "FP cleanup (sqlite) removed expired entries older than %s", now
            )

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def cleanup_orphans(self, active_sources: set[str]) -> None:
        """Delete fingerprints for sources not present in config."""
        db = await self._ensure()
        async with self._lock:
            placeholders = ",".join("?" for _ in active_sources) or "''"
            sql = f"DELETE FROM fingerprints WHERE source NOT IN ({placeholders})"
            await self._execute_with_retry(db, sql, tuple(active_sources), commit=True)

    async def _execute_with_retry(
        self, db: aiosqlite.Connection, sql: str, params: tuple, commit: bool = False
    ) -> None:
        """Execute a statement with simple lock retry."""
        attempts = max(1, self.lock_retries)
        delay = self.lock_backoff
        for attempt in range(1, attempts + 1):
            try:
                await db.execute(sql, params)
                if commit:
                    await db.commit()
                return
            except aiosqlite.OperationalError as exc:
                if "locked" in str(exc).lower() and attempt < attempts:
                    logger.warning(
                        "Sqlite locked during fingerprint op (attempt %s/%s); retrying",
                        attempt,
                        attempts,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 1.0)
                    continue
                raise


class ValkeyFingerprintStore(FingerprintStore):
    """Valkey/Redis-backed fingerprint store."""

    def __init__(self, cfg_obj: cfg.FingerprintStoreValkey, max_entries: int):
        """Create a valkey-backed fingerprint store.

        Args:
            cfg_obj: Valkey configuration.
            max_entries: Maximum entries per source.
        """
        try:
            import importlib

            valkey_async = importlib.import_module("valkey.asyncio")  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(
                "valkey backend requested but valkey.asyncio unavailable"
            ) from exc

        client_cls = getattr(valkey_async, "Valkey", None) or getattr(
            valkey_async, "Redis", None
        )
        if client_cls is None:
            raise RuntimeError("valkey.asyncio does not expose Valkey/Redis client")
        valkey_password = cfg_obj.password
        if valkey_password and valkey_password in os.environ:
            valkey_password = os.environ[valkey_password]
        self.client = client_cls(
            host=cfg_obj.host,
            port=cfg_obj.port,
            db=cfg_obj.db,
            password=valkey_password,
            ssl=cfg_obj.ssl,
            decode_responses=True,
        )
        self.max_entries = max_entries
        self.sources: set[str] = set()

    async def contains(self, fp_hash: str, source: str, ttl_seconds: int) -> bool:
        """Check valkey for existing fingerprint."""
        key = self._key(source, fp_hash)
        exists = bool(await self.client.exists(key))
        logger.debug(
            "FP %s (valkey) source=%s hash=%s",
            "hit" if exists else "miss",
            source,
            fp_hash,
        )
        return exists

    async def touch(self, fp_hash: str, source: str, ttl_seconds: int) -> None:
        """Insert or refresh a fingerprint entry."""
        key = self._key(source, fp_hash)
        now = utc_now().timestamp()
        await self.client.set(key, now, ex=ttl_seconds)
        index_key = self._index_key(source)
        await self.client.zadd(index_key, {fp_hash: now})
        self.sources.add(source)
        await self._trim(index_key, source)
        logger.debug("FP touch (valkey) source=%s hash=%s", source, fp_hash)

    async def _trim(self, index_key: str, source: str) -> None:
        """Enforce capacity by trimming least-recent fingerprints."""
        size = await self.client.zcard(index_key)
        if size and size > self.max_entries:
            overflow = int(size - self.max_entries)
            victims = await self.client.zrange(index_key, 0, overflow - 1)
            if victims:
                await self.client.delete(*[self._key(source, v) for v in victims])
                await self.client.zrem(index_key, *victims)
                logger.debug(
                    "FP trim (valkey) source=%s removed=%s", source, len(victims)
                )

    async def cleanup(self) -> None:
        """Prune sorted-set indexes for expired fingerprints."""
        for source in list(self.sources):
            index_key = self._index_key(source)
            try:
                members = await self.client.zrange(index_key, 0, -1)
            except Exception:
                continue
            if not members:
                continue
            keys = [self._key(source, m) for m in members]
            try:
                values = await self.client.mget(*keys)
            except Exception:
                # Fallback: skip index pruning if mget is unavailable.
                continue
            missing = [
                member for member, value in zip(members, values) if value is None
            ]
            if missing:
                await self.client.zrem(index_key, *missing)
                logger.debug(
                    "FP cleanup (valkey) source=%s removed_missing=%s",
                    source,
                    len(missing),
                )

    async def close(self) -> None:
        """Close valkey client."""
        await self.client.close()

    def _key(self, source: str, fp_hash: str) -> str:
        return f"fp:{source}:{fp_hash}"

    def _index_key(self, source: str) -> str:
        return f"fp_index:{source}"

    async def cleanup_orphans(self, active_sources: set[str]) -> None:
        """Remove valkey fingerprint keys for sources not in config."""
        # Gather index keys
        cursor = "0"
        index_keys: list[str] = []
        try:
            while True:
                cursor, keys = await self.client.scan(
                    cursor=cursor, match="fp_index:*", count=100
                )
                index_keys.extend(keys)
                if cursor == "0":
                    break
        except Exception:
            return
        for index_key in index_keys:
            source = index_key.replace("fp_index:", "", 1)
            if source in active_sources:
                continue
            try:
                members = await self.client.zrange(index_key, 0, -1)
                if members:
                    await self.client.delete(*[self._key(source, m) for m in members])
                await self.client.delete(index_key)
                logger.debug(
                    "FP orphan cleanup (valkey) removed source=%s keys=%s",
                    source,
                    len(members),
                )
            except Exception:
                continue


def build_store(store_cfg: cfg.FingerprintStoreConfig) -> FingerprintStore:
    """Create a fingerprint store for the configured backend."""
    backend = store_cfg.backend
    if backend == "sqlite":
        return SqliteFingerprintStore(
            store_cfg.sqlite.path,
            store_cfg.maxEntriesPerSource,
            lock_retries=store_cfg.lockRetries,
            lock_backoff=store_cfg.lockBackoffSeconds,
        )
    if backend == "valkey" or backend == "redis":
        try:
            return ValkeyFingerprintStore(
                store_cfg.valkey, store_cfg.maxEntriesPerSource
            )
        except Exception as exc:
            logger.warning("Falling back to in-memory fingerprint store: %s", exc)
            return MemoryFingerprintStore(store_cfg.maxEntriesPerSource)
    return MemoryFingerprintStore(store_cfg.maxEntriesPerSource)
