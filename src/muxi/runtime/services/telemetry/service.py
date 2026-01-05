"""Telemetry service for MUXI Runtime.

Collects anonymous usage metrics and sends them hourly to help improve the product.
All data is aggregated and contains no PII or user content.
"""

import asyncio
import json
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .machine_id import get_machine_id

logger = logging.getLogger(__name__)

# Global telemetry instance for access from anywhere in the runtime
_global_telemetry: "TelemetryService | None" = None


def get_telemetry() -> "TelemetryService | None":
    """Get the global telemetry service instance."""
    return _global_telemetry


def set_telemetry(service: "TelemetryService | None") -> None:
    """Set the global telemetry service instance."""
    global _global_telemetry
    _global_telemetry = service


TELEMETRY_ENDPOINT = "https://capture.muxi.org/v1/telemetry"
FLUSH_INTERVAL_SECONDS = 3600  # 1 hour
BACKUP_PATH = Path.home() / ".muxi" / "runtime" / "telemetry_backup.json"
COUNTRY_CACHE_PATH = Path.home() / ".muxi" / "runtime" / "country_cache.json"


@dataclass
class TelemetryConfig:
    """Telemetry configuration."""

    enabled: bool = True
    endpoint: str = TELEMETRY_ENDPOINT


@dataclass
class Counters:
    """Thread-safe counters for telemetry metrics."""

    lock: threading.Lock = field(default_factory=threading.Lock)

    # Request tracking
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0

    # Request sources (route dimension)
    sources_framework: int = 0
    sources_direct: int = 0
    sources_server: int = 0

    # Failures by source
    failures_framework: int = 0
    failures_direct: int = 0
    failures_server: int = 0

    # SDK tracking (independent dimension)
    sdk_requests: dict = field(default_factory=lambda: defaultdict(int))

    # Latencies for percentile calculation
    latencies: list = field(default_factory=list)
    max_latencies: int = 1000  # Keep last N for percentile calculation

    # Error tracking
    errors: dict = field(default_factory=lambda: defaultdict(int))

    # LLM tracking (provider -> model -> {requests, cache_hits})
    llm_stats: dict = field(
        default_factory=lambda: defaultdict(
            lambda: defaultdict(lambda: {"requests": 0, "cache_hits": 0})
        )
    )

    # Feature tracking
    features: dict = field(default_factory=lambda: defaultdict(int))

    def increment_request(
        self,
        success: bool,
        latency_ms: float,
        route: str,
        sdk: str | None = None,
    ) -> None:
        """Record a request with all its dimensions."""
        with self.lock:
            self.requests_total += 1
            if success:
                self.requests_success += 1
            else:
                self.requests_failed += 1
                # Track failures by route
                if route == "framework":
                    self.failures_framework += 1
                elif route == "direct":
                    self.failures_direct += 1
                elif route == "server":
                    self.failures_server += 1

            # Track by route
            if route == "framework":
                self.sources_framework += 1
            elif route == "direct":
                self.sources_direct += 1
            elif route == "server":
                self.sources_server += 1

            # Track by SDK if provided
            if sdk:
                self.sdk_requests[sdk] += 1

            # Track latency
            self.latencies.append(latency_ms)
            if len(self.latencies) > self.max_latencies:
                self.latencies = self.latencies[-self.max_latencies :]

    def increment_llm(self, provider: str, model: str, cache_hit: bool) -> None:
        """Record an LLM request."""
        with self.lock:
            self.llm_stats[provider][model]["requests"] += 1
            if cache_hit:
                self.llm_stats[provider][model]["cache_hits"] += 1

    def increment_error(self, error_type: str) -> None:
        """Record an error by type."""
        with self.lock:
            self.errors[error_type] += 1

    def increment_feature(self, feature_name: str) -> None:
        """Record a feature usage."""
        with self.lock:
            self.features[feature_name] += 1

    def _calculate_percentiles(self) -> dict[str, float]:
        """Calculate latency percentiles. Must be called with lock held."""
        if not self.latencies:
            return {"p50": 0, "p95": 0, "p99": 0}
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        return {
            "p50": sorted_latencies[int(n * 0.50)],
            "p95": sorted_latencies[int(n * 0.95)] if n >= 20 else sorted_latencies[-1],
            "p99": sorted_latencies[int(n * 0.99)] if n >= 100 else sorted_latencies[-1],
        }

    def get_percentiles(self) -> dict[str, float]:
        """Calculate latency percentiles (thread-safe)."""
        with self.lock:
            return self._calculate_percentiles()

    def snapshot_and_reset(self) -> dict[str, Any]:
        """Take a snapshot of all counters and reset them."""
        with self.lock:
            # Calculate LLM totals
            llm_requests_total = 0
            llm_cache_hits_total = 0
            llm_by_provider = {}
            for provider, models in self.llm_stats.items():
                llm_by_provider[provider] = {}
                for model, stats in models.items():
                    llm_by_provider[provider][model] = dict(stats)
                    llm_requests_total += stats["requests"]
                    llm_cache_hits_total += stats["cache_hits"]

            snapshot = {
                "requests": {
                    "total": self.requests_total,
                    "success": self.requests_success,
                    "failed": self.requests_failed,
                    "sources": {
                        "framework": self.sources_framework,
                        "api": {
                            "direct": self.sources_direct,
                            "server": self.sources_server,
                        },
                        "sdk": dict(self.sdk_requests),
                    },
                    "failures": {
                        "framework": self.failures_framework,
                        "api": {
                            "direct": self.failures_direct,
                            "server": self.failures_server,
                        },
                    },
                },
                "latency_ms": self._calculate_percentiles(),
                "errors": dict(self.errors),
                "llm": {
                    "requests_total": llm_requests_total,
                    "cache_hits": llm_cache_hits_total,
                    "cache_hit_rate": (
                        (llm_cache_hits_total / llm_requests_total) if llm_requests_total > 0 else 0
                    ),
                    **llm_by_provider,
                },
                "features": dict(self.features),
            }

            # Reset counters
            self.requests_total = 0
            self.requests_success = 0
            self.requests_failed = 0
            self.sources_framework = 0
            self.sources_direct = 0
            self.sources_server = 0
            self.failures_framework = 0
            self.failures_direct = 0
            self.failures_server = 0
            self.sdk_requests = defaultdict(int)
            self.latencies = []
            self.errors = defaultdict(int)
            self.llm_stats = defaultdict(
                lambda: defaultdict(lambda: {"requests": 0, "cache_hits": 0})
            )
            self.features = defaultdict(int)

            return snapshot


class TelemetryService:
    """Main telemetry service that manages collection and sending."""

    def __init__(self, version: str = "unknown"):
        self._version = version
        self._config = self._load_config()
        self._counters = Counters()
        self._formation_info: dict[str, Any] = {}
        self._start_time = time.time()
        self._flush_task: asyncio.Task | None = None
        self._country: str | None = None
        self._running = False

    def _load_config(self) -> TelemetryConfig:
        """Load configuration from environment variables."""
        enabled_str = os.environ.get("MUXI_TELEMETRY", "1")
        enabled = enabled_str.lower() not in ("0", "false", "no", "off")
        endpoint = os.environ.get("TELEMETRY_URL", TELEMETRY_ENDPOINT)
        return TelemetryConfig(enabled=enabled, endpoint=endpoint)

    @property
    def enabled(self) -> bool:
        """Whether telemetry sending is enabled."""
        return self._config.enabled

    def set_formation_info(
        self,
        agents: int = 0,
        tools: int = 0,
        mcp_servers: int = 0,
        memory_backend: str = "none",
        features: list[str] | None = None,
    ) -> None:
        """Set formation configuration info (called at startup)."""
        self._formation_info = {
            "agents_count": agents,
            "tools_count": tools,
            "mcp_servers": mcp_servers,
            "memory_backend": memory_backend,
            "features_enabled": features or [],
        }

    async def start(self) -> None:
        """Start the telemetry service (background flush loop)."""
        if self._running:
            return
        self._running = True
        self._start_time = time.time()

        # Load backup if exists
        self._load_backup()

        # Fetch country code (async, cached forever)
        asyncio.create_task(self._fetch_country())

        # Start flush loop
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.debug("Telemetry service started")

    async def shutdown(self) -> None:
        """Shutdown the telemetry service (final flush)."""
        if not self._running:
            return
        self._running = False

        # Cancel flush loop
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush()
        logger.debug("Telemetry service shutdown")

    async def _flush_loop(self) -> None:
        """Background loop that flushes telemetry every hour."""
        while self._running:
            try:
                await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Telemetry flush error: {e}")

    async def _flush(self) -> None:
        """Flush accumulated telemetry to the server."""
        snapshot = self._counters.snapshot_and_reset()

        # Skip if no activity
        if snapshot["requests"]["total"] == 0:
            return

        payload = self._build_payload(snapshot)

        if not self._config.enabled:
            logger.debug("Telemetry disabled, skipping send")
            return

        success = await self._send(payload)
        if not success:
            # Save to backup file for retry on next flush
            self._save_backup(payload)

    def _build_payload(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Build the full telemetry payload."""
        uptime_hours = (time.time() - self._start_time) / 3600

        return {
            "module": "runtime",
            "schema_version": 1,
            "machine_id": get_machine_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "country": self._country,
            "payload": {
                "version": self._version,
                "uptime_hours": round(uptime_hours, 2),
                "formation": self._formation_info,
                **snapshot,
            },
        }

    async def _send(self, payload: dict[str, Any]) -> bool:
        """Send telemetry payload to the server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._config.endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code in (200, 201, 202, 204):
                    logger.debug("Telemetry sent successfully")
                    # Clear backup on success
                    self._clear_backup()
                    return True
                else:
                    logger.debug(f"Telemetry send failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.debug(f"Telemetry send error: {e}")
            return False

    def _save_backup(self, payload: dict[str, Any]) -> None:
        """Save payload to backup file for retry."""
        try:
            BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(BACKUP_PATH, "w") as f:
                json.dump(payload, f)
        except Exception as e:
            logger.debug(f"Failed to save telemetry backup: {e}")

    def _load_backup(self) -> None:
        """Load and merge backup payload if exists."""
        if not BACKUP_PATH.exists():
            return
        try:
            with open(BACKUP_PATH) as f:
                _ = json.load(f)  # Validate backup exists and is valid JSON
            # TODO: Merge backup counters into current counters
            # For now, we just validate the backup exists
            logger.debug("Loaded telemetry backup")
        except Exception as e:
            logger.debug(f"Failed to load telemetry backup: {e}")

    def _clear_backup(self) -> None:
        """Clear backup file after successful send."""
        try:
            if BACKUP_PATH.exists():
                BACKUP_PATH.unlink()
        except Exception as e:
            logger.debug(f"Failed to clear telemetry backup: {e}")

    async def _fetch_country(self) -> None:
        """Fetch country code from IP API (cached forever)."""
        # Check cache first
        if COUNTRY_CACHE_PATH.exists():
            try:
                with open(COUNTRY_CACHE_PATH) as f:
                    data = json.load(f)
                    self._country = data.get("country")
                    return
            except Exception:
                pass

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://ipapi.co/country/")
                if response.status_code == 200:
                    self._country = response.text.strip()[:2]  # ISO 2-letter code
                    # Cache forever
                    try:
                        COUNTRY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                        with open(COUNTRY_CACHE_PATH, "w") as f:
                            json.dump({"country": self._country}, f)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Failed to fetch country: {e}")
            self._country = None

    # Public recording methods

    def record_request(
        self,
        success: bool,
        latency_ms: float,
        route: str,
        sdk: str | None = None,
    ) -> None:
        """Record a request with its outcome and dimensions.

        Args:
            success: Whether the request succeeded
            latency_ms: Request latency in milliseconds
            route: One of "framework", "direct", "server"
            sdk: Optional SDK identifier (e.g., "python", "typescript")
        """
        self._counters.increment_request(success, latency_ms, route, sdk)

    def record_llm_request(
        self,
        provider: str,
        model: str,
        cache_hit: bool = False,
    ) -> None:
        """Record an LLM request.

        Args:
            provider: Provider name (e.g., "openai", "anthropic")
            model: Model name (e.g., "gpt-4o", "claude-3-sonnet")
            cache_hit: Whether this was a cache hit
        """
        self._counters.increment_llm(provider, model, cache_hit)

    def record_error(self, error_type: str) -> None:
        """Record an error by type.

        Args:
            error_type: Error category (e.g., "timeout", "rate_limit", "auth", "network", "internal")
        """
        self._counters.increment_error(error_type)

    def record_feature(self, feature_name: str) -> None:
        """Record a feature usage.

        Args:
            feature_name: Feature identifier (e.g., "clarification", "workflow", "scheduled_task")
        """
        self._counters.increment_feature(feature_name)
