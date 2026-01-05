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
├── machine_id.py      # Deterministic machine ID generation
├── config.py          # ~/.muxi/config.yaml management
├── collector.py       # Metrics collection and aggregation
├── sender.py          # HTTP send with retry logic
└── service.py         # Main service, hourly flush, lifecycle
```

### Data Flow

```
┌────────────────────────────────────────────────────────────┐
│                        Runtime                             │
│                                                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Overlord │    │  Agents  │    │ Services │              │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│       │               │               │                    │
│       └───────────────┼───────────────┘                    │
│                       ▼                                    │
│              ┌────────────────┐                            │
│              │   Collector    │  ← Increment counters      │
│              └────────┬───────┘                            │
│                       │                                    │
│                       ▼                                    │
│    ┌──────────────────────────────────────┐                │
│    │  ~/.muxi/runtime/telemetry.json      │  ← Persist     │
│    └──────────────────────────────────────┘                │
│                       │                                    │
│                       ▼ (hourly)                           │
│              ┌────────────────┐                            │
│              │    Sender      │  ← If telemetry enabled    │
│              └────────┬───────┘                            │
│                       │                                    │
└───────────────────────┼────────────────────────────────────┘
                        │
                        ▼
           https://capture.muxi.org/v1/telemetry
```

---

## Implementation Details

### 1. Machine ID (`machine_id.py`)

```python
def generate_machine_id() -> str:
    """
    Deterministic machine ID from OS hardware UUID.
    Algorithm: format_as_uuid(sha256(os_machine_id + "muxi"))
    """
    os_id = _get_os_machine_id()  # Platform-specific
    hash_hex = hashlib.sha256(f"{os_id}muxi".encode()).hexdigest()
    return f"{hash_hex[0:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
```

Platform sources:
- **macOS**: `ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID`
- **Linux**: `/etc/machine-id` or `/var/lib/dbus/machine-id`
- **Windows**: `wmic csproduct get uuid`

### 2. Config Management (`config.py`)

> **Global Config:** Shared by CLI, Server, and Runtime at `~/.muxi/config.yaml`

Location: `~/.muxi/config.yaml`

```yaml
machine_id: 7f83b165-7ff1-fc53-b92d-c18148a1d65d
country: US
telemetry: true  # Set to false to opt-out (applies to all MUXI modules)
```

Functions:
- `get_or_create_machine_id()` - Generate once, cache in config file
- `get_or_fetch_country()` - Fetch from ipapi.co once, cache in config file
- `is_telemetry_enabled()` - Check env `MUXI_TELEMETRY=0` first, then config file

```python
def is_telemetry_enabled() -> bool:
    """Check if telemetry is enabled. Opt-in by default."""
    # Environment variable takes precedence
    if os.environ.get("MUXI_TELEMETRY") == "0":
        return False
    
    # Check global config file
    config = load_global_config()  # ~/.muxi/config.yaml
    return config.get("telemetry", True)  # Default: enabled
```

### 3. Collector (`collector.py`)

Thread-safe counter aggregation:

```python
class TelemetryCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = defaultdict(int)
        self._latencies = []  # For percentile calculation
        self._features_enabled = set()
        self._llm_providers = set()
        self._errors_by_type = defaultdict(int)
        self._sdk_requests = defaultdict(int)
    
    def record_request(self, success: bool, latency_ms: float, sdk: str = "direct"):
        with self._lock:
            self._counters["requests_total"] += 1
            self._counters["requests_success" if success else "requests_failed"] += 1
            self._latencies.append(latency_ms)
            self._sdk_requests[sdk] += 1
    
    def record_error(self, error_type: str):
        with self._lock:
            self._errors_by_type[error_type] += 1
    
    def record_llm_request(self, provider: str, cache_hit: bool):
        with self._lock:
            self._llm_providers.add(provider)
            self._counters["llm_requests_total"] += 1
            if cache_hit:
                self._counters["llm_cache_hits"] += 1
    
    def record_feature_use(self, feature: str):
        with self._lock:
            self._counters[f"feature_{feature}"] += 1
    
    def set_formation_info(self, agents: int, tools: int, mcp_servers: int, 
                          memory_backend: str, features: list[str]):
        with self._lock:
            self._counters["agents_count"] = agents
            self._counters["tools_count"] = tools
            self._counters["mcp_servers_count"] = mcp_servers
            self._memory_backend = memory_backend
            self._features_enabled = set(features)
    
    def snapshot_and_reset(self) -> dict:
        """Get current metrics and reset counters."""
        with self._lock:
            snapshot = self._build_payload()
            self._reset()
            return snapshot
```

### 4. Sender (`sender.py`)

> **Server Decision:** On failure, wait 5 seconds and retry once. If still fails, wait until next hourly flush. No rate limiting.

```python
ENDPOINT = os.environ.get("TELEMETRY_URL", "https://capture.muxi.org/v1/telemetry")
TIMEOUT = 2.0
RETRY_BACKOFF = 5.0  # seconds

async def send_telemetry(payload: dict) -> bool:
    """Send with single retry after 5 second backoff."""
    # First attempt
    if await _do_send(payload):
        return True
    
    # Wait 5 seconds and retry once
    await asyncio.sleep(RETRY_BACKOFF)
    
    # Second attempt - if this fails, we wait until next hour
    return await _do_send(payload)

async def _do_send(payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(ENDPOINT, json=payload)
            return 200 <= resp.status_code < 300
    except Exception:
        return False
```

### 5. Service (`service.py`)

```python
class TelemetryService:
    FLUSH_INTERVAL = timedelta(hours=1)
    STATE_PATH = Path.home() / ".muxi" / "runtime" / "telemetry.json"
    
    def __init__(self):
        self.collector = TelemetryCollector()
        self.start_time = datetime.now()
        self._last_flush = datetime.now()
        self._load_state()
    
    async def start(self):
        """Start background flush task."""
        asyncio.create_task(self._flush_loop())
    
    async def _flush_loop(self):
        while True:
            await asyncio.sleep(60)  # Check every minute
            if datetime.now() - self._last_flush >= self.FLUSH_INTERVAL:
                await self._flush()
    
    async def _flush(self):
        payload = self._build_full_payload()
        self._save_state(payload)  # Always save locally
        
        if is_telemetry_enabled():
            await send_telemetry(payload)
        
        self.collector.snapshot_and_reset()
        self._last_flush = datetime.now()
    
    async def shutdown(self):
        """Final flush on shutdown."""
        await self._flush()
```

---

## Integration Points

### 1. Formation Startup

```python
# In formation.py
async def _initialize_telemetry(self):
    self.telemetry = TelemetryService()
    self.telemetry.collector.set_formation_info(
        agents=len(self.agents),
        tools=self._count_tools(),
        mcp_servers=len(self.mcp_servers),
        memory_backend=self.memory_config.get("backend", "none"),
        features=self._enabled_features()
    )
    await self.telemetry.start()
```

### 2. Request Middleware

> **Server Integration:** The MUXI Server proxy passes through `X-Muxi-*` headers from clients. The runtime can read:
> - `X-Muxi-Server` - Server version (e.g., "1.0.0") - indicates request came through server
> - `X-Muxi-SDK` - SDK identifier (e.g., "python/1.2.3", "cli/0.12.0") - identifies calling SDK

#### Request Source Tracking

Two independent dimensions are tracked:

**Route** (how the request arrived - mutually exclusive):
| Source | Condition | Example |
|--------|-----------|---------|
| `framework` | Direct Python API call (no HTTP) | `formation.chat("hello")` |
| `api.direct` | HTTP without `X-Muxi-Server` header | curl directly to runtime |
| `api.server` | HTTP with `X-Muxi-Server` header | Request proxied through MUXI Server |

**SDK** (which SDK made the request - independent dimension):

Extracted from `X-Muxi-SDK` header (format: `sdk/version`):
| Header Value | Extracted SDK |
|--------------|---------------|
| `python/1.2.3` | `python` |
| `typescript/0.5.0` | `typescript` |
| `cli/1.0.0` | `cli` |
| `java/2.0.0` | `java` |
| (no header) | not counted |

**Math:**
- `total = framework + api.direct + api.server`
- `sum(sdk.*) = requests with X-Muxi-SDK header` (currently subset of api.server, may change)

```python
# In server/middleware.py
@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    start = time.time()
    
    # Determine route (how request arrived)
    has_server_header = request.headers.get("X-Muxi-Server") is not None
    route = "server" if has_server_header else "direct"
    
    # Determine SDK (independent dimension)
    sdk_header = request.headers.get("X-Muxi-SDK", "")
    sdk = sdk_header.split("/")[0] if sdk_header else None  # "python", "typescript", "cli", or None
    
    try:
        response = await call_next(request)
        latency_ms = (time.time() - start) * 1000
        telemetry.collector.record_request(
            success=response.status_code < 400,
            latency_ms=latency_ms,
            route=route,
            sdk=sdk
        )
        return response
    except Exception as e:
        telemetry.collector.record_request(success=False, latency_ms=0, route=route, sdk=sdk)
        telemetry.collector.record_error(_classify_error(e))
        raise
```

For framework mode (direct Python API), track at the Formation level:

```python
# In formation.py
async def chat(self, message: str, ...):
    start = time.time()
    try:
        result = await self._process_chat(message, ...)
        latency_ms = (time.time() - start) * 1000
        self.telemetry.collector.record_request(
            success=True,
            latency_ms=latency_ms,
            route="framework",
            sdk=None
        )
        return result
    except Exception as e:
        self.telemetry.collector.record_request(success=False, latency_ms=0, route="framework", sdk=None)
        raise
```

### 3. LLM Service

```python
# In services/llm/llm.py
async def complete(self, messages, **kwargs):
    provider = self._get_provider_name()  # "openai", "anthropic", etc.
    cache_hit = self._check_cache(messages)
    
    telemetry.collector.record_llm_request(provider, cache_hit)
    # ... rest of completion logic
```

### 4. Feature Usage

```python
# In overlord/clarification.py
async def request_clarification(self, ...):
    telemetry.collector.record_feature_use("clarification")
    # ...

# In workflow/executor.py
async def execute_workflow(self, ...):
    telemetry.collector.record_feature_use("workflow")
    # ...

# In scheduler/service.py
async def run_scheduled_task(self, ...):
    telemetry.collector.record_feature_use("scheduled_task")
    # ...
```

---

## Error Classification

```python
def classify_error(error: Exception) -> str:
    error_str = str(error).lower()
    
    if "timeout" in error_str or isinstance(error, asyncio.TimeoutError):
        return "timeout"
    if "rate" in error_str and "limit" in error_str:
        return "rate_limit"
    if "401" in error_str or "403" in error_str or "auth" in error_str:
        return "auth"
    if "connection" in error_str or "network" in error_str:
        return "network"
    
    return "internal"
```

---

## Local State File

> **Server Decision:** Simple accumulate-until-sent approach. No historical data kept.

Path: `~/.muxi/runtime/telemetry.json`

```json
{
  "last_flush": "2026-01-02T09:00:00Z",
  "pending_payload": {
    "requests": {"total": 150, "success": 148},
    "...": "..."
  }
}
```

Behavior:
- **Successful send** → Clear file, reset counters, start fresh
- **Failed send** → Keep accumulating until next successful send
- **Runtime restart** → Load pending payload, continue accumulating
- **Telemetry disabled** → Still collect locally (in case user re-enables)

---

## Testing

### Environment Override

```bash
export TELEMETRY_URL=http://localhost:8080/v1/telemetry
export MUXI_TELEMETRY=0  # Disable sending (still collects)
```

### Unit Tests

```python
def test_machine_id_deterministic():
    """Same machine should generate same ID."""
    id1 = generate_machine_id()
    id2 = generate_machine_id()
    assert id1 == id2

def test_collector_thread_safe():
    """Concurrent increments should be accurate."""
    collector = TelemetryCollector()
    # ... concurrent test

def test_flush_respects_opt_out():
    """Data collected but not sent when disabled."""
    # ...
```

---

## Rollout Plan

### Phase 1: Infrastructure (Day 1)
- [ ] Create telemetry module structure
- [ ] Implement machine_id.py
- [ ] Implement config.py
- [ ] Unit tests for core functions

### Phase 2: Collection (Day 1-2)
- [ ] Implement collector.py
- [ ] Implement sender.py
- [ ] Implement service.py
- [ ] Add formation startup integration

### Phase 3: Integration (Day 2)
- [ ] Add request middleware
- [ ] Add LLM tracking
- [ ] Add feature usage tracking
- [ ] Integration tests

### Phase 4: Validation (Day 2)
- [ ] Test with local receiver
- [ ] Verify payload format
- [ ] Test opt-out behavior
- [ ] Test restart persistence

---

## Open Questions

1. **Percentile calculation** - Keep last N latencies in memory or use streaming algorithm (t-digest)?
   > *Suggestion:* Keep last 1000 latencies in memory, calculate percentiles on snapshot. Simple and sufficient.

2. ~~**Formation changes** - If user hot-reloads formation, do we track as new session or continue?~~
   > **RESOLVED:** Continue same session. Formation info is updated on reload but counters persist.

3. ~~**Multi-formation** - If someone runs multiple formations on same machine, separate or combined telemetry?~~
   > **RESOLVED:** Separate. Each runtime instance has its own telemetry service and sends independently.

4. ~~**Startup telemetry** - Send on startup or wait for first hourly flush?~~
   > **RESOLVED:** Wait for first hourly flush. Consistent with server behavior.

---

## Appendix: Privacy Review Checklist

Before shipping, verify:

- [ ] No formation names, paths, or content in payload
- [ ] No user prompts or agent responses
- [ ] No API keys, tokens, or secrets
- [ ] No IP addresses (country code only)
- [ ] No timestamps that could identify users
- [ ] Machine ID is hashed, not raw hardware ID
- [ ] Opt-out is respected at env and config level
