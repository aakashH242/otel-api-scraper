
# Source Configuration Reference

This document describes all configuration options for individual API sources under the `sources` section. Each source represents a single API endpoint that the scraper will poll periodically to collect metrics and logs.

---

## Table of Contents
- [Core Source Settings](#core-source-settings)
- [Authentication](#authentication)
- [Scrape Configuration](#scrape-configuration)
- [Data Extraction and Processing](#data-extraction-and-processing)
- [Filters and Limits](#filters-and-limits)
- [Delta Detection (Deduplication)](#delta-detection-deduplication)
- [Metrics Configuration](#metrics-configuration)
- [Attributes and Logs](#attributes-and-logs)
- [Complete Examples](#complete-examples)

---

## Core Source Settings

### `name`
- **Type**: `string`
- **Required**: ✅ Yes
- **Description**: Logical name for this API source. This is used as the `service.name` in OTEL resource attributes, making it easy to distinguish telemetry from different sources in your observability backend.
- **Use Case**: Use descriptive names like `"stripe-payments"`, `"github-webhooks"`, or `"salesforce-leads"`.
- **Example**: 
  ```yaml
  name: "integration-performance"
  ```

### `frequency`
- **Type**: `string`
- **Required**: ✅ Yes
- **Format**: `<number><unit>` where unit is one of:
  - `min` - minutes
  - `h` - hours  
  - `d` - days
  - `w` - weeks
  - `m` - months
- **Description**: How often to scrape this API endpoint. The scraper will schedule scrapes at this interval.
- **Examples**:
  - `"15min"` - Every 15 minutes
  - `"1h"` - Every hour
  - `"1d"` - Once per day
  - `"30min"` - Every 30 minutes
- **Use Case**: Match this to your API's data freshness requirements and rate limits.

### `baseUrl`
- **Type**: `string`
- **Required**: ✅ Yes
- **Description**: The base URL of the API (scheme + host + optional port). This is combined with `endpoint` to form the complete request URL.
- **Examples**:
  - `"https://api.example.com"`
  - `"https://api.example.com:8443"`
  - `"http://internal-service"`
- **Use Case**: Set this to your API's base domain. The endpoint path is appended to this.

### `endpoint`
- **Type**: `string`
- **Required**: ✅ Yes
- **Description**: The API endpoint path (appended to `baseUrl`). Should start with `/`.
- **Examples**:
  - `"/v1/metrics"`
  - `"/api/integrations/performance"`
  - `"/posts"`
- **Complete URL**: `baseUrl` + `endpoint` + query parameters = `https://api.example.com/v1/metrics?start=...`

### `allowOverlapScans`
- **Type**: `boolean`
- **Default**: `false`
- **Global Override**: ✅ Overrides `scraper.allowOverlapScans`
- **Description**: Whether this source allows overlapping scrapes. If `false`, a new scrape will wait for the previous one to complete. If `true`, scrapes can run concurrently.
- **Use Case**: Enable for APIs that can handle concurrent requests and where data freshness is critical. Keep disabled for APIs with strict rate limits or stateful operations.

### `emitLogs`
- **Type**: `boolean`
- **Default**: `true`
- **Description**: Controls whether log records are generated for this source. If `false`, only metrics are emitted (logs are suppressed).
- **Use Case**: Disable if you only care about metrics or if the API returns too much data for logging.

---

## Authentication

Configure how the scraper authenticates with your API. Omit the `auth` section entirely if the API is public.

### Basic Authentication

```yaml
auth:
  type: basic
  username: API_USERNAME_ENV  # Name of environment variable
  password: API_PASSWORD_ENV  # Name of environment variable
```

- **Description**: HTTP Basic Authentication using username and password.
- **Security**: Values are environment variable **names**, not the actual credentials. The scraper reads `os.environ[username]` and `os.environ[password]`.
- **Use Case**: Simple APIs with basic auth.

### API Key Authentication

```yaml
auth:
  type: apikey
  keyName: "X-API-Key"        # Header name
  keyValue: API_KEY_ENV       # Name of environment variable
```

- **Description**: Authentication via a custom header (e.g., `X-API-Key`, `Authorization`).
- **Security**: `keyValue` is the environment variable name containing the actual key.
- **Use Case**: Most modern APIs use this approach.

### OAuth (Static Token)

```yaml
auth:
  type: oauth
  token: OAUTH_TOKEN_ENV      # Name of environment variable
```

- **Description**: Pre-configured OAuth token read from environment.
- **Use Case**: When you already have a long-lived OAuth token from a secrets manager.

### OAuth (Runtime Token Fetch)

```yaml
auth:
  type: oauth
  username: OAUTH_USER_ENV
  password: OAUTH_PASS_ENV
  getTokenEndpoint: "https://auth.example.com/token"
  getTokenMethod: "POST"      # GET or POST
  tokenKey: "access_token"    # JSON key in response
  tokenHeaders:               # Optional
    Content-Type: "application/x-www-form-urlencoded"
  bodyData:                   # Optional
    type: json
    data:
      grant_type: "client_credentials"
      scope: "read:metrics"
```

- **Description**: Fetches OAuth token at runtime before each scrape (or with caching).
- **Fields**:
  - `getTokenEndpoint`: URL to fetch token from
  - `getTokenMethod`: HTTP method (default: `POST`)
  - `tokenKey`: JSON field containing the token in the response
  - `tokenHeaders`: Optional headers for token request
  - `bodyData`: Optional body payload (type: `raw` or `json`)
- **Use Case**: APIs requiring dynamic token acquisition (e.g., OAuth2 client credentials flow).

### Azure AD Authentication

```yaml
auth:
  type: azuread
  client_id: AZURE_CLIENT_ID_ENV
  client_secret: AZURE_CLIENT_SECRET_ENV
  tokenEndpoint: "https://login.microsoftonline.com/{tenant}/oauth2/token"
  resource: "https://api.example.com"
```

- **Description**: Azure AD service principal authentication.
- **Use Case**: Accessing Azure-protected APIs or services like Microsoft Dynamics, Azure Resource Manager, etc.

---

## Scrape Configuration

The `scrape` section controls **how** and **when** the API is called.

### `scrape.type`
- **Type**: `string`
- **Required**: ✅ Yes
- **Options**: `range`, `instant`
- **Description**:
  - `range`: Scrapes data over a time window (e.g., "get metrics from 1 hour ago to now")
  - `instant`: Scrapes current state without time parameters (e.g., "get current active users")
- **Use Case**: Use `range` for historical/time-series APIs, `instant` for snapshot APIs.

### `scrape.httpMethod`
- **Type**: `string`
- **Default**: `"GET"`
- **Options**: `GET`, `POST`
- **Description**: HTTP method to use for the API request.
- **Use Case**: Most APIs use `GET`. Use `POST` if the API requires it (e.g., complex queries in body).

### `scrape.runFirstScrape`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: If `true`, runs a scrape immediately when the scraper starts or when this source is newly added. Otherwise, waits for the first scheduled interval.
- **Use Case**: Enable to get initial data immediately on startup.

### `scrape.timeFormat`
- **Type**: `string` (Python `strftime` format)
- **Default**: Uses `scraper.defaultTimeFormat`
- **Global Override**: ✅ Overrides `scraper.defaultTimeFormat` for this source
- **Description**: Format string for datetime values sent to the API.
- **Examples**:
  - `"%Y-%m-%dT%H:%M:%SZ"` → `2025-11-28T10:15:00Z`
  - `"%s"` → `1732790100` (Unix timestamp)
  - `"%Y-%m-%d"` → `2025-11-28`
- **Use Case**: Override if this API expects a different date format than your global default.

### `scrape.maxConcurrency`
- **Type**: `integer`
- **Default**: Uses `scraper.defaultSourceConcurrency`
- **Global Override**: ✅ Overrides `scraper.defaultSourceConcurrency` for this source
- **Description**: Maximum number of concurrent HTTP requests for this source (e.g., when using `parallelWindow`).
- **Use Case**: Increase for APIs that can handle high concurrency, decrease for rate-limited APIs.

### `scrape.parallelWindow`
- **Type**: `object`
- **Applies to**: `type: range` only
- **Description**: Splits a large time range into smaller sub-windows that are scraped in parallel.
- **Fields**:
  - `unit`: `minutes`, `hours`, or `days`
  - `value`: Size of each sub-window
- **Example**:
  ```yaml
  parallelWindow:
    unit: hours
    value: 1  # Split into 1-hour chunks
  ```
- **Use Case**: If scraping 24 hours of data, this splits it into 24 parallel 1-hour requests for faster collection.

### `scrape.rangeKeys` (for `type: range`)

Controls how time ranges are passed to the API.

#### Explicit Start/End Keys

```yaml
scrape:
  type: range
  rangeKeys:
    startKey: "from"
    endKey: "to"
    firstScrapeStart: "2025-01-01T00:00:00Z"
    dateFormat: "%Y-%m-%dT%H:%M:%SZ"  # Optional override
```

- **`startKey`**: Query parameter name for range start (e.g., `from`, `start_time`, `since`)
- **`endKey`**: Query parameter name for range end (e.g., `to`, `end_time`, `until`)
- **`firstScrapeStart`**: Historical start time for the first scrape (optional)
- **`dateFormat`**: Legacy format override (prefer `scrape.timeFormat`)
- **Result**: `?from=2025-11-28T10:00:00Z&to=2025-11-28T11:00:00Z`

#### Relative Time Window

```yaml
scrape:
  type: range
  rangeKeys:
    unit: hours
    value: 1
    takeNegative: true
```

- **`unit`**: `minutes`, `hours`, `days`, `weeks`, or `months`
- **`value`**: Number of units (or `"from-config"` to auto-calculate from `frequency`)
- **`takeNegative`**: Convert value to negative (e.g., `-1` for "last 1 hour")
- **Result**: `?hours=-1` (depending on API's parameter name)

### `scrape.urlEncodeTimeKeys`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: URL-encode the time values in query parameters.
- **Use Case**: Enable if the API expects encoded datetime strings (e.g., `2025-11-28T10%3A15%3A00Z`).

### `scrape.extraHeaders`
- **Type**: `object` (key-value pairs)
- **Description**: Additional HTTP headers to send with every request.
- **Example**:
  ```yaml
  extraHeaders:
    Accept: "application/json"
    X-Custom-Header: "value"
  ```

### `scrape.extraArgs`
- **Type**: `object`
- **Description**: Additional query parameters (GET) or body fields (POST) to include in requests.
- **URL Encoding**: By default, values are URL-encoded for GET requests. To disable encoding for a specific value:
  ```yaml
  extraArgs:
    format: json              # Will be URL-encoded
    filter:
      noEncodeValue: "status:active,type:user"  # Won't be encoded
  ```

---

## Data Extraction and Processing

### `dataKey`
- **Type**: `string`
- **Optional**: Yes
- **Description**: Path to the data array in the API response. If omitted, the entire response is treated as the data.
- **Path Syntax**:
  - Dot notation: `"data.records"` → `response["data"]["records"]`
  - Array expansion: `"items[].value"` → extract `value` from all items
  - Array indexing: `"items[0].value"` → first item only
  - Array slicing: `"items[1:3].value"` → items at index 1 and 2
  - Root prefix: `"$root.metadata"` → field at response root
  - Literal dots: Use `"/.`" as separator if keys contain periods
- **Examples**:
  ```yaml
  # Response: {"data": {"records": [...]}}
  dataKey: "data.records"
  
  # Response: [{"id": 1}, {"id": 2}]
  dataKey: null  # Omit, treat whole response as array
  
  # Response: {"results": [{"items": [...]}, {"items": [...]}]}
  dataKey: "results[].items"  # Flatten all items
  ```

---

## Filters and Limits

Apply filters to reduce noise and limit data volume before metrics/logs are generated.

### `filters.drop`
- **Description**: Discard records matching ANY of these rules.
- **Structure**:
  ```yaml
  filters:
    drop:
      - any:  # Drop if ANY predicate matches
          - field: "status"
            matchType: "equals"
            value: "draft"
          - field: "type"
            matchType: "in"
            value: ["test", "staging"]
  ```
- **Match Types**:
  - `equals`: Exact match
  - `not_equals`: Does not match
  - `in`: Value is in list
  - `regex`: Matches regular expression
- **Use Case**: Drop test data, internal records, or known noisy events.

### `filters.keep`
- **Description**: After drop rules, ONLY keep records matching ALL predicates in at least one keep rule.
- **Structure**:
  ```yaml
  filters:
    keep:
      - all:  # Keep if ALL predicates match
          - field: "status"
            matchType: "equals"
            value: "completed"
          - field: "priority"
            matchType: "in"
            value: ["high", "critical"]
  ```
- **Use Case**: Focus on specific record types (e.g., only completed high-priority items).

### `filters.limits.maxRecordsPerScrape`
- **Type**: `integer`
- **Description**: Maximum number of records to process per scrape after filters are applied.
- **Use Case**: Prevent memory issues or OTEL payload size limits with high-volume APIs.
- **Example**:
  ```yaml
  filters:
    limits:
      maxRecordsPerScrape: 1000
  ```

---

## Delta Detection (Deduplication)

Prevent duplicate records from being emitted when the same data is scraped multiple times.

### `deltaDetection.enabled`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: Enable fingerprint-based deduplication for this source.
- **How it works**: Each record is fingerprinted and stored. On subsequent scrapes, only new/changed records are emitted.

### `deltaDetection.fingerprintMode`
- **Type**: `string`
- **Default**: `"full_record"`
- **Options**:
  - `full_record`: Hash the entire record
  - `keys`: Hash only specific fields (defined in `fingerprintKeys`)
- **Use Case**: Use `keys` for APIs where only certain fields determine uniqueness (e.g., ID + timestamp).

### `deltaDetection.fingerprintKeys`
- **Type**: `array` of `string`
- **Required when**: `fingerprintMode: keys`
- **Description**: List of field paths to use for fingerprinting (same syntax as `dataKey`).
- **Example**:
  ```yaml
  deltaDetection:
    enabled: true
    fingerprintMode: keys
    fingerprintKeys:
      - userId
      - id
      - timestamp
  ```

### `deltaDetection.ttlSeconds`
- **Type**: `integer`
- **Default**: Uses `scraper.fingerprintStore.defaultTtlSeconds`
- **Global Override**: ✅ Yes
- **Description**: How long to remember fingerprints (in seconds). After TTL expires, the same record can be emitted again.

### `deltaDetection.maxEntries`
- **Type**: `integer`
- **Default**: Uses `scraper.fingerprintStore.maxEntriesPerSource`
- **Global Override**: ✅ Yes
- **Description**: Maximum fingerprints to store for this source (LRU eviction).

---

## Metrics Configuration

Define what metrics to extract from API data. All metrics support both `dataKey` (extract from record field) and `fixedValue` (emit constant).

### Gauge Metrics (`gaugeReadings`)

Gauges represent **point-in-time values** (e.g., queue depth, last run duration, temperature).

```yaml
gaugeReadings:
  - name: "queue_depth"
    dataKey: "items_pending"
    unit: "1"
  
  - name: "processing_time"
    dataKey: "duration_ms"
    unit: "milliseconds"
  
  - name: "health_status"
    fixedValue: 1  # Emit 1 for every record
    unit: "1"
```

- **`name`**: Metric name (will be prefixed by OTEL conventions)
- **`dataKey`**: Field path to extract value from (use `$root.` for root-level fields)
- **`fixedValue`**: Constant value to emit (overrides `dataKey`)
- **`unit`**: Unit of measurement (supports all OTEL units: `milliseconds`, `seconds`, `bytes`, `1`, etc.)

### Counter Metrics (`counterReadings`)

Counters represent **monotonically increasing counts** (e.g., total requests, error count).

```yaml
counterReadings:
  - name: "api_requests_total"
    valueKey: "request_count"  # Add this value to counter
    unit: "1"
  
  - name: "records_processed"
    # No valueKey = each record adds 1
    unit: "1"
  
  - name: "errors_total"
    fixedValue: 1
```

- **`valueKey`**: Field to extract counter increment from (optional, defaults to 1 per record)

### Histogram Metrics (`histogramReadings`)

Histograms capture **distributions** of values (e.g., request duration, payload size).

```yaml
histogramReadings:
  - name: "request_duration_seconds"
    dataKey: "duration_ms"
    unit: "milliseconds"
    buckets: [10, 50, 100, 500, 1000, 5000]
```

- **`buckets`**: List of bucket boundaries (must be sorted ascending)

---

## Attributes and Logs

### `attributes`

Attach key-value pairs to telemetry as resource/span attributes.

```yaml
attributes:
  - name: "user_id"
    dataKey: "userId"
  
  - name: "integration_system"
    dataKey: "system_name"
  
  - name: "status_code"
    dataKey: "status"
    asMetric:  # Also emit as a metric
      metricName: "status_numeric"  # Optional override
      valueMapping:
        "success": 1
        "failure": 0
        "pending": 0.5
      unit: "1"
```

- **`asMetric`**: Optionally convert attribute values to numeric metrics using value mapping.

### `logStatusField`

Control log severity based on a field value.

```yaml
logStatusField:
  name: "status"
  info:
    value: ["success", "completed"]
    matchType: "in"
  warning:
    value: "pending"
    matchType: "equals"
  error:
    value: ["failed", "error"]
    matchType: "in"
```

- **Match Types**: `equals` (exact match) or `in` (value in list)
- **Default**: If field doesn't match any rule, logs are emitted as `info`

---

## Complete Examples

### Example 1: Simple Instant Scrape (Public API)

```yaml
sources:
  - name: "json-placeholder"
    baseUrl: "https://jsonplaceholder.typicode.com"
    endpoint: "/posts"
    frequency: "5min"
    
    scrape:
      type: instant
      runFirstScrape: true
    
    counterReadings:
      - name: "posts_total"
        unit: "1"
    
    attributes:
      - name: "user_id"
        dataKey: "userId"
      - name: "post_id"
        dataKey: "id"
```

### Example 2: Range Scrape with Authentication

```yaml
sources:
  - name: "stripe-payments"
    baseUrl: "https://api.stripe.com"
    endpoint: "/v1/charges"
    frequency: "15min"
    
    auth:
      type: apikey
      keyName: "Authorization"
      keyValue: STRIPE_API_KEY
    
    scrape:
      type: range
      timeFormat: "%s"  # Unix timestamp
      runFirstScrape: true
      rangeKeys:
        startKey: "created[gte]"
        endKey: "created[lte]"
        firstScrapeStart: "2025-01-01T00:00:00Z"
      extraArgs:
        limit: 100
    
    dataKey: "data"
    
    deltaDetection:
      enabled: true
      fingerprintMode: keys
      fingerprintKeys:
        - id
    
    counterReadings:
      - name: "charges_total"
        valueKey: "amount"
    
    histogramReadings:
      - name: "charge_amount"
        dataKey: "amount"
        unit: "1"
        buckets: [100, 500, 1000, 5000, 10000, 50000]
```

### Example 3: Advanced with Filters and Parallel Windows

```yaml
sources:
  - name: "workday-integrations"
    baseUrl: "https://wd5-services1.myworkday.com"
    endpoint: "/ccx/service/customreport2/tenant/report"
    frequency: "1h"
    allowOverlapScans: false
    
    auth:
      type: basic
      username: WORKDAY_USER
      password: WORKDAY_PASS
    
    scrape:
      type: range
      httpMethod: GET
      runFirstScrape: true
      timeFormat: "%Y-%m-%dT%H:%M:%S-00:00"
      maxConcurrency: 8
      parallelWindow:
        unit: hours
        value: 2  # Split into 2-hour chunks
      rangeKeys:
        startKey: "From_Second"
        endKey: "To_Second"
        firstScrapeStart: "2025-11-01T00:00:00-00:00"
      extraHeaders:
        Content-Type: "application/x-www-form-urlencoded"
      extraArgs:
        format: json
    
    dataKey: "Report_Entry"
    
    filters:
      drop:
        - any:
            - field: "Status"
              matchType: "equals"
              value: "Test"
      keep:
        - all:
            - field: "Status"
              matchType: "in"
              value: ["Completed", "Failed", "Running"]
      limits:
        maxRecordsPerScrape: 5000
    
    deltaDetection:
      enabled: true
      fingerprintMode: keys
      fingerprintKeys:
        - Integration_System
        - Actual_Start_Date_and_Time
        - Status
      ttlSeconds: 3600
      maxEntries: 10000
    
    gaugeReadings:
      - name: "integration_duration"
        dataKey: "Total_Duration__ms_"
        unit: "milliseconds"
      - name: "queue_time"
        dataKey: "Queued_Time__ms_"
        unit: "milliseconds"
    
    counterReadings:
      - name: "integration_runs"
    
    attributes:
      - name: "integration_system"
        dataKey: "Integration_System"
      - name: "start_time"
        dataKey: "Actual_Start_Date_and_Time"
      - name: "status"
        dataKey: "Status"
        asMetric:
          metricName: "integration_status"
          valueMapping:
            "Completed": 1
            "Failed": 0
            "Running": 0.5
    
    logStatusField:
      name: "Status"
      info:
        value: "Completed"
      warning:
        value: "Running"
      error:
        value: "Failed"
```

---

## Field Reference Summary

| Field | Required | Type | Global Override | Description |
|-------|----------|------|-----------------|-------------|
| `name` | ✅ | string | - | Service name for telemetry |
| `frequency` | ✅ | string | - | Scrape interval |
| `baseUrl` | ✅ | string | - | API base URL |
| `endpoint` | ✅ | string | - | API endpoint path |
| `allowOverlapScans` | ❌ | boolean | ✅ | Allow concurrent scrapes |
| `emitLogs` | ❌ | boolean | - | Enable log generation |
| `auth` | ❌ | object | - | Authentication config |
| `scrape.type` | ✅ | string | - | `range` or `instant` |
| `scrape.httpMethod` | ❌ | string | - | `GET` or `POST` |
| `scrape.timeFormat` | ❌ | string | ✅ | Datetime format override |
| `scrape.maxConcurrency` | ❌ | integer | ✅ | Concurrency limit |
| `dataKey` | ❌ | string | - | Path to data array |
| `deltaDetection.ttlSeconds` | ❌ | integer | ✅ | Fingerprint TTL |
| `deltaDetection.maxEntries` | ❌ | integer | ✅ | Max fingerprints |

---

## Detailed Examples by Category

For comprehensive, working examples of specific configuration aspects, see these specialized directories:

### 🔐 [Authentication Examples](auth/)
Complete examples for all supported authentication methods:
- **[No Authentication](auth/no-auth.yaml)** - Public APIs
- **[Basic Auth](auth/basic-auth.yaml)** - Username/password authentication
- **[API Key Auth](auth/apikey-auth.yaml)** - Header-based API keys (Stripe example)
- **[OAuth Static Token](auth/oauth-static-token.yaml)** - Pre-generated tokens (GitHub example)
- **[OAuth Runtime Token](auth/oauth-runtime-token.yaml)** - Dynamic token acquisition
- **[Azure AD Auth](auth/azuread-auth.yaml)** - Microsoft Azure/Office 365 APIs

Each example includes:
- ✅ Complete working configuration
- ✅ Environment variable setup instructions
- ✅ Real-world API examples
- ✅ Security best practices

### ⏱️ [Scrape Types Examples](scrape-types/)
Comprehensive examples for both scrape types:
- **[Range-Type Scraping](scrape-types/range-type.yaml)** - Time-window based data collection
- **[Instant-Type Scraping](scrape-types/instant-type.yaml)** - Current state snapshots

Key differences explained:
- When to use range vs instant
- Time parameter configuration
- Parallel window processing
- Historical backfill patterns

### 📊 [Measurement Types Examples](measurements/)
Detailed examples for all three metric types:
- **[Counter Metrics](measurements/counters.yaml)** - Monotonically increasing values
- **[Histogram Metrics](measurements/histograms.yaml)** - Value distributions and percentiles
- **[Gauge Metrics](measurements/gauges.yaml)** - Point-in-time current values

Each shows all value configuration options:
- From data fields (`dataKey`/`valueKey`)
- Fixed values (`fixedValue`)
- Default behaviors
- **How labels come from attributes** (no separate labels field!)

### 🎯 Why Use These Examples?

- **Copy-Paste Ready**: All examples are complete and functional
- **Real APIs**: Based on actual services (Stripe, GitHub, Azure, etc.)
- **Best Practices**: Security, performance, and operational considerations
- **Error Handling**: Shows what happens when things go wrong
- **Production Patterns**: Suitable for real-world deployments

---

## Tips & Best Practices

1. **Start Simple**: Begin with `type: instant`, no auth, and basic counters. Add complexity incrementally.

2. **Use Delta Detection**: Enable for APIs that may return duplicate data across scrapes.

3. **Filter Early**: Use `filters.drop` to discard noise before metrics are generated (saves memory and OTEL payload size).

4. **Parallel Windows**: For large historical backfills or wide time ranges, use `parallelWindow` to speed up collection.

5. **Monitor Concurrency**: Watch `scrape.maxConcurrency` and `scraper.maxGlobalConcurrency` to avoid overwhelming APIs.

6. **Secure Credentials**: Always use environment variables for secrets. Never hardcode credentials in `config.yaml`.

7. **Test with `dryRun`**: Set `scraper.dryRun: true` globally to see what metrics/logs would be emitted without actually sending them.

8. **Label Cardinality**: Be careful with counter/histogram labels. High-cardinality labels (e.g., user IDs) can explode your metric storage.

---

For global configuration options, see [`CONFIGURATION/global/README.md`](../global/README.md).
