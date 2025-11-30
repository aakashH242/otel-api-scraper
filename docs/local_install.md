# Local Installation

This guide covers getting API2OTEL running locally using Python and `uv` for dependency management.

## Prerequisites

- **Python 3.10+**
- **uv** (recommended) or pip for dependency management
- **Git** for cloning the repository
- A running **OpenTelemetry Collector** listening for OTLP (gRPC or HTTP)

## Installation Methods

### Option 1: Using uv (Recommended)

`uv` is a fast, modern Python package installer and resolver. It's the recommended way to set up API2OTEL.

#### 1. Clone the Repository

```bash
git clone https://github.com/aakashH242/otel-api-scraper.git
cd otel-api-scraper
```

#### 2. Install Dependencies

```bash
uv sync
```

This installs all dependencies specified in `pyproject.toml` into a virtual environment.

#### 3. Verify Installation

```bash
# Check that uv created a virtual environment
ls .venv

# Or run a quick command to verify
uv run python --version
```

#### 4. Create Configuration

Copy the template configuration:

```bash
cp config.yaml.template config.yaml
```

Edit `config.yaml` to set at minimum:

- `scraper.otelCollectorEndpoint` – your collector's OTLP endpoint
- At least one source configuration

**Minimal config example:**

```yaml
scraper:
  otelCollectorEndpoint: "http://localhost:4318"
  otelTransport: "http"  # or "grpc" if using gRPC endpoint
  serviceName: "otel-api-scraper"

sources:
  - name: Dummy-JSON
    baseUrl: https://dummyjson.com
    endpoint: /comments
    frequency: 1m
    scrape:
      type: instant
      extraHeaders:
        Accept: "application/json"
    dataKey: comments
    gaugeReadings:
      - name: comments_count
        dataKey: $root.limit
        unit: "1"
    counterReadings:
      - name: likes_count
        dataKey: likes
        unit: "1"
    attributes:
      - name: user_id
        dataKey: user.id
      - name: comment_id
        dataKey: id
      - name: post_id
        dataKey: postId
    emitLogs: true
    runFirstScrape: true
```

#### 5. Run the Scraper

```bash
uv run otel-api-scraper --config config.yaml
```

Or use the `otel-api-scraper` command directly if the virtual environment is activated:

```bash
source .venv/bin/activate  # On Windows: . .venv\Scripts\activate.ps1
otel-api-scraper --config config.yaml
```

---

### Option 2: Using pip

If you don't have `uv` installed or prefer traditional Python packaging:

#### 1. Clone the Repository

```bash
git clone https://github.com/aakashH242/otel-api-scraper.git
cd otel-api-scraper
```

#### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

#### 3. Install Package

```bash
pip install -e .
```

The `-e` flag installs in editable mode, useful for development.

#### 4. Verify Installation

```bash
python --version
pip list | grep otel-api-scraper
```

#### 5. Create Configuration

```bash
cp config.yaml.template config.yaml
# Edit config.yaml as needed
```

#### 6. Run the Scraper

```bash
otel-api-scraper --config config.yaml
```

---

## Environment Variables

You can configure the scraper via environment variables referenced in `config.yaml`:

```bash
export OTEL_COLLECTOR_ENDPOINT="http://localhost:4318"
export API_KEY="your-api-key"
otel-api-scraper --config config.yaml
```

In `config.yaml`, reference them with `${VAR_NAME}` syntax:

```yaml
scraper:
  otelCollectorEndpoint: "${OTEL_COLLECTOR_ENDPOINT}"

sources:
  - name: my-api
    auth:
      type: apikey
      keyName: "X-API-Key"
      keyValue: "${API_KEY}"
```

---

## Quick Verification

Once running, verify the scraper is working:

1. **Check logs** - The scraper outputs info about each scrape execution
2. **Check metrics** - If you have Prometheus connected to your OTEL collector, query for metrics from the scraper
3. **Check health** (if Admin API enabled) - `curl http://localhost:8080/health`

---

## Troubleshooting

### Command not found: `uv`

Install `uv` using:
```bash
pip install uv
```

Or use system package manager:
```bash
# macOS
brew install uv

# Ubuntu/Debian
sudo apt-get install uv

# Or download from: https://github.com/astral-sh/uv/releases
```

### Command not found: `otel-api-scraper`

Make sure your virtual environment is activated:
```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
```

Or use `uv run`:
```bash
uv run otel-api-scraper --config config.yaml
```

### Python version error

Check your Python version:
```bash
python --version
```

API2OTEL requires Python 3.10 or higher. If you have multiple Python versions, specify the version:
```bash
python3.10 -m venv .venv
```

### Connection refused to OTEL collector

Ensure your OpenTelemetry Collector is running and accessible at the endpoint specified in `config.yaml`:
```bash
curl -v http://localhost:4318/  # If using HTTP
```

---

## Next Steps

- **Read the [Configuration Guide](CONFIGURATION/README.md)** for detailed configuration options
