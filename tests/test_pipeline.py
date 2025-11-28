import pytest

from otel_api_scraper import config as cfg
from otel_api_scraper.pipeline import RecordPipeline


class DummyStore:
    def __init__(self, existing=None):
        self.existing = set(existing or [])
        self.touched = []
        self.contains_calls = []
        self.last_ttl = None

    async def contains(self, fp_hash, source, ttl_seconds):
        self.contains_calls.append((fp_hash, source, ttl_seconds))
        self.last_ttl = ttl_seconds
        return fp_hash in self.existing

    async def touch(self, fp_hash, source, ttl_seconds):
        self.touched.append((fp_hash, source, ttl_seconds))
        self.existing.add(fp_hash)

    async def cleanup(self):
        return None

    async def cleanup_orphans(self, active_sources):
        return None

    async def close(self):
        return None


def make_source(filters=None, delta=None):
    return cfg.SourceConfig(
        name="svc",
        frequency="1m",
        baseUrl="https://api.example.com",
        endpoint="/items",
        scrape=cfg.ScrapeConfig(type="instant"),
        filters=filters or cfg.FiltersConfig(),
        deltaDetection=delta or cfg.DeltaDetectionConfig(),
    )


@pytest.mark.asyncio
async def test_pipeline_no_filters_no_delta_detection():
    store = DummyStore()
    pipeline = RecordPipeline(store, cfg.FingerprintStoreConfig())
    records = [{"id": 1}, {"id": 2}]

    result = await pipeline.run(records, make_source())

    assert result == records
    assert store.contains_calls == []
    assert store.touched == []


@pytest.mark.asyncio
async def test_filters_drop_keep_and_limits(monkeypatch):
    drop_rule = cfg.DropRule(
        any=[cfg.MatchPredicate(field="type", matchType="equals", value="ignore")]
    )
    keep_rule = cfg.KeepRule(
        all=[cfg.MatchPredicate(field="status", matchType="equals", value="ok")]
    )
    filters = cfg.FiltersConfig(
        drop=[drop_rule],
        keep=[keep_rule],
        limits=cfg.FilterLimits(maxRecordsPerScrape=1),
    )
    source = make_source(filters=filters)
    store = DummyStore()
    pipeline = RecordPipeline(store, cfg.FingerprintStoreConfig())
    records = [
        {"id": 1, "type": "ignore", "status": "ok"},  # dropped
        {"id": 2, "status": "ok"},  # kept then limited
        {"id": 3, "status": "fail"},  # filtered by keep
    ]

    result = await pipeline.run(records, source)

    assert result == [records[1]]
    assert store.contains_calls == []
    assert store.touched == []


@pytest.mark.asyncio
async def test_delta_detection_full_record_uses_global_ttl(monkeypatch):
    monkeypatch.setattr(
        "otel_api_scraper.pipeline.compute_hash", lambda payload: payload
    )
    global_cfg = cfg.FingerprintStoreConfig(defaultTtlSeconds=10)
    source = make_source(delta=cfg.DeltaDetectionConfig(enabled=True, ttlSeconds=None))
    store = DummyStore()
    pipeline = RecordPipeline(store, global_cfg)
    records = [{"id": 1}, {"id": 2}]

    # Pre-mark first record as seen
    from otel_api_scraper.utils import fingerprint_payload

    seen_payload = fingerprint_payload(records[0], None, source.name)
    store.existing.add(seen_payload)

    result = await pipeline.run(records, source)

    assert result == [records[1]]
    # Second record was touched with defaultTtlSeconds
    assert store.last_ttl == 10
    assert store.touched and store.touched[0][1] == source.name


@pytest.mark.asyncio
async def test_delta_detection_keys_mode_and_custom_ttl(monkeypatch):
    monkeypatch.setattr(
        "otel_api_scraper.pipeline.compute_hash", lambda payload: payload
    )
    source = make_source(
        delta=cfg.DeltaDetectionConfig(
            enabled=True,
            fingerprintMode="keys",
            fingerprintKeys=["id"],
            ttlSeconds=5,
        )
    )
    store = DummyStore()
    pipeline = RecordPipeline(store, cfg.FingerprintStoreConfig())
    records = [{"id": 1, "status": "ok"}, {"id": 1, "status": "changed"}]

    from otel_api_scraper.utils import fingerprint_payload

    first_fp = fingerprint_payload(records[0], ["id"], source.name)

    result = await pipeline.run(records, source)

    # First record touched, second deduped by key
    assert result == [records[0]]
    assert store.contains_calls[0][0] == first_fp
    assert store.touched[0][0] == first_fp
    assert store.last_ttl == 5


@pytest.mark.asyncio
async def test_pipeline_logs_when_no_records_remain(caplog, monkeypatch):
    class AlwaysExistsStore(DummyStore):
        async def contains(self, fp_hash, source, ttl_seconds):
            return True

    caplog.set_level("DEBUG", logger="otel_api_scraper.pipeline")
    source = make_source(delta=cfg.DeltaDetectionConfig(enabled=True))
    pipeline = RecordPipeline(AlwaysExistsStore(), cfg.FingerprintStoreConfig())

    result = await pipeline.run([{"id": 1}], source)

    assert result == []
    assert any("No records remain after pipeline" in msg for msg in caplog.messages)
