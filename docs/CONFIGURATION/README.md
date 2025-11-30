# Configuration Documentation

This directory contains comprehensive documentation for configuring the OTEL API Scraper.

Full config explained: https://github.com/aakashH242/otel-api-scraper/blob/main/config.yaml.template

[Download Config Template](../config.yaml.template)


## Documentation Structure

### [Global Configuration](global/README.md)

Settings under the `scraper` section that control the overall behavior of the scraper:

- Telemetry & observability settings
- OTEL collector connection
- Concurrency limits
- Fingerprint store (delta detection backend)
- Time formatting defaults
- Admin API settings

**Key Topics:**

- Which settings can be overridden at the source level
- Default values and their implications
- Best practices for production deployments

### [Source Configuration](sources/README.md)

Settings for individual API sources under the `sources` section:

- Authentication (Basic, API Key, OAuth, Azure AD)
- Scrape configuration (range vs instant, time windows)
- Data extraction and filtering
- Metrics (gauges, counters, histograms)
- Attributes and logging
- Delta detection per source

**Key Topics:**

- Complete examples for common use cases
- Field reference with override capabilities
- Tips for optimizing API scraping

## Quick Start

1. **Copy the template:**
   ```bash
   cp config.yaml.template config.yaml
   ```

2. **Configure global settings** (`scraper` section):
   - Set your OTEL collector endpoint
   - Choose transport (gRPC or HTTP)
   - Configure concurrency limits
   - See [Global Configuration](global/README.md) for details

3. **Add API sources** (`sources` section):
   - Define each API endpoint you want to scrape
   - Configure authentication
   - Map response fields to metrics/logs
   - See [Source Configuration](sources/README.md) for examples

4. **Set environment variables** for secrets:
   ```bash
   export API_USERNAME="your-username"
   export API_PASSWORD="your-password"
   export ADMIN_SECRET="your-admin-secret"
   ```

5. **Validate your configuration:**
   ```bash
   # Dry run mode - see what would be emitted without sending
   # Set scraper.dryRun: true in config.yaml
   uv run otel-api-scraper
   ```

## Configuration Priority

When the same setting exists at both global and source level:

| Setting | Global Default | Source Override Field | Behavior |
|---------|---------------|----------------------|----------|
| Service Name | `scraper.serviceName` | `sources[].name` | Source name is always used |
| Time Format | `scraper.defaultTimeFormat` | `sources[].scrape.timeFormat` | Source overrides if set |
| Overlap Scans | `scraper.allowOverlapScans` | `sources[].allowOverlapScans` | Source overrides if set |
| Concurrency | `scraper.defaultSourceConcurrency` | `sources[].scrape.maxConcurrency` | Source overrides if set |
| Fingerprint TTL | `scraper.fingerprintStore.defaultTtlSeconds` | `sources[].deltaDetection.ttlSeconds` | Source overrides if set |
| Max Fingerprints | `scraper.fingerprintStore.maxEntriesPerSource` | `sources[].deltaDetection.maxEntries` | Source overrides if set |

**Rule:** Source-level settings always take precedence over global defaults.

## Common Patterns

### Pattern 1: Simple REST API (No Auth)
```yaml
sources:
  - name: "public-api"
    baseUrl: "https://api.example.com"
    endpoint: "/v1/data"
    frequency: "5min"
    scrape:
      type: instant
    counterReadings:
      - name: "records_total"
```

### Pattern 2: Time-Range API with Authentication
```yaml
sources:
  - name: "metrics-api"
    baseUrl: "https://api.example.com"
    endpoint: "/metrics"
    frequency: "15min"
    auth:
      type: apikey
      keyName: "X-API-Key"
      keyValue: API_KEY_ENV
    scrape:
      type: range
      rangeKeys:
        startKey: "from"
        endKey: "to"
    gaugeReadings:
      - name: "response_time_ms"
        dataKey: "responseTime"
        unit: "milliseconds"
```

### Pattern 3: High-Volume API with Deduplication
```yaml
sources:
  - name: "events-api"
    baseUrl: "https://api.example.com"
    endpoint: "/events"
    frequency: "1min"
    scrape:
      type: range
      maxConcurrency: 10
    deltaDetection:
      enabled: true
      fingerprintMode: keys
      fingerprintKeys:
        - event_id
        - timestamp
      ttlSeconds: 3600
    filters:
      limits:
        maxRecordsPerScrape: 5000
```

## Environment Variables

The scraper expects secrets to be provided via environment variables:

| Variable Purpose | Example Variable Name | Where Referenced |
|-----------------|----------------------|------------------|
| Basic Auth | `API_USERNAME`, `API_PASSWORD` | `sources[].auth.username/password` |
| API Key | `API_KEY` | `sources[].auth.keyValue` |
| OAuth Token | `OAUTH_TOKEN` | `sources[].auth.token` |
| Azure AD | `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` | `sources[].auth.client_id/client_secret` |
| Admin Secret | `ADMIN_SECRET` | `scraper.adminSecretEnv` |

**Security Note:** The config file contains the **names** of environment variables, not the actual secrets.

## Validation

The scraper validates your configuration on startup using Pydantic models. Common errors:

- **Missing required fields**: Ensure all required fields are present
- **Invalid enum values**: Check allowed values (e.g., `type: range` not `type: ranged`)
- **Type mismatches**: Ensure booleans are `true`/`false`, numbers are unquoted
- **Range without rangeKeys**: `type: range` requires `rangeKeys` section
- **Fingerprint keys without mode**: `fingerprintKeys` requires `fingerprintMode: keys`

## Testing Your Configuration

1. **Dry Run Mode:**
   ```yaml
   scraper:
     dryRun: true
   ```
   Logs what would be emitted without sending to OTEL collector.

2. **First Scrape:**
   ```yaml
   sources:
     - name: "test-api"
       runFirstScrape: true
   ```
   Runs immediately on startup for testing.

3. **Admin API:**
   ```yaml
   scraper:
     enableAdminApi: true
     adminSecretEnv: "ADMIN_SECRET"
   ```
   Trigger manual scrapes via HTTP API (Coming soon).

## Additional Resources

- [**config.yaml.template**](../config.yaml.template) - Complete reference with all options defined
- [**LOCAL TESTING/**](../LOCAL_TESTING.md) - Docker Compose setup

## Support

For issues or questions:

- Check the detailed docs: [Global](global/README.md) | [Sources](sources/README.md)
- Review explanations in [config.yaml.template](../config.yaml.template)
- See complete working examples in [Sources README](sources/README.md#complete-examples)

