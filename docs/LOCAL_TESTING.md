# Local Testing: Grafana + Loki + Prometheus + OTEL Collector

This guide spins up a local observability stack (Grafana, Loki, Prometheus, OTEL Collector) so you can run and validate the scraper end-to-end. Requires Docker and docker-compose (or compatible, e.g., Podman + podman-compose).
You can also adjust these values for your deployment needs.

## Prerequisites
- Docker (or Podman) and docker-compose available on your PATH.
- The scraper config ([`config.yaml`](config.yaml)) should point to the local OTLP collector at `http://localhost:4317` (set `scraper.otelCollectorEndpoint` and `otelTransport: grpc`, or HTTP if you prefer).

## Stack Contents
- **Grafana**: UI to inspect metrics/logs.
- **Prometheus**: Scrapes OTEL collector's metrics endpoint.
- **Loki**: Stores logs from OTEL collector.
- **OTEL Collector**: Receives OTLP metrics/logs and forwards to Prometheus (via Prometheus scrape) and Loki.

## Quickstart

1. Use the provided stack under `LOCAL_TESTING/`:
   - Compose: [`LOCAL_TESTING/compose.yaml`](LOCAL_TESTING/compose.yaml)
   - Collector config: [`LOCAL_TESTING/config/collector.yaml`](LOCAL_TESTING/config/collector.yaml)
   - Prometheus config: [`LOCAL_TESTING/config/prometheus.yml`](LOCAL_TESTING/config/prometheus.yml)
   - Loki config: [`LOCAL_TESTING/config/loki-config.yml`](LOCAL_TESTING/config/loki-config.yml)
   - Grafana datasources: [`LOCAL_TESTING/config/grafana-datasources.yaml`](LOCAL_TESTING/config/grafana-datasources.yaml)
   - Grafana ini: [`LOCAL_TESTING/config/grafana.ini`](LOCAL_TESTING/config/grafana.ini)

2. Start the observability stack:
   ```bash
   docker-compose -f "LOCAL_TESTING/compose.yaml" up -d
   ```

## Running the Scraper

### Option 1: Run scraper as part of the stack (Recommended)

The compose file includes a `scraper` service that runs in the same network. This allows it to communicate with `otel-collector` via DNS.
Please ensure you set the OTLP endpoint in the config to http://otel-collector:4317

```bash
# Start everything including the scraper
docker-compose -f "LOCAL_TESTING/compose.yaml" up -d

# View scraper logs
docker-compose -f "LOCAL_TESTING/compose.yaml" logs -f scraper
```

**Network access**: The scraper can use `http://otel-collector:4318` or `http://otel-collector:4317`

### Option 2: Run scraper outside Docker (on host machine)
If you want to run the scraper directly on your host machine (not in a container):

```bash
# Make sure config.yaml points to localhost
# otelCollectorEndpoint: http://localhost:4318  # or grpc://localhost:4317

# Run the scraper
uv run otel-api-scraper
```

**Network access**: The scraper must use `localhost:4318` or `localhost:4317` because it's outside the Docker network.

### Option 3: Run scraper in a separate container
If you run the scraper in a separate container NOT defined in this compose file, you need to connect it to the `otel-network`:

```bash
docker run --network local-testing_otel-network \
  -e OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
  your-scraper-image
```

**Network access**: Use `otel-collector:4318` or `otel-collector:4317` when connected to the network.

## Accessing the Stack
```
SCRAPER_CONFIG=./config.yaml uv run otel-api-scraper 
# configure OTel endpoint to http://localhost:4317 when running outside container
# or inside the container, ensure config points to http://otel-collector:4317
```

- Inspect:
  - Grafana: http://localhost:3000 (default creds admin/admin), browse Prometheus metrics and Loki logs.
  - Prometheus: http://localhost:9090
  - Loki API: http://localhost:3100

## Tips
- When using the sample configurations 
  - Run `counts_total{exported_job="otel-api-scrapper"}` in the Prometheus explorer
  - Run `{service_name="otel-api-scrapper"}` in the Loki explorer
- Keep `scraper.dryRun=false` to send real telemetry.
- For quick visibility, add the `debug` exporter in OTEL collector to view payloads.
- If you change Grafana provisioning, restart the `grafana` container.
- Ensure ports `4317`, `4318`, `8889`, `9090`, `3100`, and `3000` are free on your host.

## Cleanup
```
docker-compose -f "LOCAL_TESTING/compose.yaml" down -v
```
