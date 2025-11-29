"""Record filtering and delta detection pipeline."""

from __future__ import annotations

import logging
from typing import Any, List

from . import config as cfg
from .fingerprints import FingerprintStore
from .utils import compute_hash, fingerprint_payload, lookup_path, matches

logger = logging.getLogger(__name__)


class RecordPipeline:
    """Pipeline applying filters, limits, and delta detection to records."""

    def __init__(
        self,
        fingerprint_store: FingerprintStore,
        global_cfg: cfg.FingerprintStoreConfig,
    ):
        """Create a record pipeline.

        Args:
            fingerprint_store: Store used for deduplication.
            global_cfg: Global fingerprint configuration.
        """
        self.store = fingerprint_store
        self.global_cfg = global_cfg
        self.last_stats: dict[str, int] = {"hits": 0, "misses": 0, "total": 0}

    async def run(
        self, records: List[dict[str, Any]], source: cfg.SourceConfig
    ) -> List[dict[str, Any]]:
        """Run the pipeline for a source.

        Args:
            records: Raw records extracted from the API.
            source: Source configuration.

        Returns:
            list[dict[str, Any]]: Records that pass filters and delta detection.
        """
        self.last_stats = {"hits": 0, "misses": 0, "total": len(records)}
        logger.debug(
            "Pipeline start for source %s with %s records", source.name, len(records)
        )
        filtered = self._apply_filters(records, source.filters)
        logger.debug("After filters for %s: %s records", source.name, len(filtered))
        limited = self._apply_limits(filtered, source.filters)
        logger.debug("After limits for %s: %s records", source.name, len(limited))
        deduped = await self._apply_delta_detection(limited, source)
        logger.debug(
            "After delta detection for %s: %s records", source.name, len(deduped)
        )
        if not deduped:
            logger.debug(
                "No records remain after pipeline for source %s; skipping telemetry.",
                source.name,
            )
        return deduped

    def _apply_filters(
        self, records: List[dict[str, Any]], filters: cfg.FiltersConfig
    ) -> List[dict[str, Any]]:
        """Apply drop/keep filters."""
        if not filters.drop and not filters.keep:
            return records
        remaining = []
        for record in records:
            if self._matches_drop(record, filters):
                continue
            if filters.keep and not self._matches_keep(record, filters):
                continue
            remaining.append(record)
        return remaining

    def _matches_drop(self, record: dict[str, Any], filters: cfg.FiltersConfig) -> bool:
        """Return True if record matches any drop rule."""
        for rule in filters.drop:
            for predicate in rule.any:
                value = lookup_path(record, predicate.field)
                if matches(predicate.matchType, value, predicate.value):
                    return True
        return False

    def _matches_keep(self, record: dict[str, Any], filters: cfg.FiltersConfig) -> bool:
        """Return True if record satisfies at least one keep rule."""
        for rule in filters.keep:
            all_match = True
            for predicate in rule.all:
                value = lookup_path(record, predicate.field)
                if not matches(predicate.matchType, value, predicate.value):
                    all_match = False
                    break
            if all_match:
                return True
        return False

    def _apply_limits(
        self, records: List[dict[str, Any]], filters: cfg.FiltersConfig
    ) -> List[dict[str, Any]]:
        """Apply per-scrape record cap."""
        limit = filters.limits.maxRecordsPerScrape
        if limit is None or limit <= 0:
            return records
        return records[:limit]

    async def _apply_delta_detection(
        self, records: List[dict[str, Any]], source: cfg.SourceConfig
    ) -> List[dict[str, Any]]:
        """Deduplicate records using configured fingerprint store."""
        dd = source.deltaDetection
        if not dd.enabled:
            self.last_stats = {"hits": 0, "misses": len(records), "total": len(records)}
            return records
        ttl = dd.ttlSeconds or self.global_cfg.defaultTtlSeconds
        kept: List[dict[str, Any]] = []
        keys = dd.fingerprintKeys if dd.fingerprintMode == "keys" else None
        hits = 0
        misses = 0
        for record in records:
            payload = fingerprint_payload(record, keys, source.name)
            fp_hash = compute_hash(payload)
            if await self.store.contains(fp_hash, source.name, ttl):
                hits += 1
                continue
            await self.store.touch(fp_hash, source.name, ttl)
            misses += 1
            kept.append(record)
        self.last_stats = {"hits": hits, "misses": misses, "total": len(records)}
        return kept
