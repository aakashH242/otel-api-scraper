"""State storage for tracking last successful scrapes."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, Optional

import aiosqlite

from . import config as cfg
from .utils import ensure_aware

logger = logging.getLogger(__name__)


class StateStore:
    """Abstract state store for last-success timestamps."""

    async def get_last_success(self, source: str) -> Optional[datetime]:
        """Fetch the last successful scrape time for a source."""

    async def set_last_success(self, source: str, when: datetime) -> None:
        """Persist the last successful scrape time for a source."""

    async def close(self) -> None:
        """Close underlying resources."""


class MemoryStateStore(StateStore):
    """In-memory state store for ephemeral runs."""

    def __init__(self):
        """Initialize in-memory store."""
        self._state: Dict[str, datetime] = {}

    async def get_last_success(self, source: str) -> Optional[datetime]:
        """Return last success timestamp for a source."""
        return self._state.get(source)

    async def set_last_success(self, source: str, when: datetime) -> None:
        """Record last success timestamp for a source."""
        self._state[source] = ensure_aware(when)

    async def close(self) -> None:
        return None


class SqliteStateStore(StateStore):
    """SQLite-backed store for last-success timestamps."""

    def __init__(self, path: str):
        """Create sqlite state store.

        Args:
            path: Database file path.
        """
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None

    async def _ensure(self) -> aiosqlite.Connection:
        """Ensure database exists with expected schema."""
        if self._db is None:
            self._db = await aiosqlite.connect(self.path)
            await self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS last_success (
                    source TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL
                );
                """
            )
            await self._db.commit()
        return self._db

    async def get_last_success(self, source: str) -> Optional[datetime]:
        """Fetch last success timestamp for a source."""
        db = await self._ensure()
        async with db.execute(
            "SELECT timestamp FROM last_success WHERE source=?", (source,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return datetime.fromisoformat(row[0])

    async def set_last_success(self, source: str, when: datetime) -> None:
        """Persist last success timestamp for a source."""
        db = await self._ensure()
        ts = ensure_aware(when).isoformat()
        await db.execute(
            "INSERT INTO last_success(source, timestamp) VALUES (?, ?) ON CONFLICT(source) DO UPDATE SET timestamp=excluded.timestamp",
            (source, ts),
        )
        await db.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None


class ValkeyStateStore(StateStore):
    """Valkey/Redis-backed store for last-success timestamps."""

    def __init__(self, cfg_obj: cfg.FingerprintStoreValkey):
        """Create valkey-backed state store.

        Args:
            cfg_obj: Valkey configuration.
        """
        try:
            import importlib

            valkey_async = importlib.import_module("valkey.asyncio")  # type: ignore
        except Exception as exc:  # pragma: no cover
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

    async def get_last_success(self, source: str) -> Optional[datetime]:
        """Fetch last success timestamp for a source."""
        val = await self.client.get(self._key(source))
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return None

    async def set_last_success(self, source: str, when: datetime) -> None:
        """Persist last success timestamp for a source."""
        await self.client.set(self._key(source), ensure_aware(when).isoformat())

    async def close(self) -> None:
        """Close valkey client."""
        await self.client.close()

    def _key(self, source: str) -> str:
        return f"last_success:{source}"


def build_state_store(store_cfg: cfg.FingerprintStoreConfig) -> StateStore:
    """Create state store using same backend as fingerprints."""
    backend = store_cfg.backend
    if backend == "sqlite":
        return SqliteStateStore(store_cfg.sqlite.path)
    if backend in {"valkey", "redis"}:
        try:
            return ValkeyStateStore(store_cfg.valkey)
        except Exception as exc:
            logger.warning("Falling back to in-memory state store: %s", exc)
            return MemoryStateStore()
    return MemoryStateStore()
