"""Pydantic models and loader for scraper configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .utils import resolve_env


class BasicAuthConfig(BaseModel):
    """Configuration for HTTP basic authentication."""

    type: Literal["basic"]
    username: str
    password: str

    model_config = ConfigDict(extra="forbid")


class ApiKeyAuthConfig(BaseModel):
    """Configuration for API key header authentication."""

    type: Literal["apikey"]
    keyName: str
    keyValue: str

    model_config = ConfigDict(extra="forbid")


class OAuthBodyData(BaseModel):
    """Payload format for OAuth token acquisition."""

    type: Literal["raw", "json"]
    data: Any

    model_config = ConfigDict(extra="forbid")


class OAuthAuthConfig(BaseModel):
    """OAuth authentication configuration (static or runtime token)."""

    type: Literal["oauth"]
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    getTokenEndpoint: Optional[str] = None
    tokenKey: Optional[str] = None
    bodyData: Optional[OAuthBodyData] = None
    getTokenMethod: Literal["GET", "POST"] = "POST"
    tokenHeaders: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @property
    def runtime(self) -> bool:
        """Return True when runtime token acquisition is configured."""
        return bool(
            self.username and self.password and self.getTokenEndpoint and self.tokenKey
        )

    @model_validator(mode="after")
    def validate_fields(self) -> "OAuthAuthConfig":
        """Validate presence of token or runtime credentials."""
        if not self.token and not self.runtime:
            raise ValueError(
                "oauth auth requires either token or username/password/getTokenEndpoint/tokenKey"
            )
        return self


class AzureADAuthConfig(BaseModel):
    """Azure AD client credentials configuration."""

    type: Literal["azuread"]
    client_id: str
    client_secret: str
    tokenEndpoint: str
    resource: str

    model_config = ConfigDict(extra="forbid")


AuthConfig = Union[
    BasicAuthConfig, ApiKeyAuthConfig, OAuthAuthConfig, AzureADAuthConfig
]


class ParallelWindow(BaseModel):
    """Sub-window configuration for parallel range scrapes."""

    unit: Literal["minutes", "hours", "days"]
    value: int

    model_config = ConfigDict(extra="forbid")


class RangeKeys(BaseModel):
    """Range parameter configuration for range-based scrapes."""

    startKey: Optional[str] = None
    endKey: Optional[str] = None
    firstScrapeStart: Optional[str] = None
    unit: Optional[Literal["minutes", "hours", "days", "weeks", "months"]] = None
    value: Optional[Union[str, int]] = "from-config"
    takeNegative: bool = False
    dateFormat: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    def is_relative(self) -> bool:
        """Whether this range uses relative window semantics."""
        return self.unit is not None

    def has_explicit_bounds(self) -> bool:
        """Whether start and end keys are explicitly provided."""
        return bool(self.startKey and self.endKey)


class ScrapeConfig(BaseModel):
    """Scrape-time configuration for a single source."""

    type: Literal["range", "instant"]
    httpMethod: Literal["GET", "POST"] = "GET"
    timeFormat: Optional[str] = None
    maxConcurrency: Optional[int] = None
    parallelWindow: Optional[ParallelWindow] = None
    rangeKeys: Optional[RangeKeys] = None
    urlEncodeTimeKeys: bool = False
    extraHeaders: Dict[str, str] = Field(default_factory=dict)
    extraArgs: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_range(self) -> "ScrapeConfig":
        """Validate scrape-specific constraints."""
        if self.type == "range" and not self.rangeKeys:
            raise ValueError("range scrape requires rangeKeys")
        if self.type == "instant" and self.rangeKeys:
            # Allowed but ensure no required keys.
            pass
        if self.parallelWindow and self.type != "range":
            raise ValueError("parallelWindow is only valid for range scrapes")
        if self.maxConcurrency is not None and self.maxConcurrency < 1:
            raise ValueError("maxConcurrency must be >= 1")
        return self


class MatchPredicate(BaseModel):
    """Single predicate used in drop/keep filters."""

    field: str
    matchType: Literal["equals", "not_equals", "in", "regex"]
    value: Any

    model_config = ConfigDict(extra="forbid")


class DropRule(BaseModel):
    """Drop rule containing any-of predicates."""

    any: List[MatchPredicate]

    model_config = ConfigDict(extra="forbid")


class KeepRule(BaseModel):
    """Keep rule requiring all predicates to match."""

    all: List[MatchPredicate]

    model_config = ConfigDict(extra="forbid")


class FilterLimits(BaseModel):
    """Per-scrape limits."""

    maxRecordsPerScrape: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class FiltersConfig(BaseModel):
    """Full filter configuration for a source."""

    drop: List[DropRule] = Field(default_factory=list)
    keep: List[KeepRule] = Field(default_factory=list)
    limits: FilterLimits = Field(default_factory=FilterLimits)

    model_config = ConfigDict(extra="forbid")


class DeltaDetectionConfig(BaseModel):
    """Delta detection configuration for deduplication."""

    enabled: bool = False
    fingerprintMode: Literal["full_record", "keys"] = "full_record"
    fingerprintKeys: Optional[List[str]] = None
    ttlSeconds: Optional[int] = None
    maxEntries: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class MetricLabel(BaseModel):
    """Definition of a metric label extracted from a record."""

    name: str
    dataKey: str

    model_config = ConfigDict(extra="forbid")


class GaugeReading(BaseModel):
    """Gauge metric mapping."""

    name: str
    dataKey: Optional[str] = None
    fixedValue: Optional[float] = None
    unit: str = "1"

    model_config = ConfigDict(extra="forbid")


class CounterReading(BaseModel):
    """Counter metric mapping."""

    name: str
    dataKey: Optional[str] = None
    fixedValue: Optional[float] = None
    unit: str = "1"

    model_config = ConfigDict(extra="forbid")


class HistogramReading(BaseModel):
    """Histogram metric mapping."""

    name: str
    dataKey: Optional[str] = None
    fixedValue: Optional[float] = None
    unit: str = "1"
    buckets: List[float]

    model_config = ConfigDict(extra="forbid")


class AttributeAsMetric(BaseModel):
    """Optional metric emitted from attribute values."""

    metricName: Optional[str] = None
    valueMapping: Dict[str, float] = Field(default_factory=dict)
    unit: str = "1"

    model_config = ConfigDict(extra="forbid")


class AttributeConfig(BaseModel):
    """Telemetry attribute configuration with optional metric mapping."""

    name: str
    dataKey: str
    asMetric: Optional[AttributeAsMetric] = None

    model_config = ConfigDict(extra="forbid")


class LogStatusRule(BaseModel):
    """Severity matching rule for logs."""

    value: Union[str, List[str]]
    matchType: Literal["equals", "in"] = "equals"

    model_config = ConfigDict(extra="forbid")


class LogStatusField(BaseModel):
    """Severity mapping configuration for logs."""

    name: str
    info: Optional[LogStatusRule] = None
    warning: Optional[LogStatusRule] = None
    error: Optional[LogStatusRule] = None

    model_config = ConfigDict(extra="forbid")


class SourceConfig(BaseModel):
    """Full configuration for a single API source."""

    name: str
    frequency: str
    allowOverlapScans: bool = False
    emitLogs: bool = True
    auth: Optional[AuthConfig] = None
    scrape: ScrapeConfig
    endpoint: str
    baseUrl: str
    dataKey: Optional[str] = None
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    deltaDetection: DeltaDetectionConfig = Field(default_factory=DeltaDetectionConfig)
    gaugeReadings: List[GaugeReading] = Field(default_factory=list)
    counterReadings: List[CounterReading] = Field(default_factory=list)
    histogramReadings: List[HistogramReading] = Field(default_factory=list)
    attributes: List[AttributeConfig] = Field(default_factory=list)
    logStatusField: Optional[LogStatusField] = None
    runFirstScrape: bool = False
    model_config = ConfigDict(extra="forbid")


class FingerprintStoreSqlite(BaseModel):
    """SQLite backend settings for fingerprint store."""

    path: str = "./scraper_fingerprints.db"

    model_config = ConfigDict(extra="forbid")


class FingerprintStoreValkey(BaseModel):
    """Valkey/Redis backend settings for fingerprint store."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    ssl: bool = False

    model_config = ConfigDict(extra="forbid")


class FingerprintStoreConfig(BaseModel):
    """Global fingerprint store configuration."""

    backend: Literal["sqlite", "valkey", "redis"] = "sqlite"
    maxEntriesPerSource: int = 50000
    defaultTtlSeconds: int = 86400
    cleanupIntervalSeconds: int = 3600
    lockRetries: int = 5
    lockBackoffSeconds: float = 0.1
    sqlite: FingerprintStoreSqlite = Field(default_factory=FingerprintStoreSqlite)
    valkey: FingerprintStoreValkey = Field(default_factory=FingerprintStoreValkey)
    redis: Optional[FingerprintStoreValkey] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def normalize_backend(self) -> "FingerprintStoreConfig":
        """Normalize deprecated backend names."""
        if self.backend == "redis":
            self.backend = "valkey"
        if self.redis is not None:
            self.valkey = self.redis
        return self


class ScraperSettings(BaseModel):
    """Top-level scraper settings."""

    enableSelfTelemetry: bool = False
    serviceName: str = "otel-api-scrapper"
    allowOverlapScans: bool = False
    logLevel: str = "debug"
    otelCollectorEndpoint: str
    enforceTls: bool = True
    dryRun: bool = False
    terminateGracefully: bool = True
    servicePort: int = 80
    enableAdminApi: bool = False
    adminSecretEnv: Optional[str] = None
    defaultTimeFormat: str = "%Y-%m-%dT%H:%M:%S%z"
    maxGlobalConcurrency: int = 10
    defaultSourceConcurrency: int = 4
    fingerprintStore: FingerprintStoreConfig = Field(
        default_factory=FingerprintStoreConfig
    )
    otelTransport: Literal["grpc", "http"] = "grpc"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_concurrency(self) -> "ScraperSettings":
        """Validate concurrency bounds."""
        if self.maxGlobalConcurrency < 1:
            raise ValueError("maxGlobalConcurrency must be >= 1")
        if self.defaultSourceConcurrency < 1:
            raise ValueError("defaultSourceConcurrency must be >= 1")
        return self


class AppConfig(BaseModel):
    """Root configuration object for the scraper."""

    scraper: ScraperSettings
    sources: List[SourceConfig]

    model_config = ConfigDict(extra="forbid")


def load_config(path: str | Path) -> AppConfig:
    """Load and validate scraper configuration from YAML.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        AppConfig: Parsed configuration object.

    Raises:
        FileNotFoundError: If the file is missing.
        ValueError: If validation fails.
    """
    raw_path = Path(path)
    if not raw_path.exists():
        raise FileNotFoundError(f"Config file not found at {raw_path}")
    with raw_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data = resolve_env(data)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc
