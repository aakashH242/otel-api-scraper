# Metric Measurement Types Examples

This directory contains comprehensive examples for all three metric types supported by the OTEL API Scraper, showing the different ways to configure their values.

## Available Examples

### 1. [Counters](counters.yaml)
**What they are:** Monotonically increasing values (only go up, never down)

**Value Configuration Options:**

- ✅ **Default increment** (adds 1 per record) - no `dataKey` or `fixedValue`
- ✅ **Fixed value** (adds same amount per record) - use `fixedValue`
- ✅ **From field** (adds field value per record) - use `dataKey`

**Common uses:** Event counts, error totals, bytes processed, request totals

**Example scenarios:**

- Count API requests: `events_total` (default increment)
- Sum data volumes: `bytes_processed_total` (from field)
- Weight scoring: `processing_units_total` (fixed value)

---

### 2. [Histograms](histograms.yaml)
**What they are:** Distribution of values showing percentiles and buckets

**Value Configuration Options:**

- ✅ **From field** (most common) - use `dataKey` 
- ✅ **Fixed value** (less common) - use `fixedValue`
- ✅ **Bucket boundaries** - define distribution ranges with `buckets`

**Common uses:** Response times, payload sizes, durations, resource utilization

**Example scenarios:**

- Response time distribution: `request_response_time` (from field)
- CPU usage patterns: `cpu_utilization` (from field)
- Request weighting: `request_weight_distribution` (fixed value)

---

### 3. [Gauges](gauges.yaml)
**What they are:** Point-in-time values that can go up or down

**Value Configuration Options:**

- ✅ **From field** (most common) - use `dataKey`
- ✅ **Fixed value** (for constants) - use `fixedValue`

**Common uses:** Current resource levels, queue depths, active connections, temperatures

**Example scenarios:**

- Current active connections: `service_active_connections` (from field)
- SLA targets: `service_availability_target` (fixed value)
- Resource utilization: `service_cpu_utilization` (from field)

---

## Key Concepts

### Labels Come from Attributes
**⚠️ CRITICAL:** All three metric types get their labels from the `attributes` section.

```yaml
attributes:
  - name: "status"
    dataKey: "status"
  - name: "region"
    dataKey: "region"

counterReadings:
  - name: "requests_total"
    unit: "1"
    # Automatically gets status and region as labels!
```

### Value Priority Rules

**Counters:**

1. `fixedValue` (if set, ignores `dataKey`)
2. `dataKey` (if set, uses field value)
3. Default increment of 1 (if neither set)

**Histograms & Gauges:**

1. `fixedValue` (if set, ignores `dataKey`)
2. `dataKey` (if set, uses field value)

### Error Handling

| Scenario | Counter | Histogram | Gauge |
|----------|---------|-----------|-------|
| Field missing/null | Adds 0 (skips) | Skips record | No update |
| Field non-numeric | Adds 1 (fallback) | Skips record | No update |
| fixedValue used | Always uses value | Always uses value | Always uses value |

---

## Value Configuration Patterns

### Pattern 1: Simple Counting (Counters)
```yaml
counterReadings:
  - name: "events_total"
    unit: "1"
    # No dataKey/fixedValue = counts records (adds 1 each)

  - name: "processing_points_total" 
    fixedValue: 5
    unit: "1"
    # Each record adds 5 points

  - name: "bytes_transferred_total"
    dataKey: "payload_size_bytes"
    unit: "bytes"
    # Sums the payload_size_bytes field
```

### Pattern 2: Distribution Analysis (Histograms)
```yaml
histogramReadings:
  - name: "response_time_distribution"
    dataKey: "duration_ms"
    unit: "milliseconds"
    buckets: [10, 50, 100, 500, 1000, 5000]
    # Shows percentiles and distribution patterns

  - name: "request_weight_distribution"
    fixedValue: 1
    unit: "1"
    buckets: [0.5, 1, 2, 5]
    # All records contribute weight "1"
```

### Pattern 3: Current State (Gauges)
```yaml
gaugeReadings:
  - name: "active_connections"
    dataKey: "current_connections"
    unit: "1"
    # Shows current connection count

  - name: "sla_target"
    fixedValue: 99.9
    unit: "percent"
    # Static SLA target for comparison
```

---

## Choosing the Right Metric Type

### Use **Counters** when:
- ✅ Values only increase (never decrease)
- ✅ You want totals/sums over time
- ✅ Counting events, errors, requests
- ✅ Tracking cumulative bytes/duration

**Questions to ask:**

- "How many X have happened?"
- "What's the total amount of Y?"
- "How much has increased since yesterday?"

### Use **Histograms** when:
- ✅ You need percentiles (P50, P95, P99)
- ✅ You want distribution patterns
- ✅ Values vary significantly across records
- ✅ You need to understand spread/outliers

**Questions to ask:**

- "What's the 95th percentile response time?"
- "How are request sizes distributed?"
- "What percentage of requests are fast vs slow?"

### Use **Gauges** when:
- ✅ Values can go up and down
- ✅ You want current/latest state
- ✅ Monitoring resource levels
- ✅ Tracking active/current items

**Questions to ask:**

- "What's the current value right now?"
- "How many are active at this moment?"
- "What's the latest reading?"

---

## Bucket Design for Histograms

### Response Times (milliseconds)
```yaml
buckets: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000]
# Covers: 1ms to 30 seconds
```

### Payload Sizes (bytes)
```yaml
buckets: [1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216]
# Covers: 1KB to 16MB
```

### Percentages (0-100)
```yaml
buckets: [0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
# Good for CPU, memory, error rates
```

### Queue Depths/Counts
```yaml
buckets: [0, 1, 5, 10, 20, 50, 100, 200, 500, 1000]
# Good for queue sizes, active items
```

---

## Units Reference

### Time Units
- `"seconds"` - Duration in seconds
- `"milliseconds"` - Duration in milliseconds
- `"microseconds"` - Duration in microseconds

### Size Units
- `"bytes"` - Data size in bytes
- `"kilobytes"` - Data size in kilobytes
- `"megabytes"` - Data size in megabytes
- `"gigabytes"` - Data size in gigabytes

### Rate Units
- `"{requests}/s"` - Requests per second
- `"{events}/min"` - Events per minute
- `"{packets}/s"` - Packets per second

### Dimensionless
- `"1"` - Pure counts, ratios, percentages
- `"percent"` - Percentage values (0-100)

---

## Example API Response And Config

With the given JSON response below:

```json
{
  "events": [
    {
      "event_id": "evt-123",
      "event_type": "user_login", 
      "status": "success",
      "processing_time_ms": 150,
      "bytes_processed": 2048,
      "retry_count": 0,
      "region": "us-east-1"
    }
  ]
}
```

And configuration as
```yaml
scraper:
  ...

sources:
  - name: ...
    dataKey: events
    counterReadings:
      - name: events
        unit: "1"
        fixedValue: 1
      - name: bytes_processed
        unit: "1"
        dataKey: bytes_processed
    histogramReadings:
      - name: processing_time
        unit: "milliseconds"
        dataKey: processing_time_ms
```

This creates metrics like:

- `events_total{event_type="user_login", status="success", region="us-east-1"} = 1`
- `bytes_processed_total{event_type="user_login", region="us-east-1"} = 2048`
- `processing_time_distribution{event_type="user_login"} (histogram with buckets)`

---

## Testing Your Configuration

### 1. Use Dry Run Mode
```yaml
scraper:
  dryRun: true
```
See what metrics would be emitted without sending them.

### 2. Check Units and Names
- Verify units make sense for your data
- Use consistent naming conventions
- Follow Prometheus naming guidelines

### 3. Monitor Cardinality
- Watch for high-cardinality labels (unique IDs)
- Each unique label combination creates a new time series
- Balance detail vs performance

### 4. Validate Buckets (Histograms)
- Ensure bucket ranges cover your data spread
- Include buckets for both normal and outlier values
- Test with actual data to verify distribution

---

## Advanced Patterns

### Conditional Metrics with Attributes
```yaml
attributes:
  - name: "status"
    dataKey: "status"
    asMetric:
      metricName: "status_code"
      valueMapping:
        "success": 1
        "error": 0
      unit: "1"
```

### Multi-Purpose Counters
```yaml
counterReadings:
  # Count all events
  - name: "events_total"
    unit: "1"
  
  # Sum processing time
  - name: "processing_time_total"
    dataKey: "processing_time_ms"
    unit: "milliseconds"
  
  # Weight by business value
  - name: "business_value_total"
    dataKey: "transaction_value_cents"
    unit: "cents"
```

### Resource Monitoring Suite
```yaml
gaugeReadings:
  - name: "cpu_usage"
    dataKey: "cpu_percent" 
    unit: "percent"
  
  - name: "memory_usage"
    dataKey: "memory_mb"
    unit: "megabytes"
    
  - name: "active_connections"
    dataKey: "connections"
    unit: "1"

histogramReadings:
  - name: "cpu_usage_distribution"
    dataKey: "cpu_percent"
    unit: "percent"
    buckets: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
```

---

## Extra Reading

| File | Covers | Key Concepts |
|------|--------|--------------|
| [counters.yaml](counters.yaml) | 3 value types | Default increment, fixed value, from field |
| [histograms.yaml](histograms.yaml) | 2 value types + buckets | Distribution analysis, percentiles |
| [gauges.yaml](gauges.yaml) | 2 value types | Current state, point-in-time values |

---

## Additional Resources

- [Authentication Examples](../auth/README.md) - How to configure auth
- [Scrape Types Examples](../scrape-types/README.md) - Range vs Instant scraping
- [Source Configuration Reference](../README.md) - Complete field reference
- [Global Configuration Reference](../../global/README.md) - Global settings
- [Main Configuration Docs](../../README.md) - Overview and quick start

---


Copy and adapt these patterns to your specific APIs and use cases!
