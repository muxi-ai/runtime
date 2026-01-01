# Request Cancellation

Cancel in-flight requests to stop processing and free up resources.

## Quick Start

```bash
# Cancel a request by ID
curl -X DELETE 'http://localhost:8002/v1/requests/{request_id}' \
  -H 'X-MUXI-CLIENT-KEY: your-client-key' \
  -H 'X-Muxi-User-ID: user123'
```

## How It Works

1. **User sends DELETE request** to `/v1/requests/{request_id}`
2. **Request marked as cancelled** in the request tracker
3. **Processing continues** until the next checkpoint
4. **Checkpoint detects cancellation** and raises exception
5. **Exception caught** at top level, empty response returned
6. **Resources freed** immediately

## API

### Cancel Request

```
DELETE /v1/requests/{request_id}
```

**Headers:**
- `X-MUXI-CLIENT-KEY`: Your client API key (required)
- `X-Muxi-User-ID`: User identifier (required)

**Response:**
```json
{
  "status": "cancelled",
  "request_id": "req_abc123",
  "message": "Request cancellation initiated"
}
```

## Checkpoint Coverage

Cancellation is checked after every long-running operation:

| Operation | Typical Duration | Checkpoint |
|-----------|------------------|------------|
| LLM calls | 1-30+ seconds | After each call |
| MCP tool invocations | 1-60+ seconds | After call returns |
| A2A agent requests | 5-60+ seconds | After call returns |
| Clarification analysis | 1-5 seconds | After LLM call |
| Request analysis | 1-5 seconds | After LLM call |
| Task decomposition | 2-10 seconds | After LLM call |

## Usage Patterns

### Cancel Streaming Request

```python
import httpx
import asyncio

async def chat_with_cancel():
    async with httpx.AsyncClient() as client:
        # Start streaming request
        request_id = "my-request-123"
        
        async with client.stream(
            "POST",
            "http://localhost:8002/v1/chat",
            json={"message": "Write a long story", "request_id": request_id, "stream": True},
            headers={"X-MUXI-CLIENT-KEY": "key", "X-Muxi-User-ID": "user1"}
        ) as response:
            # Read some chunks
            async for chunk in response.aiter_lines():
                print(chunk)
                
                # Decide to cancel
                if should_cancel():
                    await client.delete(
                        f"http://localhost:8002/v1/requests/{request_id}",
                        headers={"X-MUXI-CLIENT-KEY": "key", "X-Muxi-User-ID": "user1"}
                    )
                    break
```

### Cancel from UI

```javascript
// React example
const [requestId, setRequestId] = useState(null);

const sendMessage = async (message) => {
  const id = `req_${Date.now()}`;
  setRequestId(id);
  
  const response = await fetch('/v1/chat', {
    method: 'POST',
    body: JSON.stringify({ message, request_id: id }),
    headers: { 'X-MUXI-CLIENT-KEY': apiKey }
  });
  // ... handle response
};

const cancelRequest = async () => {
  if (requestId) {
    await fetch(`/v1/requests/${requestId}`, {
      method: 'DELETE',
      headers: { 'X-MUXI-CLIENT-KEY': apiKey }
    });
    setRequestId(null);
  }
};
```

## Behavior Notes

1. **Immediate acknowledgment**: DELETE returns immediately with "cancelled" status
2. **Graceful termination**: Processing stops at next checkpoint, not mid-operation
3. **No partial results**: Cancelled requests return empty response
4. **Idempotent**: Cancelling already-cancelled request is safe
5. **No effect on completed**: Cancelling finished request has no effect

## Error Handling

| Scenario | Response |
|----------|----------|
| Request not found | 404 with error message |
| Request already completed | 200 with "already completed" |
| Request already cancelled | 200 with "already cancelled" |
| Invalid request ID | 400 with validation error |

## Performance Impact

**Normal requests (not cancelled):**
- Each checkpoint adds ~1 microsecond (set lookup)
- No memory overhead
- No API latency impact

**Cancelled requests:**
- Processing stops within milliseconds of next checkpoint
- LLM tokens saved from cancelled call
- MCP/A2A resources freed immediately

## Limitations

1. **Cannot cancel mid-LLM-call**: Once an LLM call starts, it runs to completion
2. **Cannot cancel mid-tool-execution**: MCP tool calls complete before checking
3. **Streaming partial results**: Already-sent SSE events cannot be recalled

## See Also

- [Design Document](../design/request-cancellation.md) - Implementation details
- [API Reference](../api/requests.md) - Full API documentation
- [Async Operations](../async-operations.md) - Background task management
