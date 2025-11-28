# 🔌 otel-api-scraper – Any API → 📊 OTEL metrics & logs ✨

> Config-driven async bridge that turns any HTTP/data API into OpenTelemetry metrics and logs. 

![Release](https://img.shields.io/github/v/release/aakashH242/otel-api-scraper?sort=semver)
![Lint](https://img.shields.io/github/actions/workflow/status/aakashH242/otel-api-scraper/ci.yml?branch=main&label=lint)
![Unit Tests](https://img.shields.io/github/actions/workflow/status/aakashH242/otel-api-scraper/ci.yml?branch=main&label=tests)
[![Coverage](https://codecov.io/gh/aakashH242/otel-api-scraper/graph/badge.svg)](https://codecov.io/gh/aakashH242/otel-api-scraper)

For those use-cases when you have data, jobs, or business processes buried behind APIs, reports, or CSV-style endpoints 
and you want them to show up as first-class signals in your existing OTEL stack – without writing a custom exporter for each system.

## 💡 A Common Use-case

Most teams run critical flows on systems they don't control:
- **SaaS platforms**: Workday, ServiceNow, Jira, GitHub, Salesforce…
- **Internal tools**: Only expose REST/HTTP APIs or "download report" endpoints
- **Batch runners**: Emit JSON or CSV, not OTEL signals

They already have an observability stack built on OpenTelemetry, but bridging those APIs typically ends up as messy one-offs:
- Python scripts + cron that nobody owns
- SaaS-specific "exporters" that can't be reused
- CSV dumps and screenshots instead of real metrics

## 🎯 A Solution

Make this reusable and standard:

```
API data → extract records → emit OTLP → your collector
```

No code changes. No vendor lock-in. Everything flows through your existing OTEL stack.

## 📋 What It Does

`otel-api-scraper` is a config-driven async service that:
- **Polls** any HTTP API or data endpoint
- **Extracts** records from JSON/CSV responses  
- **Maps** them to OTEL metrics (gauges, counters, histograms) and logs
- **Emits** everything via OTLP to your collector

```
[ APIs / data endpoints ]
                ↓ HTTP
       otel-api-scraper (this)
                ↓ OTLP (gRPC/HTTP)
      OpenTelemetry Collector
                ↓
      Prometheus / Grafana / Loki / …
```

Entirely YAML-driven. Add/update sources by editing config—no code needed.

## ⚙️ Key Features

### Config-driven scraping
- Declare every source in YAML: frequency (5min, 1h, 1d, …), scrape mode (range with start/end or relative windows; instant snapshots), time formats (global + per-source), and query params (time keys, extra args, URL encoding rules). 
- Add/change sources by editing config—no code.

### Rich auth strategies
- Built-in: Basic (env creds), API key headers, OAuth (static token or runtime via HTTP GET/POST with configurable body/headers and response key), Azure AD client credentials. 
- Tokens are fetched asynchronously and reused per source.

### Async concurrency
- Asyncio/httpx end-to-end. 
- Global concurrency limit plus per-source limits. 
- Range scrapes can split into sub-windows and run in parallel within limits—stay within rate caps while scraping multiple systems.

### Filtering & volume control
- Drop rules, keep rules, and per-scrape caps: "don't emit INFO," "only these IDs," "cap at N records." 
- Protects metrics backends and logging costs from noisy sources.

### Delta detection via fingerprinting
- Fingerprints stored in sqlite or Valkey (Redis-compatible) with configurable TTL and keys/modes. 
- Enables historical scrapes and frequent "last N hours" polls without duplicate spam. 
- Scheduler/last-success share the same backend.

### Metrics mapping
- Metrics live in config: gauges/counters/histograms from `dataKey` or `fixedValue`; attributes can emit counters via `asMetric`; per-source `emitLogs`; severity mapping from record fields. 
- Labels come from attributes and optional metric labels as configured.

### Log emission with severity mapping
- Records become OTEL logs with severity derived from a configured field; attributes align with metrics for easy pivots. 
- Per-source `emitLogs` lets you opt out where logs aren't useful.

## ⚖️ When to Use (and When Not)

**Use this when:**
- ✅ You need metrics/logs about business processes or integrations that only exist as API responses
- ✅ You already have an OTEL collector and want to feed it more sources
- ✅ You need real auth (OAuth, Azure AD) and time windows (historical backfills, relative ranges)
- ✅ You want to deduplicate data or cap volumes with filtering

**You probably don't need this when:**
- ❌ The system already emits OTLP or Prometheus natively—just scrape it directly
- ❌ You only need simple uptime checks—use the collector's `httpcheckreceiver`
- ❌ You're fine writing a one-off Go receiver for a single vendor

## 🚀 Quickstart

### Option A: Native Installation

**Prerequisites**
- Python 3.10+
- A running OTEL collector listening for OTLP (gRPC or HTTP)
- `uv` or `pip` for Python dependencies

1. **Install**
   - Using uv (recommended):
     ```
     uv sync
     ```
   - Or with plain pip:
     ```
     pip install .
     ```

2. **Create a config**
   - Copy the template:
     ```
     cp config.yaml.template config.yaml
     ```
   - Set at least:
     - `scraper.otelCollectorEndpoint` – your collector's OTLP endpoint.
     - One simple source pointing at an HTTP endpoint you control.

   Example minimal source (simplified):
   ```yaml
   scraper:
     otelCollectorEndpoint: "http://otel-collector:4318"
     otelTransport: "http"   # or "grpc"

   sources:
     - name: demo-api
       frequency: "1min"
       auth: null
       baseUrl: "https://httpbin.org"
       endpoint: "/json"
       scrape:
         type: instant
       dataKey: slideshow.slides   # where the records live
       gaugeReadings:
         - name: demo_slide_count
           dataKey: $root.length   # pseudo-example; see real docs
           unit: "1"
       emitLogs: true
   ```
   (Use your real API instead of httpbin; full config semantics are documented in the [configuration docs](./CONFIGURATION/README.md).)

3. **Run the scraper**
   - With uv:
     ```
     uv run otel-api-scraper --config /app/config.yaml
     ```
   - Or with the installed console script:
     ```
     otel-api-scraper --config /app/config.yaml
     ```
   By default, it will schedule the configured source(s), scrape the API, and emit metrics/logs via OTLP to the collector.

4. **Check your telemetry**
   - In your collector logs, look for incoming metrics/logs from service `otel-api-scraper`.
   - In Prometheus/Grafana/Loki, query for the metric/log names you configured.

### Option B: Docker Compose (with Full Stack)

Get the scraper + OTEL collector + Prometheus + Grafana + Loki running in one command:

**Prerequisites**
- Docker & Docker Compose
- No Python installation needed

1. **Start the full stack**
   ```bash
   cd "LOCAL TESTING"
   docker-compose up -d
   ```

2. **Update your config** (optional)
   - Edit `config.yaml` in the repo root
   - The compose setup mounts it into the scraper container
   - Restart the scraper to apply changes:
     ```bash
     docker-compose restart scraper
     ```

3. **Access the dashboards**
   - **Grafana**: http://localhost:3000 (default user: `admin` / `admin`)
   - **Prometheus**: http://localhost:9090
   - **Loki**: http://localhost:3100

4. **View scraper logs**
   ```bash
   docker-compose logs -f scraper
   ```

5. **Stop everything**
   ```bash
   docker-compose down -v
   ```

For more details, see [LOCAL_TESTING.md](LOCAL_TESTING.md) and [LOCAL TESTING/](LOCAL%20TESTING/) config directory.

## 🛠️ Architecture & Internals

The scraper is built as an async-first Python application with clear separation of concerns.

### Core Components

#### **Config & Validation** (`config.py`)
- Pydantic models for strict config schema validation.
- Environment variable resolution via `${VAR_NAME}` syntax.
- Supports: sources, auth types, scrape modes, metrics, filters, attributes, etc.
- Fails fast with clear errors on schema violations.

#### **HTTP Client** (`http_client.py`)
- `AsyncHttpClient`: Wraps `httpx.AsyncClient` with connection pooling and global semaphore.
- Auth strategies (pluggable):
  - `BasicAuth`: Encodes username/password.
  - `ApiKeyAuth`: Injects header (e.g., `X-API-Key`).
  - `OAuthAuth`: Static token or runtime fetch with configurable body/headers.
  - `AzureADAuth`: Client credentials flow to Azure token endpoint.
- Token caching: OAuth tokens fetched once and reused until expiry.
- All requests are async and respect concurrency limits.

#### **Scraper Engine** (`scraper_engine.py`)
- **Window computation**: For range scrapes, calculates start/end based on frequency and last scrape time. Supports relative windows ("last N hours") and historical backfills.
- **Sub-window splitting**: If `parallelWindow` configured, splits a large range into smaller chunks for parallel scraping (e.g., 24-hour range → 12 × 2-hour chunks).
- **Concurrency orchestration**: Maintains per-source semaphores; enforces global limit via shared semaphore in `AsyncHttpClient`.
- **Response handling**: Extracts records via `dataKey` using flexible nested path syntax (dot notation, array indexing, slicing).
- **Error resilience**: Catches HTTP errors, response parsing errors, and logs them without crashing the scraper.

#### **Record Pipeline** (`pipeline.py`)
- **Filtering**: Applies drop/keep rules (any/all predicates with `equals`, `not_equals`, `in`, `regex` matchers).
- **Limits**: Caps records per scrape to prevent memory/storage spikes.
- **Delta detection**: 
  - Fingerprints records (MD5 hash of full record or specified keys).
  - Checks fingerprint store (sqlite or Valkey).
  - Only emits records with unseen fingerprints (within TTL window).
  - Supports per-source TTL/max entries overrides.

#### **Fingerprint Store** (`fingerprints.py`)
- **Backend options**: SQLite (local file) or Valkey (distributed).
- **Storage**: Maps `(source_name, fingerprint)` → `(timestamp, ttl_expires_at)`.
- **Cleanup**: Background task periodically removes expired fingerprints.
- **Orphan cleanup**: Removes fingerprints for sources that have been removed from config.

#### **State Store** (`state.py`)
- Tracks last successful scrape timestamp per source.
- Persists in same backend as fingerprint store.
- Enables resumption after restarts: next scrape picks up where the last one ended (no re-scraping old data).

#### **Telemetry** (`telemetry.py`)
- **SDK initialization**: Sets up OTEL SDK with OTLP exporter (gRPC or HTTP).
- **Metric emission**:
  - **Gauges**: Current values from records (each record sets gauge to its value).
  - **Counters**: Aggregate (sum field values, fixed value per record, or add 1 per record).
  - **Histograms**: Distributions with explicit bucket boundaries.
  - Labels derived from source `attributes`; no separate label definitions.
- **Log emission**: Per-record logs with severity derived from configured field.
- **Attributes**: Added to all telemetry for pivoting/filtering in backends.
- **Dry run**: If `dryRun: true`, logs metric/log summaries to stderr instead of exporting.
- **Self-telemetry**: If `enableSelfTelemetry: true`, emits scraper's own metrics (scrape duration, record counts, errors).

#### **Scheduler** (`scheduler.py`)
- `APScheduler AsyncIOScheduler` integrated into the asyncio event loop.
- Parses frequency strings (`"5min"`, `"1h"`, `"1d"`, etc.) into cron/interval schedules.
- One job per source; each job calls the scraper engine.
- Supports `runFirstScrape: true` to scrape immediately on startup.

#### **Admin API** (`admin_api.py`)
- Optional FastAPI HTTP server on `servicePort` (default 80).
- Endpoints:
  - `GET /health` – health check (always 200).
  - `GET /config` – effective config as JSON (auth-gated).
  - `POST /scrape/{source_name}` – trigger manual scrape (auth-gated).
  - `GET /sources` – list all configured sources (auth-gated).
- Authentication via Bearer token from environment variable (`adminSecretEnv`).

#### **Utils** (`utils.py`)
- **Path extraction** (`lookup_path`): Nested dict/list traversal with dot notation, array indexing, slicing.
- **Datetime handling**: Parse/format with per-source and global format overrides.
- **Frequency parsing** (`parse_frequency`): Convert `"5min"`, `"1h"`, etc. to timedelta.
- **Window slicing** (`window_slices`): Generate sub-windows for parallel scraping.
- **Query building** (`build_query_string`): Construct URL params with optional URL encoding.

#### **Runner** (`runner.py`)
- **Entrypoint**: Loads config, initializes all components, starts scheduler and optional admin API.
- **Cleanup loop**: Background task periodically runs fingerprint store cleanup.
- **Graceful shutdown**: Cancels scheduler, closes HTTP client, flushes telemetry.

## 📚 Documentation

Comprehensive guides and examples for every aspect of the scraper:

- **[Configuration Reference](./CONFIGURATION/README.md)** – Global settings, source settings, all options explained
- **[Authentication Examples](./CONFIGURATION/sources/auth/)** – All 6 auth types with real API examples
- **[Scrape Types Examples](./CONFIGURATION/sources/scrape-types/)** – Range vs instant scraping patterns
- **[Measurement Types Examples](./CONFIGURATION/sources/measurements/)** – Gauge/counter/histogram configuration patterns
- **[Local Testing Stack](./LOCAL_TESTING.md)** – Docker Compose setup with Grafana + Loki + Prometheus + OTEL collector

## 🤝 Contributing

Contributions welcome! Areas of interest:

- New auth strategies (SAML, Kerberos, mTLS, etc.)
- Receiver for additional data formats (XML, Parquet, Protocol Buffers, etc.)
- Built-in connector templates for popular SaaS (Salesforce, Jira, etc.)
- Performance improvements or test coverage
- Documentation and examples

### Development Setup

1. **Clone and install dependencies:**
   ```bash
   git clone <repo-url>
   cd otel-api-scraper
   uv sync --dev
   ```

2. **Install pre-commit hooks:**
   ```bash
   uv run pre-commit install
   uv run pre-commit install --hook-type commit-msg
   ```

3. **Follow conventional commits:**
   All commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) format:
   ```bash
   git commit -m "feat(auth): add SAML authentication support"
   git commit -m "fix(scraper): handle timeout errors properly"  
   git commit -m "docs(readme): update installation instructions"
   ```

4. **Ensure tests pass:**
   - Code must pass linting (ruff)
   - Test coverage must be ≥90%
   - All tests must pass

📋 **For detailed contribution guidelines, see [CONTRIBUTING.md](./CONTRIBUTING.md)** which covers:
- Code quality requirements (100% docstring coverage)
- Testing standards and local stack testing
- Pull request process with commit squashing
- CI/CD pipeline details
- Common development tasks and troubleshooting

## 📄 License

[LICENSE](./LICENSE)

