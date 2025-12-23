# Request Cancellation Design

**Status:** Implemented
**Created:** 2025-12-23
**Updated:** 2025-12-23

## Problem

When a user calls `DELETE /requests/{request_id}`, the request is marked as cancelled but the actual work continues until completion. This wastes resources and can cause confusion.

## Solution Overview

Cooperative cancellation using a cancelled set in `RequestTracker` with checkpoints placed after all long-running operations (LLM calls, MCP tool invocations, A2A requests).

## Architecture

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `RequestTracker._cancelled` | `background/request_tracker.py` | Set of cancelled request IDs |
| `RequestCancelledException` | `background/cancellation.py` | Exception raised at checkpoints |
| `check_cancellation_from_context()` | `background/cancellation.py` | Helper for context-based checks |
| Checkpoints | Various files | Check cancellation after long operations |

### Flow

```
DELETE /requests/{id}
  │
  ├─► request_tracker.mark_cancelled(id)
  │
  └─► overlord.cancel_request(id) ─► task_ref.cancel() [may fail]

Processing continues until checkpoint:
  │
  └─► is_cancelled(id)?
        │
        ├─► Yes: clear_cancelled(id), raise RequestCancelledException
        │         │
        │         └─► Caught at top-level ─► log event ─► return empty response
        │
        └─► No: continue normally
```

## Checkpoint Coverage

### Overlord (overlord.py)

| Method | Checkpoint Location |
|--------|---------------------|
| `_process_sync_chat` | Start of processing |
| `_process_sync_chat` | Before clarification analysis |
| `_process_sync_chat` | Before request analysis |
| `_process_sync_chat` | Before agent processing |
| `_execute_workflow` | Before workflow execution |
| `_apply_persona` | After LLM call |

### Agent (agent.py)

| Method | Checkpoint Location |
|--------|---------------------|
| `process_message` | Before LLM call with tools |
| `process_message` | Before fallback LLM call |
| `process_message` | Before normal LLM call (no tools) |
| `process_message` | Before final LLM call |
| `process_message` | Before tool chain execution |
| `invoke_tool` | After MCP call returns (2 locations) |
| `_plan_before_execution` | After planning LLM call |
| `_request_a2a_assistance` | After A2A call returns |

### Clarification (clarification.py)

| Method | Checkpoint Location |
|--------|---------------------|
| `_analyze_request` | After LLM call |
| `_check_need_more` | After LLM call |
| `_is_recall_question_with_answer` | After LLM call |

### Workflow (analyzer.py, decomposer.py)

| Method | Checkpoint Location |
|--------|---------------------|
| `_llm_analyze_request` | After LLM call |
| `decompose_request` | After LLM call |

## Implementation Details

### RequestTracker Extensions

```python
class RequestTracker:
    def __init__(self):
        self._requests: Dict[str, RequestState] = {}
        self._cancelled: Set[str] = set()  # Cancelled request IDs
        self._lock = asyncio.Lock()

    async def mark_cancelled(self, request_id: str) -> None:
        """Mark request as cancelled for cooperative cancellation."""
        async with self._lock:
            self._cancelled.add(request_id)

    def is_cancelled(self, request_id: str) -> bool:
        """Check if request is marked cancelled. O(1) set lookup."""
        return request_id in self._cancelled

    async def clear_cancelled(self, request_id: str) -> None:
        """Remove from cancelled set after processing cancellation."""
        async with self._lock:
            self._cancelled.discard(request_id)
```

### Cancellation Check Pattern

```python
# Direct check (when request_id is available)
if request_id and self.request_tracker.is_cancelled(request_id):
    await self.request_tracker.clear_cancelled(request_id)
    raise RequestCancelledException(request_id)

# Context-based check (when request_id not in scope)
from ..background.cancellation import check_cancellation_from_context
await check_cancellation_from_context(self.request_tracker)
```

### Exception Handling

```python
# At top level (chat_orchestrator._process_sync_chat)
try:
    response = await self.overlord._process_sync_chat(...)
except RequestCancelledException as e:
    observability.observe(...)
    return MuxiResponse(content="", ...)
```

## Safety Analysis

**Normal operation (no cancel request):**
- `is_cancelled()` is O(1) set lookup
- `_cancelled` set is empty (never populated)
- Returns `False` immediately
- **Zero impact on normal flow**

**Only when DELETE is called:**
- `mark_cancelled()` adds to set
- Next checkpoint finds it
- Exception propagates up
- Request terminates cleanly

## Files Modified

| File | Changes |
|------|---------|
| `formation/background/request_tracker.py` | `_cancelled` set, `mark_cancelled()`, `is_cancelled()`, `clear_cancelled()` |
| `formation/background/cancellation.py` | NEW - `RequestCancelledException`, `check_cancellation_from_context()` |
| `formation/server/routes/client/requests.py` | Call `mark_cancelled()` before `cancel_request()` |
| `formation/overlord/chat_orchestrator.py` | Catch `RequestCancelledException`, return empty response |
| `formation/overlord/overlord.py` | 6 checkpoints, `_check_cancelled()` helper |
| `formation/overlord/clarification.py` | 3 checkpoints after LLM calls |
| `formation/agents/agent.py` | 8 checkpoints (LLM, MCP, A2A) |
| `formation/workflow/analyzer.py` | 1 checkpoint after LLM call |
| `formation/workflow/decomposer.py` | 1 checkpoint after LLM call |

## Testing

```bash
# Start a long-running request
curl -X POST 'http://localhost:8002/v1/chat' \
  -H 'Content-Type: application/json' \
  -H 'X-MUXI-CLIENT-KEY: clientkey' \
  -d '{"message": "write a very long story", "request_id": "test123", "stream": true}'

# In another terminal, cancel it
curl -X DELETE 'http://localhost:8002/v1/requests/test123' \
  -H 'X-MUXI-CLIENT-KEY: clientkey' \
  -H 'X-Muxi-User-ID: 0'
```

## Future Enhancements

- Add cancellation checkpoints inside workflow executor loop
- Add streaming cancellation support (SSE close detection)
- Add cancellation metrics/observability
