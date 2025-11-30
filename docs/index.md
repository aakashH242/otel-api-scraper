# Overview

**API2OTEL** is a config-driven async bridge that turns any HTTP/data API into OpenTelemetry metrics and logs.

For those use-cases when you have data, jobs, or business processes buried behind APIs, reports, or REST API endpoints 
and you want them to show up as first-class signals in your existing OTEL stack – without writing a custom exporter for each system.

## 💡 The Problem

Most teams run critical flows on systems they don't control:

- **SaaS platforms**: Workday, ServiceNow, Jira, GitHub, Salesforce…
- **Internal tools**: Only expose REST/HTTP APIs or "download report" endpoints
- **Batch runners**: Emit JSON or CSV, not OTEL signals

They already have an observability stack built on OpenTelemetry, but bridging those APIs typically ends up as messy one-offs:

- Python scripts + cron that nobody owns
- SaaS-specific "exporters" that can't be reused across products
- JSON dumps and screenshots instead of real metrics

## 🎯 The Solution

Make this reusable and standard:

```
API data → extract records → emit OTLP → your collector
```

**No code changes. No vendor lock-in. Everything flows through your existing OTEL stack.**

## 📋 What It Does

API2OTEL is a config-driven async service that:

- **Polls** any HTTP API or data endpoint
- **Extracts** records from JSON responses  
- **Maps** them to OTEL metrics (gauges, counters, histograms) and logs
- **Emits** everything via OTLP to your collector

```
       [ APIs / data endpoints ]
                ↓ HTTP
       API2OTEL (this service)
                ↓ OTLP (gRPC/HTTP)
      OpenTelemetry Collector
                ↓
      Prometheus / Grafana / Loki / …
```

**Entirely YAML-driven.** Add/update sources by editing config—no code needed.

## ⚙️ Key Features

### 🔧 Config-Driven Scraping

Declare every source in YAML with:

- Frequency (5min, 1h, 1d, …)
- Scrape mode (range with start/end or relative windows; instant snapshots)
- Time formats (global + per-source)
- Query params (time keys, extra args, URL encoding rules)

Add/change sources by editing config—no code changes required.  
Full config explained: [Click here](https://github.com/aakashH242/otel-api-scraper/blob/main/config.yaml.template)

[Download Config Template](./config.yaml.template)

### 🔐 Rich Authentication Strategies

Built-in auth support:

- **Basic Auth**: Username/password via environment variables
- **API Key Headers**: Static or environment-sourced keys (e.g., `X-API-Key`)
- **OAuth**: Static token or runtime fetch with configurable HTTP GET/POST body and response parsing
- **Azure AD**: Client credentials flow for enterprise identity

Tokens are fetched asynchronously and reused per source.

### ⚡ Async Concurrency

- **Asyncio/httpx** end-to-end
- **Global concurrency limit** plus per-source limits
- **Range scrapes** can split into sub-windows and run in parallel within limits
- Stay within rate caps while scraping multiple systems

### 🧹 Filtering & Volume Control

- **Drop rules**: Exclude records matching conditions
- **Keep rules**: Only include records matching conditions
- **Per-scrape caps**: Limit records emitted per execution
- Protects metrics backends and logging costs from noisy sources

### 🔄 Delta Detection via Fingerprinting

- **Fingerprints** stored in SQLite or Valkey (Redis-compatible)
- **Configurable TTL** and fingerprint keys/modes
- **Historical scrapes** and frequent "last N hours" polls without duplicate spam
- **Scheduler/last-success** share the same backend

### 📊 Metrics Mapping

- **Gauges, counters, histograms** from `dataKey` or `fixedValue`
- **Attributes** can emit counters via `asMetric`
- **Per-source logs** with configurable emission
- **Severity mapping** from record fields
- Labels derived from attributes and optional metric labels

### 📝 Log Emission with Severity Mapping

- Records become OTEL logs with **severity derived from a configured field**
- **Attributes align with metrics** for easy pivots in observability tools
- **Per-source opt-out** for logs where they're not needed

## ⚖️ When to Use

### ✅ Perfect For:

- Metrics/logs about business processes only available as API responses
- Adding new sources to an existing OTEL collector
- Complex auth (OAuth, Azure AD) and time windows (historical backfills, relative ranges)
- Data deduplication and volume control

### ❌ Not Needed For:

- Systems already emitting OTLP or Prometheus natively
- Simple uptime checks (use the collector's `httpcheckreceiver`)
- One-off custom exporters for specific vendors

## 🚀 Quick Concepts

### Sources

A **source** is a single API endpoint to scrape. Each source:

- Has a **name** and **frequency** (how often to poll)
- Uses an **auth strategy** (or none)
- Defines **scrape mode** (instant or range-based)
- Specifies how to **extract** records from the response (via `dataKey`)
- Maps records to **metrics and logs**

### Scrape Modes

- **Instant**: Snapshot at a point in time. No time windows involved.
- **Range**: Scrape a time range (e.g., "last 15 minutes"). Supports parallel sub-windows for efficiency.

### Fingerprinting & Deduplication

Each record is **fingerprinted** (MD5 hash). On scrape:

1. Extract records from API
2. Pass through filters (drop/keep rules)
3. Check fingerprint store: **hit** = skip (seen before), **miss** = emit
4. Store new fingerprints with TTL

Prevents duplicate metrics while enabling historical backfills.

### Self-Telemetry

When enabled, API2OTEL emits its **own metrics** about scraping health:

- Scrape duration and success/error rates
- Deduplication hit/miss rates
- Cleanup job performance

Monitor the scraper itself—not just the data it extracts.

## 🏗️ Architecture at a Glance

```
┌──────────────────────────────────────────────────┐
│          Configuration (YAML)                    │
│  - Sources, auth, metrics, filters, attributes   │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│        Scheduler (APScheduler)                   │
│  - Frequency-based job scheduling                │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│      Scraper Engine (AsyncIO)                    │
│  - HTTP fetching, window calculation, concurrency│
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│    Record Pipeline                               │
│  - Filtering, limits, delta detection            │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│      Telemetry (OTEL SDK)                        │
│  - Metrics (gauges, counters, histograms)        │
│  - Logs with severity mapping                    │
│  - Self-telemetry (optional)                     │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│    OTLP Exporters (gRPC or HTTP)                 │
│  - Send to OpenTelemetry Collector               │
└──────────────────────────────────────────────────┘
```

**Ready to turn your APIs into observable signals?** Let's go! 🚀
