# Request Cancellation Design

**Status:** Implemented
**Created:** 2025-12-23
**Updated:** 2025-12-23

## Problem

When a user calls `DELETE /requests/{request_id}`, the request is marked as cancelled but the actual work continues until completion. This wastes resources and can cause confusion.

## Current Behavior

1. `DELETE /requests/{id}` calls `overlord.cancel_request(request_id)`
2. `cancel_request()` calls `task_ref.cancel()` (asyncio cancellation)
3. Status is set to "cancelled" in tracker
4. **But**: Work continues until next `await` point, and `CancelledError` may be swallowed by exception handlers

## Existing Infrastructure (to leverage)

| Component | Location | Purpose |
|-----------|----------|---------|
| `RequestTracker` | `formation/background/request_tracker.py` | Already tracks requests with `task_ref` |
| `RequestStatus.CANCELLED` | `request_tracker.py` | Status enum already exists |
| `RequestContext` | `datatypes/observability.py` | Has `id` field for request_id |
| `get_current_request_context()` | `services/observability/context.py` | Gets context from contextvars |
| `cancel_request()` | `overlord.py` | Already handles task cancellation |

## Proposed Solution

Extend `RequestTracker` with a cancelled set and add a `@cancellable` decorator for cooperative cancellation checkpoints.

### Changes

#### 1. Extend RequestTracker (modify existing)

```python
# src/muxi/formation/background/request_tracker.py

class RequestTracker:
    def __init__(self):
        self._requests: Dict[str, RequestState] = {}
        self._cancelled: Set[str] = set()  # NEW
        self._lock = asyncio.Lock()

    async def mark_cancelled(self, request_id: str) -> None:  # NEW
        """Mark request as cancelled for cooperative cancellation."""
        async with self._lock:
            self._cancelled.add(request_id)

    def is_cancelled(self, request_id: str) -> bool:  # NEW (sync for decorator)
        """Check if request is marked cancelled. Non-blocking."""
        return request_id in self._cancelled

    async def clear_cancelled(self, request_id: str) -> None:  # NEW
        """Remove from cancelled set (called when cancellation is processed)."""
        async with self._lock:
            self._cancelled.discard(request_id)

    async def remove_request(self, request_id: str) -> bool:
        """Remove a request from tracking."""
        async with self._lock:
            self._cancelled.discard(request_id)  # NEW: cleanup cancelled set too
            if request_id in self._requests:
                del self._requests[request_id]
                return True
            return False
```

#### 2. Add Exception and Decorator (new file)

```python
# src/muxi/formation/background/cancellation.py

from functools import wraps
from ...services.observability.context import get_current_request_context

class RequestCancelledException(Exception):
    """Raised when processing detects a cancelled request."""
    def __init__(self, request_id: str):
        self.request_id = request_id
        super().__init__(f"Request {request_id} cancelled by user")


def cancellable(request_tracker):
    """
    Factory that creates a cancellable decorator using the given tracker.

    Usage:
        # At module level or in class
        check_cancelled = cancellable(overlord.request_tracker)

        @check_cancelled
        async def some_function(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            ctx = get_current_request_context()
            if ctx and request_tracker.is_cancelled(ctx.id):
                await request_tracker.clear_cancelled(ctx.id)
                raise RequestCancelledException(ctx.id)
            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

#### 3. Modify DELETE endpoint

```python
# src/muxi/formation/server/routes/client/requests.py

@router.delete("/requests/{request_id}")
async def cancel_request(...):
    # ... existing validation ...

    # Mark for cooperative cancellation (NEW)
    await overlord.request_tracker.mark_cancelled(request_id)

    # Existing: also try asyncio cancellation
    result = await overlord.cancel_request(request_id)
    # ...
```

#### 4. Add top-level exception handler

```python
# In overlord._process_sync_chat or chat_orchestrator.chat

from ..background.cancellation import RequestCancelledException

try:
    # ... existing processing ...
except RequestCancelledException as e:
    observability.observe(
        event_type=observability.ConversationEvents.REQUEST_FAILED,
        level=observability.EventLevel.INFO,
        data={
            "request_id": e.request_id,
            "reason": "cancelled_by_user",
            "cancelled": True
        },
        description="Request processing stopped - cancelled by user",
    )
    # No return value needed - DELETE already responded
```

#### 5. Add decorator to key checkpoints

```python
# In overlord.py (during initialization or as class method)
self._cancellable = cancellable(self.request_tracker)

# Then use on key methods:
@self._cancellable
async def _call_agent(self, ...): ...
```

**Alternative** - simpler inline check without decorator:
```python
async def _some_method(self, ...):
    ctx = get_current_request_context()
    if ctx and self.request_tracker.is_cancelled(ctx.id):
        raise RequestCancelledException(ctx.id)
    # ... rest of method
```

### Flow

```
DELETE /requests/{id}
  │
  ├─► request_tracker.mark_cancelled(id)
  │
  └─► overlord.cancel_request(id) ─► task_ref.cancel()

Processing continues until:
  │
  └─► Checkpoint reached (decorated function or inline check)
        │
        ├─► is_cancelled(id)?
        │     │
        │     ├─► Yes: clear_cancelled(id), raise RequestCancelledException
        │     │         │
        │     │         └─► Caught at top-level ─► log event ─► stop
        │     │
        │     └─► No: continue
```

## Strategic Checkpoint Placement

Only add checks at meaningful boundaries:

| Checkpoint | Location | Rationale |
|------------|----------|-----------|
| Before LLM call | `LLM.chat()` | Can take 5-30+ seconds |
| Before tool execution | `agent._execute_tool()` | External calls |
| Before workflow task | `WorkflowExecutor.execute_task()` | Long-running |
| Before agent routing | `overlord._route_to_agent()` | Entry point |

## Memory Management

**Automatic cleanup** via existing `remove_request()`:
- When request completes (success/failure), `remove_request()` is called
- Now also clears `_cancelled` set
- No separate TTL needed

## Breaking Changes

**None:**
- New methods on RequestTracker are additive
- Decorator is opt-in per function
- Exception caught internally, doesn't affect API contract
- DELETE endpoint returns same response

## Testing Plan

1. Unit: `RequestTracker.mark_cancelled/is_cancelled/clear_cancelled`
2. Unit: Decorator raises exception when cancelled
3. Integration: DELETE stops processing at next checkpoint
4. E2E: Cancel long-running MCP tool call

## Implementation Order

1. Add `_cancelled` set and methods to `RequestTracker` - DONE
2. Create `cancellation.py` with exception and decorator - DONE
3. Modify DELETE endpoint to call `mark_cancelled()` - DONE
4. Add exception handler in `_process_sync_chat` - DONE
5. Add inline checks to 2-3 key locations (start simple) - DONE
6. Add tests - TODO
7. Expand checkpoints as needed - TODO

## Implementation Notes

### Files Modified

| File | Changes |
|------|---------|
| `formation/background/request_tracker.py` | Added `_cancelled` set, `mark_cancelled()`, `is_cancelled()`, `clear_cancelled()` |
| `formation/background/cancellation.py` | NEW - `RequestCancelledException`, `cancellable()` decorator, `check_cancellation()` |
| `formation/server/routes/client/requests.py` | Added `mark_cancelled()` call before `cancel_request()` |
| `formation/overlord/chat_orchestrator.py` | Added try/except for `RequestCancelledException` in `_process_sync_chat` |
| `formation/overlord/overlord.py` | Added inline cancellation checks before agent processing and workflow execution |
| `formation/agents/agent.py` | Added `_check_cancellation()` helper and checkpoints before LLM calls and tool executions |

### Current Checkpoints

1. **Before agent processing** - `overlord.py` line ~6930
2. **Before workflow execution** - `overlord.py` line ~8152
3. **Before LLM calls in agent** - `agent.py` (multiple locations)
   - Before `chat_with_tools()` call
   - Before fallback `chat()` call
   - Before normal `chat()` call (no tools)
4. **Before tool executions in agent** - `agent.py`
   - Before planning tool execution
   - Before tool chain execution

### Future Checkpoints (if needed)

- Inside workflow executor for each task
- Before A2A requests
