---
name: 🐛 Bug Report
description: Report a bug or issue with API2OTEL
title: "[BUG] "
labels: ["bug", "triage"]
assignees: []
---

## 🐛 Describe the Bug

A clear and concise description of what the bug is.

## 🔍 Steps to Reproduce

Steps to reproduce the behavior:

1. ...
2. ...
3. ...

## ❌ Expected Behavior

What you expected to happen.

## ✅ Actual Behavior

What actually happened instead.

## 📊 Environment

Please provide details about your environment:

- **OS**: [e.g., Ubuntu 22.04, macOS 13, Windows 11]
- **Python Version**: [e.g., 3.10, 3.11, 3.12]
- **API2OTEL Version**: [e.g., 0.1.0, main branch]
- **Installation Method**: [e.g., uv, pip, Docker]
- **OTEL Collector Version**: [e.g., 0.68.0]
- **OTEL Transport**: [gRPC or HTTP]

## 📝 Relevant Configuration

Please share the relevant parts of your `config.yaml` (redact any sensitive information):

```yaml
scraper:
  # Configuration here
sources:
  - name: example
    # Source configuration here
```

## 📋 Logs and Error Messages

Include any error messages or relevant logs:

```
Paste logs here
```

## 🎯 Affected Components

- [ ] Authentication (`http_client.py`, auth strategies)
- [ ] HTTP Client (`http_client.py`)
- [ ] Configuration (`config.py`)
- [ ] Scraping Engine (`scraper_engine.py`)
- [ ] Pipeline (`pipeline.py`)
- [ ] Telemetry (`telemetry.py`)
- [ ] Fingerprinting (`fingerprints.py`)
- [ ] Scheduler (`scheduler.py`)
- [ ] Admin API (`admin_api.py`)
- [ ] Other: ___________

## 📸 Screenshots or Additional Context

Add any screenshots, Docker logs, or other context that might help:

## 🔗 Related Issues

Is this related to any other issues or discussions?

- Related to: # (issue number)
- Duplicate of: # (if applicable)

## ✅ Checklist

- [ ] I've searched for existing issues and discussions
- [ ] I've provided a clear description of the bug
- [ ] I've included steps to reproduce
- [ ] I've included relevant configuration (with sensitive data redacted)
- [ ] I've included error messages and logs
- [ ] I'm using the latest version or main branch
