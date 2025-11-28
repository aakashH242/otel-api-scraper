# 🗺️ Roadmap

This roadmap outlines the planned features and improvements for API2OTEL. Items are organized by category and priority.

> **Note**: This roadmap is subject to change based on community feedback and contributions. If you're interested in working on any of these items, please check existing issues or open a new one to discuss your approach.

## 📊 Status Legend

- 🎯 **Planned** - Feature is planned but work hasn't started
- 🚧 **In Progress** - Currently being worked on
- ✅ **Completed** - Feature has been implemented
- 💡 **Idea** - Under consideration, feedback welcome

---

## 🚀 Near Term

### Production Readiness
- 🎯 **Helm Chart** - Publish production-ready Helm chart with example values for various deployment scenarios
  - Support for different storage backends (SQLite vs Valkey)
  - ConfigMaps and Secrets management
  - Resource limits and requests templates
  - Multi-environment configurations (dev/staging/prod)

### Extensibility
- 🎯 **SSL Verification Control** - Allow configured REST API sources to skip SSL verification when scraping
  - Per-source configuration option
  - Security warnings and best practices documentation
  - Support for custom CA certificates

### Observability
- 🎯 **Distributed Tracing** - OpenTelemetry traces for scrape operations
  - End-to-end tracing from scrape to OTLP export
  - Correlation with existing traces in downstream systems
  - Performance bottleneck identification

---

## 🔮 Medium Term

### Other API types Support
- 🎯 **GraphQL API Support** - Extend scraper to support GraphQL endpoints
  - GraphQL query configuration
  - Variable substitution and pagination
  - Fragment and inline fragment support
  - GraphQL-specific error handling

### Admin UI & Management
- 🎯 **Web-based Admin Dashboard** - Full-featured UI for monitoring and control
  - Real-time scrape status and metrics visualization
  - Source configuration management (add/edit/delete without restart)
  - Scrape history and logs viewer with filtering
  - Advanced debugging tools and diagnostics
  - Interactive API explorer
  - User authentication and role-based access control (RBAC)

### Fingerprinting & State Management
- 🎯 **Enhanced Fingerprint Store** - Improved eviction strategies and visibility
  - LRU (Least Recently Used) eviction policy
  - Size-based eviction (max memory/disk usage)
  - Per-source fingerprint statistics and metrics
  - Fingerprint store health monitoring
  - Backup and restore capabilities
  - Distributed fingerprint store with Redis Cluster support

---

## 🌟 Long Term

### Advanced Data Sources
- 💡 **Non-HTTP Sources** - Extend beyond HTTP to support additional data sources
  - **File-based sources**: Local files, S3, Azure Blob, GCS
  - **Message queues**: Kafka, RabbitMQ, AWS SQS, Azure Service Bus
  - **Database queries**: PostgreSQL, MySQL, MongoDB read queries
  - **gRPC endpoints**: Native gRPC support with protobuf definitions

### AI/ML Integration
- 💡 **Intelligent Anomaly Detection** - ML-based anomaly detection for scraped data
  - Detect unusual patterns in API responses
  - Alert on data quality issues
  - Adaptive thresholds based on historical data

### Performance & Scalability
- 💡 **Horizontal Scaling** - Distributed scraping architecture
  - Shard sources across multiple scraper instances
  - Leader election and work distribution
  - Shared state via distributed cache
  - Kubernetes operator for auto-scaling

### Security & Compliance
- 💡 **Enhanced Security** - Additional authentication and security features
  - SAML/OIDC authentication support
  - Data encryption at rest for fingerprint store

---

## 🤝 Contributing to the Roadmap

We welcome community input on our roadmap! Here's how you can contribute:

### Suggest a Feature
1. Check if a similar feature is already on the roadmap or in [Issues](https://github.com/aakashH242/otel-api-scraper/issues)
2. Open a new issue with the **feature request** template
3. Clearly describe the use case and expected behavior
4. Add the `enhancement` label

### Work on a Roadmap Item
1. Comment on the related issue expressing your interest
2. Wait for maintainer feedback on approach
3. Fork the repository and create a feature branch
4. Follow our [Contributing Guidelines](./CONTRIBUTING.md)
5. Submit a PR referencing the issue

### Prioritize Features
- 👍 React with thumbs up on issues you'd like to see prioritized
- 💬 Comment with your specific use case
- 📊 We review community feedback quarterly when updating the roadmap
