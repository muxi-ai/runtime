# Request Cancellation Feature

## Overview

Allow users to cancel long-running chat requests via `DELETE /requests/{request_id}`. This stops further processing but does not undo completed side effects.

## API Endpoint

```
DELETE /v1/requests/{request_id}
```

**Response:**
```json
{
  "object": "request_status",
  "type": "request.cancelled",
  "data": {
    "request_id": "req_abc123",
    "status": "cancelled",
    "cancelled_at": 1706616000.0,
    "partial_results": null
  }
}
```

## What Cancellation Does

1. Sets cancellation flag on the request
2. Stops further processing at the next checkpoint
3. Returns cancellation status to client
4. Closes any open streams

## What Cancellation Does NOT Do

- Cancel HTTP requests already sent to LLM providers
- Undo files created by MCP tools
- Delete generated artifacts
- Reverse external API calls (Slack messages, emails, etc.)
- Remove memory entries that were persisted

## Implementation Requirements

### 1. Request Tracker Enhancement

```python
class RequestTracker:
    async def cancel_request(self, request_id: str) -> bool:
        """Mark request for cancellation."""
        
    async def is_cancelled(self, request_id: str) -> bool:
        """Check if request has been cancelled."""
```

### 2. Cancellation Checkpoints

Insert cancellation checks at key points in the processing flow:

**Overlord (`overlord.py`):**
- Before sending to LLM
- After LLM response returns (discard if cancelled)
- Before tool execution
- Before memory persistence

**Streaming (`chat()`):**
- Between token yields in streaming generator
- Break loop and close stream on cancellation

**Workflow Executor:**
- Between workflow steps
- Before each task execution

**MCP Tool Execution:**
- Before each tool call
- Between tool iterations

### 3. Cancellation Pattern

```python
async def _process_chat(self, message, request_id, ...):
    # Check before LLM call
    if await self.request_tracker.is_cancelled(request_id):
        raise RequestCancelledException(request_id)
    
    # Make LLM call
    response = await self.llm.chat(...)
    
    # Check after LLM call - discard response if cancelled
    if await self.request_tracker.is_cancelled(request_id):
        raise RequestCancelledException(request_id)
    
    # Continue processing...
```

### 4. Streaming Cancellation

```python
async def _stream_response(self, request_id, ...):
    async for token in llm_stream:
        if await self.request_tracker.is_cancelled(request_id):
            yield {"event": "cancelled", "data": {"request_id": request_id}}
            break
        yield {"event": "token", "data": {"token": token}}
```

### 5. Exception Handling

```python
class RequestCancelledException(Exception):
    def __init__(self, request_id: str):
        self.request_id = request_id
        super().__init__(f"Request {request_id} was cancelled")
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Cancel before LLM call | Immediate cancellation, no LLM usage |
| Cancel during LLM call | Wait for response, discard it, stop processing |
| Cancel during streaming | Stop yielding tokens, send cancellation event |
| Cancel during tool execution | Complete current tool, stop before next |
| Cancel during workflow | Complete current step, stop before next |
| Cancel already completed request | Return error: request already finished |
| Cancel non-existent request | Return 404 |

## Future Enhancements (Out of Scope for v1)

### Artifact Cleanup (Optional)

Track side effects and offer cleanup:

```
DELETE /v1/requests/{request_id}?cleanup=true
```

Would require:
- Tracking all artifacts created during request
- MCP tools registering created files/resources
- Reversible operations log
- Cleanup executor

### Partial Results

Return what was completed before cancellation:

```json
{
  "data": {
    "status": "cancelled",
    "partial_results": {
      "tokens_generated": 150,
      "tools_executed": ["read_file"],
      "artifacts_created": ["output.txt"]
    }
  }
}
```

## Testing Strategy

1. **Unit tests:** RequestTracker cancellation flag
2. **Integration tests:** Cancellation at each checkpoint
3. **E2E tests:**
   - Cancel before processing starts
   - Cancel during LLM call
   - Cancel during streaming
   - Cancel during tool execution
   - Cancel during multi-step workflow

## Security Considerations

- Only the user who initiated the request can cancel it
- Admin can cancel any request
- Rate limit cancellation requests to prevent abuse

## Observability

New events:
- `request.cancellation.requested` - Cancellation initiated
- `request.cancelled` - Request successfully cancelled
- `request.cancellation.failed` - Could not cancel (already complete, etc.)
