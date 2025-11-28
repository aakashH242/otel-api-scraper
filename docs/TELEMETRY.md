# SELF TELEMETRY

When enabled, the scraper emits the following metrics about its own operations:

## Scrape Execution Metrics

| Metric Name | Type | Unit | Description | Attributes |
|-------------|------|------|-------------|------------|
| `scraper_scrape_duration_seconds` | Histogram | `s` | Distribution of scrape execution times | `source`, `status`, `api_type` |
| `scraper_scrape_total` | Counter | `1` | Total number of scrapes executed | `source`, `status`, `api_type` |
| `scraper_last_scrape_duration_seconds` | Gauge | `s` | Duration of the most recent scrape | `source`, `status`, `api_type` |
| `scraper_last_records_emitted` | Gauge | `1` | Number of records emitted in the most recent scrape | `source`, `status`, `api_type` |

**Attributes:**
- `source`: Name of the source being scraped
- `status`: `success` or `error`
- `api_type`: `instant` or `range` (derived from `source.scrape.type`)

**Example:**
```promql
# Average scrape duration by source
rate(scraper_scrape_duration_seconds_sum[5m]) / rate(scraper_scrape_duration_seconds_count[5m])

# Scrape success rate
rate(scraper_scrape_total{status="success"}[5m]) / rate(scraper_scrape_total[5m])

# Records emitted per scrape
scraper_last_records_emitted
```

## Deduplication Metrics

| Metric Name | Type | Unit | Description | Attributes |
|-------------|------|------|-------------|------------|
| `scraper_dedupe_hits_total` | Counter | `1` | Total fingerprints skipped (already seen) | `source`, `api_type` |
| `scraper_dedupe_misses_total` | Counter | `1` | Total fingerprints processed (new records) | `source`, `api_type` |
| `scraper_dedupe_total` | Counter | `1` | Total records processed through dedupe | `source`, `api_type` |
| `scraper_dedupe_hit_rate` | Gauge | `1` | Ratio of hits to total (0.0 to 1.0) | `source`, `api_type` |

**Attributes:**
- `source`: Name of the source
- `api_type`: `instant` or `range`

**Example:**
```promql
# Deduplication hit rate (percentage of duplicates)
scraper_dedupe_hit_rate * 100

# New records per minute
rate(scraper_dedupe_misses_total[1m])

# Duplicate detection rate
rate(scraper_dedupe_hits_total[5m]) / rate(scraper_dedupe_total[5m])
```

## Cleanup Job Metrics

| Metric Name | Type | Unit | Description | Attributes |
|-------------|------|------|-------------|------------|
| `scraper_cleanup_duration_seconds` | Histogram | `s` | Distribution of cleanup job execution times | `job`, `backend` |
| `scraper_cleanup_last_duration_seconds` | Gauge | `s` | Duration of the most recent cleanup | `job`, `backend` |
| `scraper_cleanup_items_total` | Counter | `1` | Total items cleaned across all jobs | `job`, `backend` |
| `scraper_cleanup_last_items` | Gauge | `1` | Number of items cleaned in most recent run | `job`, `backend` |

**Attributes:**
- `job`: Type of cleanup job (`fingerprint_cleanup` or `orphan_cleanup`)
- `backend`: Storage backend (`sqlite` or `valkey`)

**Example:**
```promql
# Cleanup duration by job type
scraper_cleanup_last_duration_seconds

# Items cleaned per cleanup cycle
rate(scraper_cleanup_items_total[10m])

# Cleanup frequency
rate(scraper_cleanup_duration_seconds_count[1h])
```

## Self-Telemetry Logs

In addition to metrics, the scraper emits structured logs for each scrape execution when self-telemetry is enabled:

**Log Attributes:**
- `component`: `scraper`
- `source`: Source name
- `status`: `success` or `error`
- `duration_seconds`: Scrape duration
- `record_count`: Number of records processed

**Severity Levels:**
- `INFO`: Successful scrapes
- `ERROR`: Failed scrapes

**Example Log Query (Loki):**
```logql
{component="scraper"} | json | status="error"
```

## Monitoring Dashboard Examples

### Key Performance Indicators

```promql
# Scraper health: Success rate
sum(rate(scraper_scrape_total{status="success"}[5m])) by (source)
/ sum(rate(scraper_scrape_total[5m])) by (source)

# Scraper throughput: Records per second
sum(rate(scraper_last_records_emitted[1m])) by (source)

# Scraper efficiency: Dedupe hit rate
avg(scraper_dedupe_hit_rate) by (source)

# Scraper performance: P95 scrape duration
histogram_quantile(0.95, 
  rate(scraper_scrape_duration_seconds_bucket[5m])
)
```

### Alerting Rules

```yaml
# Alert when scrapes are failing
- alert: ScraperHighErrorRate
  expr: |
    rate(scraper_scrape_total{status="error"}[5m])
    / rate(scraper_scrape_total[5m]) > 0.1
  for: 5m
  annotations:
    summary: "Scraper {{ $labels.source }} has high error rate"

# Alert when scrapes are slow
- alert: ScraperSlowScrapes
  expr: |
    histogram_quantile(0.95,
      rate(scraper_scrape_duration_seconds_bucket[5m])
    ) > 60
  for: 10m
  annotations:
    summary: "Scraper {{ $labels.source }} taking too long (>60s)"

# Alert when no new records detected
- alert: ScraperNoNewRecords
  expr: |
    rate(scraper_dedupe_misses_total[15m]) == 0
  for: 30m
  annotations:
    summary: "Scraper {{ $labels.source }} not detecting new records"
```

## Best Practices

1. **Enable self-telemetry in production**: Monitor the scraper's own health and performance
2. **Set up alerts**: Track error rates, slow scrapes, and stalled deduplication
3. **Monitor dedupe hit rate**: High hit rates may indicate:
   - Effective fingerprinting (good)
   - APIs not returning new data (investigate)
   - TTL too long for your use case
4. **Track cleanup metrics**: Ensure fingerprint/orphan cleanup is running and completing successfully
5. **Use `api_type` attribute**: Distinguish instant vs range scrape performance patterns
6. **Correlate with API metrics**: Compare self-telemetry with the actual metrics being extracted

## Performance Impact

Self-telemetry has minimal overhead:
- **CPU**: ~1-2% additional CPU for metric recording
- **Memory**: Negligible (metrics buffered and batched)
- **Network**: Small increase (~100-500 bytes per scrape)
- **Latency**: No impact on scrape timing (metrics recorded asynchronously)
