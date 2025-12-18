# PRD: Logging Configuration Restructure

**Date:** 2025-12-18  
**Status:** Proposed  
**Author:** Engineering  

## 1. Decision

Restructure the `logging:` configuration in formation.afs to separate **system events** (infrastructure/debugging) from **conversation events** (user-facing/streamable).

### Current Structure
```yaml
logging:
  enabled: true
  streams:
    - transport: stdout
      level: debug
      format: jsonl
    - transport: file
      destination: /path/to/formation.log
      level: debug
```

### New Structure
```yaml
logging:
  system:
    level: debug              # default: debug
    destination: stdout       # default: stdout, or file path
  conversation:
    enabled: true
    streams:
      - transport: stdout
        level: debug
        format: jsonl
      - transport: file
        destination: /path/to/formation.log
        level: debug
```

## 2. Reasoning

### Current Problems

1. **Hardcoded Routing**: `SystemEvents`, `ErrorEvents`, `ServerEvents`, `APIEvents` are hardcoded to stdout in `EventLogger._emit_to_output()`, ignoring any transport configuration.

2. **Mixed Concerns**: The `streams` configuration was designed for conversation events (user-facing, streamable to clients), but system events (infrastructure debugging) have different requirements.

3. **No Control**: Users cannot:
   - Send system events to a file for production log aggregation
   - Suppress system events from stdout
   - Configure different log levels for system vs conversation events

### Design Rationale

| Aspect | Conversation Events | System Events |
|--------|---------------------|---------------|
| **Purpose** | User-facing, streamable to clients | Developer debugging, infrastructure |
| **Consumers** | SDKs, UIs, clients via SSE | DevOps, log aggregation, developers |
| **Volume** | Per-request lifecycle | Startup, connections, errors |
| **Complexity** | Multiple transports, formats, protocols | Simple: stdout or file |
| **Examples** | `request.received`, `agent.thinking.started`, `response.delivered` | `llm.initialized`, `mcp.server.connected`, `error.validation.failed` |

### Event Type Classification

| Event Class | Route To |
|-------------|----------|
| `ConversationEvents` | `logging.conversation.streams` |
| `SystemEvents` | `logging.system.destination` |
| `ErrorEvents` | `logging.system.destination` |
| `ServerEvents` | `logging.system.destination` |
| `APIEvents` | `logging.system.destination` |

## 3. Files to Change

### Schema Files - Runtime (code/runtime/schemas/formation/)

| File | Change |
|------|--------|
| `formation.yaml` | Update `logging:` section with new nested structure |
| `LOGGING.md` | Update documentation to reflect new structure |
| `README.md` | No change needed (references SCHEMA_GUIDE.md) |

### Schema Files - Agent Formation Spec (agent-formation-spec/)

| File | Change |
|------|--------|
| `schemas/formation.afs` | Update `logging:` section with new nested structure |
| `schemas/LOGGING.md` | Update documentation to reflect new structure |
| `schemas/SCHEMA_GUIDE.md` | Update logging section if referenced |
| `specs/formation.md` | Update if logging is documented there |

### Runtime Files (src/muxi/)

| File | Change |
|------|--------|
| `formation/initialization.py` | Parse new `logging.system` and `logging.conversation` structure |
| `services/observability/logger.py` | Remove hardcoded stdout routing; route based on event type to system or conversation destination |
| `formation/config/validation.py` | Update schema validation for new logging structure |

### Test Files

| File | Change |
|------|--------|
| `tests/unit/services/observability/test_logger.py` | Update tests for new routing logic |
| `tests/integration/observability/` | Update integration tests |
| `e2e/tests/01_foundation/` | Update any logging-related e2e tests |

### Documentation Files

| File | Change |
|------|--------|
| `docs/features/observability.md` | Update if exists |

## 4. API Endpoint Behavior

### Existing Endpoints (No Changes Required)

The API endpoints stream events via `ObservabilityManager.subscribe()`, which filters events from an internal queue. The routing change happens at **emit time**, not at subscription time.

#### `/events` (Client - SSE)
- **Current**: Filters for `chat.`, `agent.`, `workflow.`, `task.` events
- **After Change**: Same behavior - these are ConversationEvents, routed via `logging.conversation.streams`
- **No code change needed**

#### `/events/{session_id}` (Client - SSE)
- **Current**: Same filter as `/events`, scoped to session
- **After Change**: Same behavior
- **No code change needed**

#### `/events/{session_id}/{request_id}` (Client - SSE)
- **Current**: Uses `streaming_manager` for response tokens
- **After Change**: Same behavior - streaming manager is independent of logging config
- **No code change needed**

#### `/logs` (Admin - SSE)
- **Current**: Streams all events matching filters via `observability_manager.subscribe()`
- **After Change**: Same behavior - subscription sees all events regardless of file/stdout routing
- **No code change needed**

### Why Endpoints Don't Need Changes

```
Event Flow:
                                    ┌──────────────────┐
                                    │ stdout/file      │
                                    │ (system events)  │
                                    └──────────────────┘
                                           ▲
                                           │
┌─────────┐    ┌────────────────┐    ┌─────┴─────┐    ┌──────────────────┐
│ observe │───▶│ EventLogger    │───▶│ _emit_to_ │───▶│ file/stdout/     │
│   ()    │    │ .emit_event()  │    │ output()  │    │ stream (convo)   │
└─────────┘    └───────┬────────┘    └───────────┘    └──────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │ Internal Queue │◀──── ObservabilityManager.subscribe()
              │ (all events)   │      (API endpoints read from here)
              └────────────────┘
```

The internal queue receives ALL events regardless of where they're routed for persistence. API endpoints subscribe to this queue with their own filters.

## 5. Default Behavior

### When `logging:` is not specified
```yaml
# Implicit defaults:
logging:
  system:
    level: debug
    destination: stdout
  conversation:
    enabled: false
```

### When only `logging.system:` is specified
```yaml
logging:
  system:
    destination: /var/log/system.log
# Conversation events disabled (no streams configured)
```

### When only `logging.conversation:` is specified
```yaml
logging:
  conversation:
    enabled: true
    streams:
      - transport: file
        destination: /var/log/conversation.log
# System events go to stdout at debug level (default)
```

## 6. Migration Guide

### Before (Current)
```yaml
logging:
  enabled: true
  streams:
    - transport: file
      destination: /var/log/formation.log
      level: debug
```

### After (New)
```yaml
logging:
  system:
    level: debug
    destination: stdout  # or /var/log/system.log
  conversation:
    enabled: true
    streams:
      - transport: file
        destination: /var/log/formation.log
        level: debug
```

## 7. Implementation Order

1. **Update schemas** (`formation.yaml`, `LOGGING.md`)
2. **Update validation** (`config/validation.py`)
3. **Update initialization** (`initialization.py`)
4. **Update logger routing** (`logger.py`)
5. **Update tests**
6. **Test with real formations**

## 8. No Backward Compatibility

As specified, backward compatibility is NOT required. Existing formations must update their `logging:` configuration to the new structure.
