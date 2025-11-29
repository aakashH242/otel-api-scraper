
# Global Configuration Reference

This document describes all global-level configuration options under the `scraper` section. These settings control the overall behavior of the API-to-OTEL scraper controller.

---

## Table of Contents
- [Telemetry and Observability](#telemetry-and-observability)
- [Service Configuration](#service-configuration)
- [Time and Formatting](#time-and-formatting)
- [Concurrency Control](#concurrency-control)
- [Fingerprint Store (Delta Detection)](#fingerprint-store-delta-detection)
- [Source-Level Overrides](#source-level-overrides)

---

## Telemetry and Observability

### `enableSelfTelemetry`
- **Type**: `boolean`
- **Default**: `false`
- **Source Override**: ❌ No
- **Description**: When enabled, the controller generates telemetry (metrics and logs) about its own operation and sends them to the configured OTEL collector. This includes internal metrics like scrape durations, error counts, and resource usage.
- **Use Case**: Enable this in production to monitor the health and performance of the scraper itself.

### `serviceName`
- **Type**: `string`
- **Default**: `"otel-api-scrapper"`
- **Source Override**: ✅ Yes (via `name` field per source)
- **Description**: The default service name used in OTEL resource attributes when emitting telemetry. Each API source can override this with its own `name` field, which becomes the service name for that source's telemetry.
- **Use Case**: Set a meaningful global name for your scraper deployment. Individual sources will use their own names to distinguish telemetry streams.

### `logLevel`
- **Type**: `string`
- **Default**: `"debug"`
- **Options**: `debug`, `info`, `warn`, `error`
- **Source Override**: ❌ No
- **Description**: Controls the verbosity of controller logs. This affects logs from the scraper framework itself, not the logs generated from API data (which are controlled per source).
- **Use Case**: Use `debug` during development, `info` or `warn` in production.

### `dryRun`
- **Type**: `boolean`
- **Default**: `false`
- **Source Override**: ❌ No
- **Description**: When enabled, the scraper will NOT send any telemetry to the OTEL collector. Instead, it logs what would have been emitted (metrics and logs) to stdout for validation and debugging. No OTEL exporters are initialized.
- **Use Case**: Test your configuration and see what metrics/logs would be generated without actually sending them.

---

## Service Configuration

### `otelCollectorEndpoint`
- **Type**: `string`
- **Required**: ✅ Yes
- **Source Override**: ❌ No
- **Description**: The endpoint URL of your OpenTelemetry collector where all generated metrics and logs are sent.
- **Examples**:
  - `"http://otel-collector:4317"` (gRPC in Docker network)
  - `"http://localhost:4318"` (HTTP on host machine)
  - `"https://otel-collector.example.com:4317"` (TLS-enabled)
- **Use Case**: Point to your OTEL collector. Use container DNS names when running in Docker, `localhost` when running on the host.

### `otelTransport`
- **Type**: `string`
- **Default**: `"grpc"`
- **Options**: `grpc`, `http`
- **Source Override**: ❌ No
- **Description**: The transport protocol to use for OTLP exports. gRPC is more efficient; HTTP is more firewall-friendly.
- **Use Case**: Use `grpc` for better performance (port 4317), `http` if gRPC is blocked (port 4318).

### `enforceTls`
- **Type**: `boolean`
- **Default**: `true`
- **Source Override**: ❌ No
- **Description**: When `true`, enforces TLS/SSL when connecting to the OTEL collector. Set to `false` for local development with `http://` endpoints.
- **Use Case**: Set to `false` for local testing, `true` in production with HTTPS endpoints.

### `terminateGracefully`
- **Type**: `boolean`
- **Default**: `true`
- **Source Override**: ❌ No
- **Description**: When the scraper receives a shutdown signal, it waits for in-flight scrapes to complete before exiting if this is `true`. If `false`, it terminates immediately.
- **Use Case**: Keep as `true` to avoid data loss. Set to `false` if you need fast shutdowns.

### `servicePort`
- **Type**: `integer`
- **Default**: `80`
- **Source Override**: ❌ No
- **Description**: The HTTP port on which the scraper exposes its admin API, health checks, and other HTTP endpoints.
- **Use Case**: Change this if port 80 conflicts with other services (e.g., use 8080).

### `enableAdminApi`
- **Type**: `boolean`
- **Default**: `false`
- **Source Override**: ❌ No
- **Description**: Enables the admin REST API which allows you to trigger manual scrapes, list configured sources, and view the effective configuration at runtime.
- **Use Case**: Enable this for operational control. Secure it with `adminSecretEnv`.

### `adminSecretEnv`
- **Type**: `string`
- **Required**: Only when `enableAdminApi: true`
- **Source Override**: ❌ No
- **Description**: Name of the environment variable containing the secret token for authenticating admin API requests.
- **Example**: `"ADMIN_SECRET"` → the scraper reads `os.environ["ADMIN_SECRET"]`
- **Use Case**: Set this to secure your admin API. Clients must send this token in requests.

---

## Time and Formatting

### `defaultTimeFormat`
- **Type**: `string` (Python `strftime` format)
- **Default**: `"%Y-%m-%dT%H:%M:%S%z"`
- **Source Override**: ✅ Yes (via `scrape.timeFormat` or `rangeKeys.dateFormat`)
- **Description**: The default format string used to format datetime values when making API requests (start/end times). This is a Python `strftime` format string.
- **Examples**:
  - `"%Y-%m-%dT%H:%M:%S%z"` → `2025-11-28T10:15:00+0000`
  - `"%Y-%m-%d %H:%M:%S"` → `2025-11-28 10:15:00`
  - `"%s"` → Unix timestamp (seconds since epoch)
- **Use Case**: Set this to match what your APIs expect. Override per source if different APIs need different formats.

---

## Concurrency Control

### `allowOverlapScans`
- **Type**: `boolean`
- **Default**: `false`
- **Source Override**: ✅ Yes (via source-level `allowOverlapScans`)
- **Description**: Global default for whether scrapes can overlap. If `false`, a source will not start a new scrape while a previous one is still running. Each source can override this.
- **Use Case**: Set to `true` if your APIs can handle overlapping requests. Override per source for fine-grained control.

### `maxGlobalConcurrency`
- **Type**: `integer`
- **Default**: `10`
- **Source Override**: ❌ No (but sources have their own limits)
- **Description**: Maximum number of concurrent HTTP requests allowed across ALL sources at any given time. This is a hard global limit enforced by the controller.
- **Use Case**: Prevent the scraper from overwhelming your network or downstream APIs. Adjust based on your infrastructure capacity.

### `defaultSourceConcurrency`
- **Type**: `integer`
- **Default**: `4`
- **Source Override**: ✅ Yes (via `scrape.maxConcurrency`)
- **Description**: Default maximum number of concurrent HTTP requests per individual source. Each source can override this with its own `scrape.maxConcurrency` setting.
- **Use Case**: Set a reasonable default. Override for sources that can handle higher concurrency or need to be throttled.

---

## Fingerprint Store (Delta Detection)

The fingerprint store is used for delta detection - preventing duplicate records from being emitted when the same data is scraped multiple times.

### `fingerprintStore.backend`
- **Type**: `string`
- **Default**: `"sqlite"`
- **Options**: `sqlite`, `valkey`, `redis`
- **Source Override**: ❌ No
- **Description**: The storage backend for fingerprints.
  - `sqlite`: Local file-based storage, suitable for single-instance deployments
  - `valkey` / `redis`: External Valkey/Redis instance, suitable for distributed/HA deployments
- **Use Case**: Use `sqlite` for simple deployments. Use `valkey`/`redis` if running multiple scraper instances that need to share fingerprint state.

### `fingerprintStore.maxEntriesPerSource`
- **Type**: `integer`
- **Default**: `50000`
- **Source Override**: ✅ Yes (via `deltaDetection.maxEntries`)
- **Description**: Maximum number of fingerprints to store per source. When this limit is reached, older fingerprints are evicted using an LRU policy.
- **Use Case**: Adjust based on your data volume. Higher values mean longer duplicate detection windows but more memory/storage usage.

### `fingerprintStore.defaultTtlSeconds`
- **Type**: `integer`
- **Default**: `86400` (24 hours)
- **Source Override**: ✅ Yes (via `deltaDetection.ttlSeconds`)
- **Description**: How long fingerprints are kept before being eligible for cleanup. After TTL expires, duplicates may be emitted again.
- **Use Case**: Set based on how long you want to suppress duplicates. 24 hours is reasonable for daily scrapes.

### `fingerprintStore.cleanupIntervalSeconds`
- **Type**: `integer`
- **Default**: `3600` (1 hour)
- **Source Override**: ❌ No
- **Description**: How often the background cleanup job runs to remove expired fingerprints.
- **Use Case**: Lower values = more frequent cleanup (less storage) but more overhead. Adjust based on your TTL and data volume.

### `fingerprintStore.lockRetries`
- **Type**: `integer`
- **Default**: `5`
- **Source Override**: ❌ No
- **Description**: Number of retries when SQLite reports "database is locked" (applies to sqlite backend only). This helps prevent failures when multiple processes access the database concurrently.
- **Use Case**: Increase this value if you experience lock contention with SQLite. Set to 0 to disable retries.

### `fingerprintStore.lockBackoffSeconds`
- **Type**: `float`
- **Default**: `0.1` (100ms)
- **Source Override**: ❌ No
- **Description**: Initial backoff in seconds between lock retries. The backoff doubles exponentially up to 1 second maximum.
- **Use Case**: Adjust this if you need to tune retry timing. Lower values retry faster, higher values reduce CPU spinning.

### `fingerprintStore.sqlite.path`
- **Type**: `string`
- **Default**: `"./scraper_fingerprints.db"`
- **Source Override**: ❌ No
- **Description**: File path for the SQLite database (only used when `backend: sqlite`). The file is created if it doesn't exist.
- **Use Case**: Change this if you want to store the database in a different location (e.g., a persistent volume in Docker).

### `fingerprintStore.valkey.*`
- **Source Override**: ❌ No
- **Description**: Valkey/Redis connection settings (only used when `backend: valkey` or `redis`).
  - `host`: Redis server hostname/IP
  - `port`: Redis server port (default 6379)
  - `db`: Redis database index (default 0)
  - `password`: Authentication password (optional)
  - `ssl`: Enable SSL/TLS connection (default false)
- **Use Case**: Configure these when using an external Redis/Valkey instance.

---

## Source-Level Overrides

The following global settings can be overridden at the individual source level:

| Global Setting | Source-Level Override | Field Path |
|----------------|----------------------|------------|
| `serviceName` | ✅ Yes | `sources[].name` |
| `defaultTimeFormat` | ✅ Yes | `sources[].scrape.timeFormat` or `sources[].scrape.rangeKeys.dateFormat` |
| `allowOverlapScans` | ✅ Yes | `sources[].allowOverlapScans` |
| `defaultSourceConcurrency` | ✅ Yes | `sources[].scrape.maxConcurrency` |
| `fingerprintStore.maxEntriesPerSource` | ✅ Yes | `sources[].deltaDetection.maxEntries` |
| `fingerprintStore.defaultTtlSeconds` | ✅ Yes | `sources[].deltaDetection.ttlSeconds` |

**Override Priority**: Source-level settings always take precedence over global defaults when both are specified.

---

## Example Configuration

```yaml
scraper:
  enableSelfTelemetry: true
  serviceName: "my-api-scraper"
  logLevel: "info"
  
  otelCollectorEndpoint: "http://otel-collector:4318"
  otelTransport: "http"
  enforceTls: false
  
  defaultTimeFormat: "%Y-%m-%dT%H:%M:%S%z"
  maxGlobalConcurrency: 20
  defaultSourceConcurrency: 5
  
  enableAdminApi: true
  adminSecretEnv: "SCRAPER_ADMIN_SECRET"
  
  fingerprintStore:
    backend: "sqlite"
    maxEntriesPerSource: 100000
    defaultTtlSeconds: 86400
    cleanupIntervalSeconds: 3600
    sqlite:
      path: "/data/fingerprints.db"

sources:
  - name: "my-api"
    # This source overrides the default concurrency
    scrape:
      maxConcurrency: 10
    # ... rest of source config
```