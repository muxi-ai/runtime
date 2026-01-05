# Runtime Telemetry Implementation Plan

**Date:** 2026-01-01
**Updated:** 2026-01-05 (with Server implementation insights)
**Status:** Draft for Review
**Author:** Droid

---

## Overview

Implement privacy-respecting telemetry for the MUXI Runtime to understand usage patterns, feature adoption, and system health. Data helps prioritize development and identify issues.

## Design Principles

1. **Privacy First** - No PII, no content, no identifiable formation data
2. **Opt-In by Default** - Enabled unless explicitly disabled via env var or config
3. **Metrics Answer Questions** - Every metric serves a product decision
4. **Non-Blocking** - Fire-and-forget, never impact runtime performance

> **Note:** Server telemetry has been implemented. Key decisions from that implementation are incorporated below.

---

## Metrics Design

### Product Questions → Metrics

| Question | Metric | Why It Matters |
|----------|--------|----------------|
| Is the runtime being used? | `requests_total`, `uptime_hours` | Basic adoption |
| Is it working reliably? | `success_rate`, `errors_by_type` | Quality signal |
| How complex are formations? | `agents_count`, `tools_count`, `features_enabled` | Complexity trends |
| Which features are adopted? | `feature_usage.*` | Prioritize development |
| What LLM ecosystem? | `llm_providers[]` | Provider partnerships |
| Are we getting repeat users? | `sessions_count`, `uptime_hours` | Stickiness |
| How is response time? | `latency_p50`, `latency_p95` | Performance baseline |
| Is caching working? | `cache_hit_rate` | Caching ROI |

### Proposed Payload

```json
{
  "module": "runtime",
  "schema_version": 1,
  "machine_id": "7f83b165-7ff1-fc53-b92d-c18148a1d65d",
  "ts": "2026-01-02T10:00:00Z",
  "country": "US",
  "payload": {
    "version": "0.20260101.5",
    "uptime_hours": 24,
    
    "formation": {
      "agents_count": 3,
      "tools_count": 12,
      "mcp_servers_count": 2,
      "memory_backend": "sqlite",
      "features_enabled": ["scheduler", "a2a", "clarification", "workflows"]
    },
    
    "requests": {
      "total": 3420,
      "success": 3350,
      "failed": 70,
      "sources": {
        "framework": 0,
        "api": {
          "direct": 10,
          "server": 3410
        },
        "sdk": {
          "python": 2800,
          "typescript": 600
        }
      },
      "failures": {
        "framework": 0,
        "api": {
          "direct": 2,
          "server": 68
        },
        "sdk": {
          "python": 50,
          "typescript": 18
        }
      }
    },
    
    "latency_ms": {
      "p50": 450,
      "p95": 1200,
      "p99": 2500
    },
    
    "errors": {
      "timeout": 30,
      "rate_limit": 25,
      "auth": 5,
      "internal": 10
    },
    
    "llm": {
      "requests_total": 5200,
      "cache_hits": 1200,
      "cache_hit_rate": 0.23,
      "openai": {
        "gpt-4o": {
          "requests": 3000,
          "cache_hits": 800
        },
        "gpt-4o-mini": {
          "requests": 2000,
          "cache_hits": 350
        }
      },
      "anthropic": {
        "claude-sonnet-4-5": {
          "requests": 200,
          "cache_hits": 50
        }
      }
    },
    
    "features": {
      "clarifications_triggered": 45,
      "workflows_executed": 12,
      "sops_matched": 8,
      "a2a_calls": 0,
      "scheduled_tasks_run": 156,
      "knowledge_queries": 230
    }
  }
}
```

---

## What We DO NOT Collect

| Category | Examples | Reason |
|----------|----------|--------|
| Content | Prompts, responses, formation names | Privacy |
| Identifiers | User IDs, session IDs, API keys | Privacy |
| IP addresses | User IPs | Privacy |
| File paths | Formation paths, knowledge paths | Security |
| Timing details | Per-request timestamps | Too granular |

---

## Architecture

### Module Structure

```
src/muxi/runtime/services/telemetry/
├── __init__.py
├── machine_id.py   # Deterministic machine ID (shared with other modules)
└── service.py      # Everything else: config, counters, sending, lifecycle
```

### State Management

```
┌─────────────────────────────────────────┐
│  In-memory counters (always collecting) │
└─────────────────────────────────────────┘
                    │
                    ▼ (every hour or shutdown)
              ┌───────────┐
              │ Try send  │──────────────────┐
              └───────────┘                  │
                    │                        │
         ┌──────────┴──────────┐             │
         ▼                     ▼             │
    [Success]              [Failure]         │
    Reset counters         Keep counters     │
    Delete backup file     Save to backup    │
                           file (for restart)│
                                             │
                    ┌────────────────────────┘
                    ▼
              [On Startup]
              Load backup file if exists
              Add to in-memory counters
              Delete backup file
```

---

## Implementation Details

### 1. Machine ID (`machine_id.py`)

```python
import hashlib
import platform
import subprocess
from pathlib import Path

import yaml

CONFIG_PATH = Path.home() / ".muxi" / "config.yaml"


def _get_os_machine_id() -> str:
    """Get platform-specific machine identifier."""
    system = platform.system()
    
    if system == "Darwin":
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if "IOPlatformUUID" in line:
                return line.split('"')[3]
    
    elif system == "Linux":
        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                return Path(path).read_text().strip()
            except FileNotFoundError:
                continue
    
    elif system == "Windows":
        result = subprocess.run(
            ["wmic", "csproduct", "get", "uuid"],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            return lines[1].strip()
    
    return ""


def get_machine_id() -> str:
    """Get or create machine ID. Cached in ~/.muxi/config.yaml."""
    # Check cache
    if CONFIG_PATH.exists():
        config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        if "machine_id" in config:
            return config["machine_id"]
    
    # Generate new
    os_id = _get_os_machine_id()
    if not os_id:
        os_id = str(uuid.uuid4())  # Fallback for containers
    
    hash_hex = hashlib.sha256(f"{os_id}muxi".encode()).hexdigest()
    machine_id = f"{hash_hex[0:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
    
    # Cache it
    config = yaml.safe_load(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    config["machine_id"] = machine_id
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.dump(config))
    
    return machine_id
```

### 2. Telemetry Service (`service.py`)

Single file with everything:

```python
import asyncio
import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import yaml

from .machine_id import get_machine_id

# Constants
CONFIG_PATH = Path.home() / ".muxi" / "config.yaml"
BACKUP_PATH = Path.home() / ".muxi" / "runtime" / "telemetry.json"
ENDPOINT = os.environ.get("TELEMETRY_URL", "https://capture.muxi.org/v1/telemetry")
FLUSH_INTERVAL = timedelta(hours=1)
SEND_TIMEOUT = 2.0
MAX_LATENCIES = 1000  # Cap for percentile calculation


def is_telemetry_enabled() -> bool:
    """Check opt-out: env var first, then config file."""
    if os.environ.get("MUXI_TELEMETRY") == "0":
        return False
    if CONFIG_PATH.exists():
        config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        if config.get("telemetry") is False:
            return False
    return True


def get_country() -> str:
    """Get country code. Fetched once from ipapi.co, then cached."""
    if CONFIG_PATH.exists():
        config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        if "country" in config:
            return config["country"]
    
    # Fetch once
    try:
        resp = httpx.get("https://ipapi.co/json/", timeout=2)
        country = resp.json().get("country_code", "XX")
    except Exception:
        country = "XX"
    
    # Cache it
    config = yaml.safe_load(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    config["country"] = country
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.dump(config))
    
    return country


class TelemetryService:
    """Collects and sends runtime telemetry."""
    
    def __init__(self, version: str):
        self._lock = threading.Lock()
        self._version = version
        self._start_time = datetime.now()
        self._last_flush = datetime.now()
        
        # Counters - match payload structure exactly
        self._requests_total = 0
        self._requests_success = 0
        self._requests_failed = 0
        self._sources = {"framework": 0, "api": {"direct": 0, "server": 0}, "sdk": {}}
        self._failures = {"framework": 0, "api": {"direct": 0, "server": 0}, "sdk": {}}
        self._latencies: list[float] = []
        self._errors: dict[str, int] = defaultdict(int)
        self._llm: dict = {"requests_total": 0, "cache_hits": 0}  # provider/model added dynamically
        self._features: dict[str, int] = defaultdict(int)
        
        # Formation info (set once on startup)
        self._formation: dict = {}
        
        # Load any pending data from previous run
        self._load_backup()
    
    def _load_backup(self):
        """Load counters from backup file if exists."""
        if BACKUP_PATH.exists():
            try:
                data = json.loads(BACKUP_PATH.read_text())
                # Merge with current counters
                self._requests_total += data.get("requests_total", 0)
                self._requests_success += data.get("requests_success", 0)
                self._requests_failed += data.get("requests_failed", 0)
                # ... merge other fields as needed
                BACKUP_PATH.unlink()  # Delete after loading
            except Exception:
                pass
    
    def _save_backup(self):
        """Save current counters to backup file."""
        BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        BACKUP_PATH.write_text(json.dumps(self._build_payload()["payload"]))
    
    def set_formation_info(self, agents: int, tools: int, mcp_servers: int,
                          memory_backend: str, features: list[str]):
        """Set formation metadata (called once on startup)."""
        self._formation = {
            "agents_count": agents,
            "tools_count": tools,
            "mcp_servers_count": mcp_servers,
            "memory_backend": memory_backend,
            "features_enabled": features
        }
    
    def record_request(self, success: bool, latency_ms: float, 
                       route: str, sdk: Optional[str] = None):
        """
        Record a request.
        
        Args:
            success: Whether request succeeded
            latency_ms: Response time in milliseconds
            route: "framework" | "direct" | "server"
            sdk: SDK name if present (e.g., "python", "typescript")
        """
        with self._lock:
            self._requests_total += 1
            if success:
                self._requests_success += 1
            else:
                self._requests_failed += 1
            
            # Track by route
            if route == "framework":
                self._sources["framework"] += 1
                if not success:
                    self._failures["framework"] += 1
            elif route == "direct":
                self._sources["api"]["direct"] += 1
                if not success:
                    self._failures["api"]["direct"] += 1
            elif route == "server":
                self._sources["api"]["server"] += 1
                if not success:
                    self._failures["api"]["server"] += 1
            
            # Track by SDK
            if sdk:
                self._sources["sdk"][sdk] = self._sources["sdk"].get(sdk, 0) + 1
                if not success:
                    self._failures["sdk"][sdk] = self._failures["sdk"].get(sdk, 0) + 1
            
            # Track latency (capped)
            if len(self._latencies) < MAX_LATENCIES:
                self._latencies.append(latency_ms)
    
    def record_error(self, error_type: str):
        """Record error by type: timeout, rate_limit, auth, network, internal."""
        with self._lock:
            self._errors[error_type] += 1
    
    def record_llm_request(self, provider: str, model: str, cache_hit: bool):
        """Record LLM request with provider and model."""
        with self._lock:
            self._llm["requests_total"] += 1
            if cache_hit:
                self._llm["cache_hits"] += 1
            
            # Track per provider/model
            if provider not in self._llm:
                self._llm[provider] = {}
            if model not in self._llm[provider]:
                self._llm[provider][model] = {"requests": 0, "cache_hits": 0}
            
            self._llm[provider][model]["requests"] += 1
            if cache_hit:
                self._llm[provider][model]["cache_hits"] += 1
    
    def record_feature(self, feature: str):
        """Record feature usage."""
        with self._lock:
            self._features[feature] += 1
    
    def _calculate_percentiles(self) -> dict:
        """Calculate latency percentiles."""
        if not self._latencies:
            return {"p50": 0, "p95": 0, "p99": 0}
        
        sorted_lat = sorted(self._latencies)
        n = len(sorted_lat)
        return {
            "p50": sorted_lat[int(n * 0.50)],
            "p95": sorted_lat[int(n * 0.95)] if n >= 20 else sorted_lat[-1],
            "p99": sorted_lat[int(n * 0.99)] if n >= 100 else sorted_lat[-1]
        }
    
    def _build_payload(self) -> dict:
        """Build the full telemetry payload."""
        uptime = (datetime.now() - self._start_time).total_seconds() / 3600
        
        # Calculate cache hit rate
        llm_total = self._llm.get("requests_total", 0)
        llm_hits = self._llm.get("cache_hits", 0)
        cache_hit_rate = round(llm_hits / llm_total, 2) if llm_total > 0 else 0
        
        return {
            "module": "runtime",
            "schema_version": 1,
            "machine_id": get_machine_id(),
            "ts": datetime.utcnow().isoformat() + "Z",
            "country": get_country(),
            "payload": {
                "version": self._version,
                "uptime_hours": round(uptime, 1),
                "formation": self._formation,
                "requests": {
                    "total": self._requests_total,
                    "success": self._requests_success,
                    "failed": self._requests_failed,
                    "sources": self._sources,
                    "failures": self._failures
                },
                "latency_ms": self._calculate_percentiles(),
                "errors": dict(self._errors),
                "llm": {**self._llm, "cache_hit_rate": cache_hit_rate},
                "features": dict(self._features)
            }
        }
    
    def _reset_counters(self):
        """Reset all counters after successful send."""
        self._requests_total = 0
        self._requests_success = 0
        self._requests_failed = 0
        self._sources = {"framework": 0, "api": {"direct": 0, "server": 0}, "sdk": {}}
        self._failures = {"framework": 0, "api": {"direct": 0, "server": 0}, "sdk": {}}
        self._latencies = []
        self._errors = defaultdict(int)
        self._llm = {"requests_total": 0, "cache_hits": 0}
        self._features = defaultdict(int)
        # Note: _formation is NOT reset (static info)
    
    async def _send(self, payload: dict) -> bool:
        """Send payload with single retry."""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=SEND_TIMEOUT) as client:
                    resp = await client.post(ENDPOINT, json=payload)
                    if 200 <= resp.status_code < 300:
                        return True
            except Exception:
                pass
            
            if attempt == 0:
                await asyncio.sleep(5)  # Wait 5s before retry
        
        return False
    
    async def flush(self):
        """Flush telemetry: send if enabled, handle success/failure."""
        with self._lock:
            if self._requests_total == 0:
                return  # Nothing to send
            
            payload = self._build_payload()
        
        if not is_telemetry_enabled():
            return  # Silently skip if disabled
        
        success = await self._send(payload)
        
        with self._lock:
            if success:
                self._reset_counters()
                if BACKUP_PATH.exists():
                    BACKUP_PATH.unlink()
            else:
                self._save_backup()
        
        self._last_flush = datetime.now()
    
    async def start(self):
        """Start the hourly flush loop."""
        asyncio.create_task(self._flush_loop())
    
    async def _flush_loop(self):
        """Background task: flush every hour."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            if datetime.now() - self._last_flush >= FLUSH_INTERVAL:
                await self.flush()
    
    async def shutdown(self):
        """Flush on shutdown."""
        await self.flush()
```

---

## Integration Points

### 1. Formation Startup

```python
# In formation.py
from muxi.runtime.services.telemetry import TelemetryService

class Formation:
    async def initialize(self):
        # ... other init ...
        
        self.telemetry = TelemetryService(version=__version__)
        self.telemetry.set_formation_info(
            agents=len(self.agents),
            tools=self._count_tools(),
            mcp_servers=len(self.mcp_servers),
            memory_backend=self.memory_config.get("backend", "none"),
            features=self._enabled_features()
        )
        await self.telemetry.start()
    
    async def shutdown(self):
        await self.telemetry.shutdown()
```

### 2. Request Tracking

**Route detection** (mutually exclusive):
| Route | Condition |
|-------|-----------|
| `framework` | Direct Python API call |
| `direct` | HTTP without `X-Muxi-Server` header |
| `server` | HTTP with `X-Muxi-Server` header |

**SDK detection** (from `X-Muxi-SDK` header, format `sdk/version`):

```python
# HTTP middleware
@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    start = time.time()
    route = "server" if request.headers.get("X-Muxi-Server") else "direct"
    sdk_header = request.headers.get("X-Muxi-SDK", "")
    sdk = sdk_header.split("/")[0] if sdk_header else None
    
    try:
        response = await call_next(request)
        telemetry.record_request(
            success=response.status_code < 400,
            latency_ms=(time.time() - start) * 1000,
            route=route,
            sdk=sdk
        )
        return response
    except Exception as e:
        telemetry.record_request(False, 0, route, sdk)
        telemetry.record_error(classify_error(e))
        raise

# Framework mode (in formation.py)
async def chat(self, message: str, ...):
    start = time.time()
    try:
        result = await self._process_chat(message, ...)
        self.telemetry.record_request(True, (time.time() - start) * 1000, "framework")
        return result
    except Exception as e:
        self.telemetry.record_request(False, 0, "framework")
        raise
```

### 3. LLM Tracking

```python
# In services/llm/llm.py
telemetry.record_llm_request(provider="openai", model="gpt-4o", cache_hit=False)
```

### 4. Feature Tracking

```python
telemetry.record_feature("clarification")
telemetry.record_feature("workflow")
telemetry.record_feature("scheduled_task")
```

### 5. Error Classification

```python
def classify_error(error: Exception) -> str:
    s = str(error).lower()
    if "timeout" in s: return "timeout"
    if "rate" in s and "limit" in s: return "rate_limit"
    if "401" in s or "403" in s or "auth" in s: return "auth"
    if "connection" in s or "network" in s: return "network"
    return "internal"
```

---

## Testing

```bash
# Override endpoint for testing
export TELEMETRY_URL=http://localhost:8080/v1/telemetry
export MUXI_TELEMETRY=0  # Disable sending (still collects)
```

Key test cases:
- Machine ID is deterministic (same machine = same ID)
- Counters are thread-safe under concurrent access
- Opt-out prevents sending but continues collection
- Backup file created on send failure, loaded on restart

---

## Implementation Checklist

**Phase 1: Core**
- [ ] `machine_id.py` - deterministic UUID generation
- [ ] `service.py` - config, counters, sending, lifecycle

**Phase 2: Integration**
- [ ] Formation startup/shutdown hooks
- [ ] Request middleware (route + SDK tracking)
- [ ] LLM service tracking (provider + model)
- [ ] Feature tracking hooks

**Phase 3: Validation**
- [ ] Test with local receiver
- [ ] Verify payload format matches spec
- [ ] Test opt-out behavior
- [ ] Test backup/restore on failure

---

## Privacy Checklist

Before shipping, verify NO payload contains:
- [ ] Formation names, paths, or content
- [ ] User prompts or agent responses
- [ ] API keys, tokens, or secrets
- [ ] IP addresses (country code only)
- [ ] Raw hardware identifiers (hashed only)
