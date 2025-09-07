# Streaming Events Architecture

## Overview

This PRD describes the new streaming events architecture for MUXI Runtime that replaces the complex AsyncGenerator-based streaming with a clean, observability-style event emission pattern.

## Problem Statement

The current streaming implementation has several issues:
1. Python's limitation: Cannot both `yield` (for streaming) and `return` (for final response) in the same function
2. Code duplication: Separate methods for streaming vs non-streaming (`_process_streaming_chat`, `_process_with_workflow_streaming`, etc.)
3. Generator complexity: AsyncGenerators make the code harder to maintain and debug
4. Cannot return `request_id` immediately while also streaming content

## Solution

Implement streaming as a separate event emission system, similar to observability but independent from it. The runtime emits events through a fire-and-forget pattern, and interested clients can subscribe via SSE.

## Architecture

### Core Components

```
Runtime Code → streaming.stream() → StreamingManager → SSE Endpoint → SDK/Client
```

### Key Design Decisions

1. **Fire-and-forget pattern**: No `await`, no blocking the main execution path
2. **Single code path**: Same code handles both streaming and non-streaming requests
3. **Early return optimization**: If request isn't streaming-enabled, return immediately (zero overhead)
4. **Real-time only**: No buffering or replay of events - connect in time or miss them
5. **Independent from observability**: Separate system to avoid config conflicts

## Implementation

### 1. StreamingManager (`src/muxi/services/streaming.py`)

```python
from typing import Dict, Set
import asyncio
import time
from ...utils import multitasking

class StreamingManager:
    """Manages real-time streaming subscriptions"""
    
    def __init__(self):
        self.active_streams: Dict[str, Set[asyncio.Queue]] = {}
        
    def enable(self, request_id: str):
        """Mark request as streaming-enabled"""
        if request_id not in self.active_streams:
            self.active_streams[request_id] = set()
    
    def disable(self, request_id: str):
        """Clean up when request completes"""
        if request_id in self.active_streams:
            for queue in self.active_streams[request_id]:
                queue.put_nowait(None)  # Sentinel to close
            del self.active_streams[request_id]
    
    async def subscribe(self, request_id: str) -> asyncio.Queue:
        """Subscribe to events for a request"""
        if request_id not in self.active_streams:
            return None
        
        queue = asyncio.Queue()
        self.active_streams[request_id].add(queue)
        return queue
    
    async def emit_event(self, request_id: str, event_type: str, content: str, **metadata):
        """Send event to all subscribers"""
        if request_id not in self.active_streams:
            return
            
        event = {
            "request_id": request_id,
            "type": event_type,
            "content": content,
            "timestamp": time.time(),
            **metadata
        }
        
        for queue in self.active_streams[request_id]:
            try:
                queue.put_nowait(event)
            except:
                pass  # Queue full or closed

# Global instance
streaming_manager = StreamingManager()

@multitasking.task
def stream(request_id: str, event_type: str, content: str, **metadata):
    """
    Fire-and-forget streaming event emission.
    Only streams if request has streaming enabled.
    """
    if request_id not in streaming_manager.active_streams:
        return
    
    asyncio.create_task(
        streaming_manager.emit_event(request_id, event_type, content, **metadata)
    )

def enable(request_id: str):
    """Enable streaming for a request"""
    streaming_manager.enable_streaming(request_id)

def disable(request_id: str):
    """Disable streaming and cleanup"""
    streaming_manager.disable_streaming(request_id)
```

### 2. SSE Endpoint

```python
@app.get("/subscribe/{request_id}")
async def subscribe_to_events(request_id: str):
    """Server-Sent Events endpoint for real-time streaming"""
    
    async def event_generator():
        queue = await streaming_manager.subscribe(request_id)
        
        if not queue:
            yield f"data: {json.dumps({'error': 'Request not streaming'})}\n\n"
            return
        
        while True:
            event = await queue.get()
            
            if event is None:  # Stream closed
                yield f"data: {json.dumps({'type': 'completed'})}\n\n"
                break
                
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
```

### 3. Integration in Overlord

```python
# In _process_sync_chat or any processing method
async def _process_sync_chat(self, message, request_id, stream=False, ...):
    # Enable streaming if requested
    if stream:
        streaming.enable(request_id)
    
    # Emit events (no-op if not streaming)
    streaming.stream(request_id, "thinking", "Understanding the request...")
    
    # Normal processing
    analysis = await self.request_analyzer.analyze_request(message)
    streaming.stream(request_id, "analysis", f"Complexity: {analysis.complexity_score}")
    
    # More processing...
    result = await self._execute(...)
    
    # Cleanup
    if stream:
        streaming.disable(request_id)
    
    return result
```

## Event Types

| Event Type | Description | Example Content |
|------------|-------------|-----------------|
| `thinking` | AI's understanding/reasoning | "Understanding the request..." |
| `analysis` | Request analysis results | "Complexity: 7.5" |
| `planning` | Task decomposition | "Breaking into 3 tasks..." |
| `executing` | Current action | "Running web search..." |
| `tool_call` | Tool usage | "Calling sys_info tool" |
| `clarification` | Questions for user | "Which database do you mean?" |
| `content` | Main response content | "Here's the solution..." |
| `artifacts` | File/data artifacts | `{"type": "file", "name": "report.pdf", "data": "..."}` |
| `metadata` | Response metadata | `{"tokens": 1234, "model": "gpt-4"}` |
| `error` | Error information | "Failed to connect to database" |
| `completed` | Stream ended with final status | `{"status": "success", "duration_ms": 2500}` |

## MuxiResponse Streaming

When `stream=True`, the entire MuxiResponse is streamed as events instead of being returned:

```python
# Normal mode (stream=False)
return MuxiResponse(
    content="Here's the solution...",
    artifacts=[...],
    metadata={...}
)

# Streaming mode (stream=True)
streaming.stream(request_id, "content", "Here's the solution...")
streaming.stream(request_id, "artifacts", json.dumps(artifacts))
streaming.stream(request_id, "metadata", json.dumps(metadata))
streaming.stream(request_id, "completed", json.dumps({"status": "success"}))
return MuxiResponse(...)  # Still return for compatibility, but SDK uses events
```

## SDK Integration

The SDK generates the request_id and subscribes BEFORE calling the runtime:

```python
class SDK:
    async def chat_with_streaming(self, message):
        # Generate request_id
        request_id = f"req_{generate_nanoid()}"
        
        # Subscribe first (avoid race condition)
        event_stream = self.subscribe_sse(f"/subscribe/{request_id}")
        
        # Call runtime with streaming enabled
        response = await self.runtime.chat(
            message,
            request_id=request_id,
            stream=True
        )
        
        # Return both events and response
        return {
            "response": response,
            "events": event_stream
        }
```

## Benefits

1. **No breaking changes**: Runtime API remains the same
2. **Clean code**: No generators, no duplicate methods
3. **Zero overhead**: Early return when not streaming
4. **Progressive enhancement**: Streaming is optional
5. **Maintainable**: Single code path for all requests
6. **Scalable**: Fire-and-forget pattern doesn't block

## Migration Path

1. Remove all `_process_*_streaming` methods
2. Add `streaming.py` module
3. Add `streaming.stream()` calls to existing methods
4. Add SSE endpoint to API
5. Update SDK to use new streaming

## Success Criteria

- [ ] Single code path handles both streaming and non-streaming
- [ ] No AsyncGenerator complexity
- [ ] Events emitted in real-time
- [ ] Zero overhead when streaming disabled
- [ ] SDK can subscribe and receive events
- [ ] Clean separation from observability system

## Future Considerations

- WebSocket support (in addition to SSE)
- Event filtering (subscribe to specific event types)
- Rate limiting for streaming endpoints
- Metrics on streaming usage

## Appendix: SDK Streaming Implementation

The SDK handles streaming with a simple 3-step process that avoids blocking on the runtime call:

### Implementation Flow

```python
class MuxiSDK:
    async def chat_streaming(self, message: str, user_id: str, session_id: str):
        """
        Stream chat responses without blocking on the runtime call.
        """
        # Step 1: Generate request_id
        request_id = f"req_{generate_nanoid()}"
        
        # Step 2: Subscribe to SSE endpoint
        # This establishes the subscription BEFORE calling runtime
        event_stream = self._subscribe_sse(f"/subscribe/{request_id}")
        
        # Step 3: Send chat message WITHOUT await
        # Fire and forget - we don't wait for response
        asyncio.create_task(
            self.runtime.chat(
                message=message,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                stream=True
            )
        )
        
        # Return the event stream immediately
        # The client will receive events as they're emitted
        return event_stream
```

### Key Design Points

1. **No Await on Runtime Call**: The runtime call is wrapped in `asyncio.create_task()` so we don't block waiting for the response. The response comes through events instead.

2. **Race Condition Prevention**: By subscribing BEFORE calling the runtime, we ensure we don't miss any early events.

3. **Request ID Generation**: SDK is responsible for generating unique request IDs, giving it control over the streaming lifecycle.

4. **Event Stream Return**: Instead of returning a MuxiResponse, we return the event stream for the client to consume.

### Client Usage Example

```python
# Initialize SDK
sdk = MuxiSDK(runtime_url="http://localhost:8000")

# Stream a chat response
async for event in await sdk.chat_streaming(
    message="Explain quantum computing",
    user_id="user123",
    session_id="session456"
):
    if event['type'] == 'thinking':
        print(f"💭 {event['content']}")
    elif event['type'] == 'content':
        print(event['content'], end='')
    elif event['type'] == 'completed':
        print(f"\n✅ Done in {event['duration_ms']}ms")
        break
```

### Error Handling

```python
async def chat_streaming_with_retry(self, message: str, **kwargs):
    """Enhanced streaming with error recovery."""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            request_id = f"req_{generate_nanoid()}"
            
            # Subscribe with timeout
            event_stream = await asyncio.wait_for(
                self._subscribe_sse(f"/subscribe/{request_id}"),
                timeout=5.0
            )
            
            # Fire runtime call
            asyncio.create_task(
                self.runtime.chat(
                    message=message,
                    request_id=request_id,
                    stream=True,
                    **kwargs
                )
            )
            
            return event_stream
            
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Brief delay before retry
                continue
            raise
```

### Non-Streaming Fallback

For compatibility, the SDK can detect if streaming fails and fall back to regular mode:

```python
async def chat_adaptive(self, message: str, **kwargs):
    """Try streaming first, fall back to regular if unavailable."""
    try:
        # Try streaming
        return await self.chat_streaming(message, **kwargs)
    except StreamingUnavailableError:
        # Fall back to regular chat
        return await self.chat(message, stream=False, **kwargs)
```