# Streaming Events Architecture

## Overview

This PRD describes the new streaming events architecture for MUXI Runtime that replaces the complex AsyncGenerator-based streaming with a clean, observability-style event emission pattern.

## Problem Statement

The current streaming implementation has several issues:
1. ~~Python's limitation: Cannot both `yield` (for streaming) and `return` (for final response) in the same function~~ (Actually, Python 3 CAN have both yield and return, but the new approach is still better)
2. Code duplication: Separate methods for streaming vs non-streaming (`_process_streaming_chat`, `_process_with_workflow_streaming`, etc.)
3. Generator complexity: AsyncGenerators make the code harder to maintain and debug
4. Cannot return `request_id` immediately while also streaming content
5. Tight coupling between streaming logic and transport mechanism (SSE)

## Solution

Implement streaming as a separate event emission system, similar to observability but independent from it. The runtime emits events through a fire-and-forget pattern, and interested clients can subscribe via SSE.

## Architecture

### Core Components

```
Any Module → streaming.stream() → StreamingManager (Event Storage) → Subscribe Function → Multiple Consumers
                                                                              ↓
                                                                    SSE / Direct API / WebSocket
```

### Key Design Decisions

1. **Fire-and-forget pattern**: Uses `@multitasking.task` like observability, no blocking the main execution path
2. **Call from anywhere**: `streaming.stream()` works from any module, just like `observability.observe()`
3. **Owner-based security**: Security validation at subscription time, not emission time
4. **Pure event storage**: Event streams don't track subscribers - clean separation of concerns
5. **Real-time streaming only**: No replay of existing events - connect in time or miss them
6. **Generator-based subscription**: Simple `async for` yielding, no queues or complex async management
7. **Automatic cleanup**: Event streams deleted when request completes/fails/cancelled

## Implementation

### 1. StreamingManager (`src/muxi/services/streaming.py`)

```python
import asyncio
import time
import multitasking
from typing import Dict, Tuple, List, Optional

# Configure multitasking like observability
multitasking.set_engine("thread")

class StreamingManager:
    """Pure event storage with owner-based security"""
    
    def __init__(self):
        # Key: request_id, Value: owner + events
        self.event_streams: Dict[str, Dict] = {}
        
    def enable_streaming(self, request_id: str, user_id: str, session_id: str):
        """Enable streaming with ownership tracking"""
        if request_id not in self.event_streams:
            self.event_streams[request_id] = {
                "owner": (user_id, session_id),
                "events": []
            }
    
    async def emit_event(self, request_id: str, event_type: str, content: str, **metadata):
        """Simple event storage - no subscriber management"""
        if request_id not in self.event_streams:
            return  # Not streaming-enabled
            
        stream_data = self.event_streams[request_id]
        user_id, session_id = stream_data["owner"]
        
        event = {
            "request_id": request_id,
            "user_id": user_id,
            "session_id": session_id,
            "type": event_type,
            "content": content,
            "timestamp": time.time(),
            **metadata
        }
        
        # Just append to events list
        stream_data["events"].append(event)
    
    async def subscribe(self, request_id: str, user_id: str, session_id: str):
        """
        Generator that yields NEW events only.
        Real-time streaming - no replay of existing events.
        """
        # Validate access
        if request_id not in self.event_streams:
            return
        
        stream_data = self.event_streams[request_id]
        if stream_data["owner"] != (user_id, session_id):
            return  # Unauthorized
        
        # Start watching from NOW (ignore existing events)
        last_seen = len(stream_data["events"])
        
        # Yield only NEW events as they arrive
        while request_id in self.event_streams:
            current_events = self.event_streams[request_id]["events"]
            if len(current_events) > last_seen:
                # New events since last check
                for event in current_events[last_seen:]:
                    yield event
                last_seen = len(current_events)
            
            await asyncio.sleep(0.1)  # Brief polling
    
    def disable_streaming(self, request_id: str):
        """Cleanup when request completes"""
        if request_id in self.event_streams:
            del self.event_streams[request_id]

# Global instance
streaming_manager = StreamingManager()

# Fire-and-forget streaming (matches observability pattern)
@multitasking.task
def stream(request_id: str, event_type: str, content: str, **metadata):
    """
    Fire-and-forget streaming emission using multitasking.
    Call from anywhere, just like observability.observe()
    """
    try:
        asyncio.create_task(
            streaming_manager.emit_event(request_id, event_type, content, **metadata)
        )
    except Exception:
        # Silent failure like observability
        pass

# Helper functions
def enable_streaming(request_id: str, user_id: str, session_id: str):
    """Enable streaming for a request"""
    streaming_manager.enable_streaming(request_id, user_id, session_id)

def disable_streaming(request_id: str):
    """Disable streaming and cleanup"""
    streaming_manager.disable_streaming(request_id)

async def subscribe(request_id: str, user_id: str, session_id: str):
    """Subscribe to real-time events"""
    async for event in streaming_manager.subscribe(request_id, user_id, session_id):
        yield event
```

### 2. SSE Endpoint

```python
@app.get("/stream/{user_id}/{session_id}/{request_id}")
async def sse_stream(user_id: str, session_id: str, request_id: str):
    """Server-Sent Events endpoint for real-time streaming with security"""
    
    async def event_generator():
        # Subscribe via overlord interface
        try:
            # Stream events in real-time
            async for event in overlord.stream_request(request_id, user_id, session_id):
                yield f"data: {json.dumps(event)}\n\n"
            
            # Stream completed (request_id deleted)
            yield f"data: {json.dumps({'type': 'stream_completed'})}\n\n"
        except:
            yield f"data: {json.dumps({'error': 'Unauthorized or request not streaming'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
```

### 3. Integration in Overlord (Embedded Streaming)

```python
# Always stream everything - no conditional streaming
async def chat(self, message, user_id, session_id, request_id=None, **kwargs):
    request_id = request_id or generate_nanoid()
    
    # Always enable streaming for every request
    streaming.enable_streaming(request_id, user_id, session_id)
    
    # Emit events throughout normal processing
    streaming.stream(request_id, "thinking", "Understanding the request...")
    
    # Normal processing with embedded streaming calls  
    analysis = await self.request_analyzer.analyze_request(message, user_id)
    streaming.stream(request_id, "analysis", f"Complexity: {analysis.complexity_score}")
    
    # Continue with normal flow
    if analysis.requires_workflow:
        result = await self._process_with_workflow(message, request_id, user_id, session_id, **kwargs)
    else:
        result = await self._handle_simple_request(message, request_id, user_id, session_id, **kwargs)
    
    # Final completion event
    streaming.stream(request_id, "completed", {"status": "success"})
    
    # Always cleanup when done
    streaming.disable_streaming(request_id)
    
    return result

async def stream_request(self, request_id: str, user_id: str, session_id: str):
    """Subscribe to real-time events for a request"""
    async for event in streaming_manager.subscribe(request_id, user_id, session_id):
        yield event
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

## Client Usage Pattern

### Fire-and-Forget + Stream Pattern

```python
# Generate request_id first
request_id = generate_nanoid()

# Fire the chat processing (don't await!) - this starts background execution
asyncio.create_task(
    overlord.chat("Explain quantum computing", user_id, session_id, request_id)
)

# Immediately start consuming real-time events
async for event in overlord.stream_request(request_id, user_id, session_id):
    if event['type'] == 'thinking':
        print(f"💭 {event['content']}")
    elif event['type'] == 'content':
        print(event['content'], end='')
    elif event['type'] == 'completed':
        print(f"\n✅ Done!")
        break
```

### Why asyncio.create_task() is Required

You **cannot** just call an async function without awaiting it:

```python
# ❌ This doesn't work - chat never actually starts!
overlord.chat("Hello", user_id, session_id, request_id)  # Returns unscheduled coroutine

# ✅ This works - schedules chat to run in background
asyncio.create_task(overlord.chat("Hello", user_id, session_id, request_id))
```

Without `create_task()`, the async function just returns a coroutine object that never executes. You need to either:
1. `await` it (blocks until completion)
2. `create_task()` it (starts in background)

Since we want streaming, we use `create_task()` to start processing while immediately consuming events.

## SDK Integration

Since SDK is remote and uses HTTP API only, it will consume streaming via SSE:

```python
class MuxiSDK:
    async def chat_with_streaming(self, message: str, user_id: str, session_id: str):
        """
        Remote SDK streaming via SSE endpoint.
        """
        # Generate request_id
        request_id = f"req_{generate_nanoid()}"
        
        # Start SSE subscription (before making the call to avoid race condition)
        event_stream_url = f"{self.base_url}/stream/{user_id}/{session_id}/{request_id}"
        event_stream = self._create_sse_stream(event_stream_url)
        
        # Call runtime with streaming enabled
        asyncio.create_task(
            self._make_chat_request(
                message=message,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                stream=True
            )
        )
        
        # Return event stream for consumption
        return event_stream
    
    async def _create_sse_stream(self, url: str):
        """Create SSE stream connection"""
        async with httpx.AsyncClient() as client:
            async with client.stream('GET', url) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        event_data = line[6:]  # Remove 'data: ' prefix
                        yield json.loads(event_data)
```

## Benefits

1. **No breaking changes**: Runtime API remains the same
2. **Call from anywhere**: `streaming.stream()` works from any module like `observability.observe()`
3. **Clean separation of concerns**: Event storage separate from subscription/transport
4. **Owner-based security**: Secure multi-user isolation with simple validation
5. **Zero overhead**: Early return when not streaming-enabled
6. **Real-time semantics**: True streaming - connect in time or miss events
7. **Generator simplicity**: No queues, just simple `async for` yielding
8. **Multiple transports**: SSE, WebSocket, Direct API can all consume same event stream
9. **Automatic cleanup**: Event streams deleted when request completes
10. **Consistent pattern**: Matches proven multitasking approach from observability

## Migration Path

1. Add `streaming.py` module with StreamingManager (owner-based event storage)
2. Add `streaming.stream()` calls throughout existing processing methods
3. Add secure SSE endpoint `/stream/{user_id}/{session_id}/{request_id}`
4. Update SDK to consume SSE endpoint for remote streaming
5. Remove all `_process_*_streaming` methods (optional cleanup)

## Success Criteria

- [ ] `streaming.stream()` function works from any module like `observability.observe()`
- [ ] Owner-based security prevents unauthorized access to streams
- [ ] Single code path handles both streaming and non-streaming requests
- [ ] Real-time streaming with no replay of existing events  
- [ ] Zero overhead when streaming not enabled for request
- [ ] SSE endpoint provides secure multi-user streaming
- [ ] Generator-based subscription without complex queue management
- [ ] Automatic cleanup when requests complete
- [ ] Transport-agnostic event storage (SSE, WebSocket, etc. can all consume)
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