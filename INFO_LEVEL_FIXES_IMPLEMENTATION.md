# INFO-Level ErrorEvents Fixes - Implementation Plan

**Status**: 12 new SystemEvents added to enum ✅  
**Remaining**: 19 code changes across 9 files

---

## Changes to Implement

### 1. src/muxi/services/llm/llm.py (4 changes)

**Line 790**: ErrorEvents.INTERNAL_ERROR (INFO) → SystemEvents.LLM_INITIALIZED (DEBUG)
```python
# BEFORE:
observability.observe(
    event_type=observability.ErrorEvents.INTERNAL_ERROR,
    level=observability.EventLevel.INFO,
    ...
)

# AFTER:
observability.observe(
    event_type=observability.SystemEvents.LLM_INITIALIZED,
    level=observability.EventLevel.DEBUG,
    ...
)
```

**Line 1824**: ErrorEvents.INTERNAL_ERROR (INFO) → SystemEvents.LLM_CACHE_CLEARED (DEBUG)
**Line 1836**: ErrorEvents.INTERNAL_ERROR (INFO) → SystemEvents.LLM_CACHE_CONFIGURED (DEBUG)
**Line 1897**: ErrorEvents.INTERNAL_ERROR (INFO) → SystemEvents.LLM_STATISTICS_RESET (INFO)

---

### 2. src/muxi/services/mcp/reconnection.py (2 changes)

**Line 318**: ErrorEvents.RETRY_ATTEMPTED (INFO) → SystemEvents.MCP_RETRY_ATTEMPTED (INFO)
```python
# BEFORE:
observability.observe(
    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
    level=observability.EventLevel.INFO,
    ...
)

# AFTER:
observability.observe(
    event_type=observability.SystemEvents.MCP_RETRY_ATTEMPTED,
    level=observability.EventLevel.INFO,
    ...
)
```

**Line 416**: SystemEvents.OPERATION_COMPLETED (INFO) → Keep as OPERATION_COMPLETED but change to DEBUG
```python
# Change level only:
level=observability.EventLevel.DEBUG,
```

---

### 3. src/muxi/services/mcp/handler.py (2 changes)

**Line 547**: SystemEvents.MCP_OVERLORD_REQUEST_CANCELLED - Change INFO → DEBUG
**Line 1038**: SystemEvents.MCP_SERVER_OPERATIONS_CANCELLED - Change INFO → DEBUG

```python
# Change level only:
level=observability.EventLevel.DEBUG,
```

---

### 4. src/muxi/formation/documents/workflow/cross_reference_manager.py (3 changes)

**Line 103**: SystemEvents.OPERATION_COMPLETED → SystemEvents.CROSS_REFERENCE_MANAGER_INITIALIZED (DEBUG)
```python
# BEFORE:
observability.observe(
    event_type=observability.SystemEvents.OPERATION_COMPLETED,
    level=observability.EventLevel.INFO,
    ...
)

# AFTER:
observability.observe(
    event_type=observability.SystemEvents.CROSS_REFERENCE_MANAGER_INITIALIZED,
    level=observability.EventLevel.DEBUG,
    ...
)
```

**Line 195**: SystemEvents.OPERATION_COMPLETED → SystemEvents.CROSS_REFERENCE_ADDED (DEBUG)
**Line 290**: SystemEvents.OPERATION_COMPLETED → SystemEvents.CROSS_REFERENCES_LOADED (DEBUG)

---

### 5. src/muxi/formation/overlord/overlord.py (1 change)

**Line 1340**: SystemEvents.OPERATION_COMPLETED - Change INFO → DEBUG
```python
# Change level only:
level=observability.EventLevel.DEBUG,
```

---

### 6. src/muxi/services/a2a/client.py (2 changes)

**Line 93**: DELETE entire observability.observe() call
```python
# REMOVE this entire block:
observability.observe(
    event_type=observability.SystemEvents.OPERATION_COMPLETED,
    level=observability.EventLevel.INFO,
    data={"operation": "a2a_sdk_init", "skipped": True},
    description="A2A SDK initialization skipped - no external registry URL",
)
```

**Line 439**: SystemEvents.OPERATION_COMPLETED → SystemEvents.A2A_HTTPX_CLEANUP (DEBUG)
```python
# BEFORE:
observability.observe(
    event_type=observability.SystemEvents.OPERATION_COMPLETED,
    level=observability.EventLevel.INFO,
    data={"operation": "a2a_httpx_cleanup"},
    description="A2A service httpx client closed successfully",
)

# AFTER:
observability.observe(
    event_type=observability.SystemEvents.A2A_HTTPX_CLEANUP,
    level=observability.EventLevel.DEBUG,
    data={"operation": "a2a_httpx_cleanup"},
    description="A2A service httpx client closed successfully",
)
```

---

### 7. src/muxi/utils/user_resolution.py (3 changes)

**Line 132**: SystemEvents.OPERATION_COMPLETED → SystemEvents.USER_RESOLVED (DEBUG)
```python
# BEFORE:
observability.observe(
    event_type=observability.SystemEvents.OPERATION_COMPLETED,
    level=observability.EventLevel.INFO,
    data={
        "operation": "user_identifier_resolved",
        ...
    },
    ...
)

# AFTER:
observability.observe(
    event_type=observability.SystemEvents.USER_RESOLVED,
    level=observability.EventLevel.DEBUG,
    data={
        "operation": "user_identifier_resolved",
        ...
    },
    ...
)
```

**Line 163**: SystemEvents.OPERATION_COMPLETED → SystemEvents.USER_CREATED (DEBUG)
**Line 353**: SystemEvents.OPERATION_COMPLETED → SystemEvents.USER_IDENTIFIERS_ASSOCIATED (DEBUG)

---

### 8. src/muxi/services/scheduler/parser.py (1 change)

**Line 145**: SystemEvents.SCHEDULER_PARSER_INITIALIZED - Change INFO → DEBUG
```python
# Change level only:
level=observability.EventLevel.DEBUG,
```

---

## Summary

| File | Changes | Type |
|------|---------|------|
| llm.py | 4 | Event type + level |
| reconnection.py | 2 | Event type (1), level (1) |
| handler.py | 2 | Level only |
| cross_reference_manager.py | 3 | Event type + level |
| overlord.py | 1 | Level only |
| a2a/client.py | 2 | DELETE (1), event type + level (1) |
| user_resolution.py | 3 | Event type + level |
| scheduler/parser.py | 1 | Level only |
| **Total** | **19** | **All fixes** |

---

## Rationale

**ErrorEvents at INFO level**: These are SUCCESS/operational events misclassified as errors
- Fixed by changing to appropriate SystemEvents

**OPERATION_COMPLETED overuse**: Too generic for monitoring
- Fixed by creating specific event types

**INFO → DEBUG**: Operational details not user-facing
- Fixed by downgrading to DEBUG level

**DELETE a2a/client.py:93**: "SDK init skipped" is noise, not valuable
- Removed entirely

---

## Next Step

Run script to apply all 19 changes automatically or implement manually file-by-file.
