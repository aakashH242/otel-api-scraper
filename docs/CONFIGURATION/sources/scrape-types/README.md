# Scrape Type Examples

This directory contains comprehensive examples for the two scrape types supported by the OTEL API Scraper.

## Available Examples

### 1. [Range-Type Scrape](range-type.yaml)
**Use Case:** Time-series data, historical metrics, event logs

**Scrapes data over a time window** (e.g., "get all integration runs from 1 hour ago to now")

**Key Features:**
- ✅ Time range parameters (start/end timestamps)
- ✅ Historical backfill support with `firstScrapeStart`
- ✅ Parallel window processing for performance
- ✅ Delta detection to avoid duplicates
- ✅ Advanced filtering (drop/keep rules)
- ✅ **Labels come from attributes** (no separate labels in metrics)

**Example API:** Integration Performance Monitoring

**When to Use:**
- APIs that return historical data
- Time-series metrics and events
- Audit logs and transaction histories
- APIs with pagination by time
- Batch processing scenarios

**Common Time Parameters:**
```yaml
rangeKeys:
  startKey: "from_time"      # or: start, since, created[gte]
  endKey: "to_time"          # or: end, until, created[lte]
  firstScrapeStart: "2025-01-01T00:00:00Z"
```

**Parallel Processing:**
```yaml
parallelWindow:
  unit: hours
  value: 2  # Split 24-hour scrape into 12 parallel 2-hour chunks
```

---

### 2. [Instant-Type Scrape](instant-type.yaml)
**Use Case:** Current state, health checks, real-time monitoring

**Scrapes current snapshot without time parameters** (e.g., "get current service health status")

**Key Features:**
- ✅ No time range parameters (instant snapshot)
- ✅ High-frequency monitoring (seconds to minutes)
- ✅ Delta detection for state changes
- ✅ Fixed-value metrics for availability tracking
- ✅ Attribute-to-metric mapping
- ✅ **Labels come from attributes** (no separate labels in metrics)

**Example APIs:** 
- Service Health Status
- Active User Sessions

**When to Use:**
- Health checks and status endpoints
- Current active items (sessions, connections)
- Real-time dashboards
- Inventory snapshots
- Current configuration state

**No Time Parameters Needed:**
```yaml
scrape:
  type: instant
  # No rangeKeys section!
```

---

## Key Difference: Range vs Instant

| Aspect | Range | Instant |
|--------|-------|---------|
| **Time Window** | Yes (start → end) | No (current state) |
| **rangeKeys** | Required | Omitted |
| **Typical Frequency** | 5min - 1h | 10s - 5min |
| **Data Growth** | Historical accumulation | Current snapshot |
| **Use Case** | Events, logs, metrics | Status, health, inventory |
| **Example Query** | "Events from last hour" | "What's happening now?" |

---

## Important: How Labels Work

### ⚠️ Counters and Histograms DO NOT have a `labels` field!

All metric labels come from the `attributes` section. This is a key design principle.

### ❌ INCORRECT (Old Pattern - Don't Use):
```yaml
counterReadings:
  - name: "requests_total"
    labels:  # ❌ This field doesn't exist!
      - name: "status"
        dataKey: "status"
```

### ✅ CORRECT (Current Pattern):
```yaml
# Define attributes once
attributes:
  - name: "status"
    dataKey: "status"
  - name: "region"
    dataKey: "region"

# Metrics automatically use attributes as labels
counterReadings:
  - name: "requests_total"
    unit: "1"
    # No labels field - uses status and region from attributes!

histogramReadings:
  - name: "response_time"
    dataKey: "duration_ms"
    unit: "milliseconds"
    buckets: [10, 50, 100, 500, 1000]
    # No labels field - uses status and region from attributes!
```

### How It Works:

1. **You define attributes** that extract fields from API records
2. **The scraper automatically applies all attributes as labels** to counters and histograms
3. **You get consistent labels** across all metric types

### Example:

```yaml
attributes:
  - name: "service_name"
    dataKey: "name"
  - name: "status"
    dataKey: "status"
  - name: "region"
    dataKey: "region"

counterReadings:
  - name: "api_requests_total"
    valueKey: "request_count"
```

**Resulting Prometheus metric:**
```
api_requests_total{service_name="payment-api", status="healthy", region="us-east-1"} = 1234
api_requests_total{service_name="user-api", status="degraded", region="eu-west-1"} = 567
```

---

## Choosing Between Range and Instant

### Use **Range** when:
- ✅ API supports time-based filtering
- ✅ You need historical data
- ✅ Data is append-only (events, logs)
- ✅ You want to backfill historical metrics
- ✅ API returns different results based on time window

**Examples:**
- Payment transactions: `GET /transactions?from=2025-11-28T10:00:00Z&to=2025-11-28T11:00:00Z`
- Integration runs: `GET /integrations/runs?start=...&end=...`
- Audit logs: `GET /logs?since=...&until=...`

### Use **Instant** when:
- ✅ API returns current state only
- ✅ No time parameters supported
- ✅ High-frequency monitoring needed
- ✅ Data represents "right now"
- ✅ Results don't change based on time parameters

**Examples:**
- Service health: `GET /health/status`
- Active sessions: `GET /sessions/active`
- Current inventory: `GET /inventory/current`
- System metrics: `GET /metrics/current`

---

## Common Patterns

### Pattern 1: Range with Initial Backfill
```yaml
runFirstScrape: true
scrape:
  type: range
  frequency: "1h"
  rangeKeys:
    startKey: "start_date"
    endKey: "end_date"
    firstScrapeStart: "2025-01-01T00:00:00Z"  # Backfill from here
  parallelWindow:
    unit: days
    value: 1  # Process 1 day at a time
```

### Pattern 2: Instant with Delta Detection
```yaml
runFirstScrape: true
scrape:
  type: instant
  frequency: "1min"

deltaDetection:
  enabled: true
  fingerprintMode: keys
  fingerprintKeys:
    - id
    - status
  ttlSeconds: 300  # Re-emit after 5 minutes even if unchanged
```

---

## Metrics Configuration Reference

### Gauge Metrics
**What they are:** Point-in-time values that can go up or down

**Common uses:**
- Current queue depth
- Latest response time
- CPU/memory usage
- Temperature, speed, level

**Configuration:**
```yaml
gaugeReadings:
  - name: "queue_depth"
    dataKey: "items_pending"
    unit: "1"
```

### Counter Metrics
**What they are:** Monotonically increasing counts (only go up)

**Common uses:**
- Total requests processed
- Error counts
- Records created
- Bytes transferred

**Configuration:**
```yaml
counterReadings:
  - name: "requests_total"
    valueKey: "request_count"  # Optional: field to add
    unit: "1"
  
  - name: "record_count"
    # No valueKey = adds 1 per record
    unit: "1"
```

### Histogram Metrics
**What they are:** Distribution of values (min, max, avg, percentiles)

**Common uses:**
- Request/response durations
- Payload sizes
- Processing times
- Latency distributions

**Configuration:**
```yaml
histogramReadings:
  - name: "request_duration"
    dataKey: "duration_ms"
    unit: "milliseconds"
    buckets: [10, 50, 100, 500, 1000, 5000]
```

---

## Testing Your Configuration

### 1. Start with Dry Run
```yaml
scraper:
  dryRun: true
```
Logs what would be emitted without sending to OTEL collector.

### 2. Use runFirstScrape
```yaml
runFirstScrape: true
```
Get immediate feedback when starting the scraper.

### 3. Short Frequency for Testing
```yaml
frequency: "30s"  # Test with short intervals
```
Speeds up testing iteration.

### 4. Enable Debug Logging
```yaml
scraper:
  logLevel: "debug"
```
See detailed information about what's happening.

---

## Additional Resources

- [Authentication Examples](../auth/README.md) - How to configure auth
- [Source Configuration Reference](../README.md) - Complete field reference
- [Global Configuration Reference](../../global/README.md) - Global settings
- [Main Configuration Docs](../../README.md) - Overview and quick start

---

## Quick Reference

| Setting | Range | Instant |
|---------|-------|---------|
| `scrape.type` | `range` | `instant` |
| `scrape.rangeKeys` | Required | Omitted |
| Typical `frequency` | `5min` - `1h` | `10s` - `5min` |
| `parallelWindow` | Supported | Not applicable |
| Time parameters | Yes | No |
| Historical backfill | Supported | Not applicable |

---

## Examples Summary

Both examples in this directory demonstrate:
- ✅ Complete, working configurations
- ✅ Realistic API response formats
- ✅ All three metric types (gauge, counter, histogram)
- ✅ Proper attribute usage (no separate labels!)
- ✅ Delta detection patterns
- ✅ Log severity mapping
- ✅ Comments showing resulting metrics

Copy and adapt these examples to your specific API needs!
