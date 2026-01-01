# Streaming - Quick Start Guide

Get started with MUXI Runtime streaming in 5 minutes.

## 1-Minute Quick Start

### Enable Streaming

**formation.afs:**
```yaml
overlord:
  response:
    streaming: true  # Enable streaming
    progress: true   # Show progress updates
```

### Stream a Response

```python
from muxi.runtime import Formation

formation = Formation()
await formation.load("formation.afs")
overlord = await formation.start_overlord()

# Stream tokens as they arrive
async for chunk in overlord.chat_stream(
    message="Explain quantum computing",
    user_id="user_123"
):
    if chunk["type"] == "stream_chunk":
        print(chunk["content"], end="", flush=True)
```

**That's it!** You're streaming AI responses.

## Common Use Cases

### CLI Application

```python
import asyncio
from muxi.runtime import Formation

async def stream_to_terminal(question: str):
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    async for chunk in overlord.chat_stream(message=question, user_id="cli"):
        if chunk["type"] in ("stream_chunk", "content", "text"):
            content = chunk.get("content") or chunk.get("text", "")
            print(content, end="", flush=True)

    print()  # Final newline
    await formation.stop_overlord()

# Run it
asyncio.run(stream_to_terminal("What is AI?"))
```

### Web API (FastAPI)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()
overlord = None  # Initialize in startup

@app.post("/chat/stream")
async def stream_chat(message: str, user_id: str):
    async def event_stream():
        async for chunk in overlord.chat_stream(message=message, user_id=user_id):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**Client:**
```javascript
const eventSource = new EventSource('/chat/stream?message=Hello&user_id=123');

eventSource.onmessage = (event) => {
    const chunk = JSON.parse(event.data);
    if (chunk.type === 'stream_chunk') {
        document.getElementById('response').textContent += chunk.content;
    }
};
```

### React/TypeScript

```typescript
import { useState } from 'react';

function StreamingChat() {
  const [content, setContent] = useState('');

  const sendMessage = async (message: string) => {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      body: JSON.stringify({ message, user_id: 'user123' })
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'stream_chunk') {
            setContent(prev => prev + data.content);
          }
        }
      }
    }
  };

  return (
    <div>
      <div>{content}</div>
      <button onClick={() => sendMessage('Hello')}>Send</button>
    </div>
  );
}
```

## Event Types Reference

### Content Events

```python
# Stream chunk - content as it arrives
{"type": "stream_chunk", "content": "quantum computing "}

# Alternative content events
{"type": "text", "text": "is revolutionary"}
{"type": "content", "content": "technology"}

# Completed - final event with full response
{"type": "completed", "content": "full response text..."}
```

### Progress Events

```python
# Progress update
{"type": "progress", "status": "Analyzing...", "progress": 25}

# Status change
{"type": "status_change", "from": "processing", "to": "completed"}
```

### Control Events

```python
# Stream lifecycle
{"type": "stream_start", "request_id": "req_123"}
{"type": "stream_end", "total_tokens": 150}

# Errors
{"type": "stream_error", "error": "Rate limit", "recoverable": true}
```

## Handling Events

### Basic Handler

```python
async for chunk in overlord.chat_stream(message="Question"):
    event_type = chunk.get("type")

    if event_type == "stream_chunk":
        print(chunk["content"], end="")
    elif event_type == "progress":
        print(f"\n[{chunk['status']}]")
    elif event_type == "stream_error":
        print(f"\nError: {chunk['error']}")
```

### Complete Handler

```python
async def handle_stream(stream):
    """Handle all event types properly."""
    content_parts = []

    async for chunk in stream:
        event_type = chunk.get("type", "unknown")

        # Content events
        if event_type in ("stream_chunk", "content", "text"):
            content = chunk.get("content") or chunk.get("text", "")
            content_parts.append(content)
            print(content, end="", flush=True)

        # Progress events
        elif event_type == "progress":
            status = chunk.get("status", "Processing...")
            progress = chunk.get("progress", 0)
            print(f"\n[{status}] {progress}%", flush=True)

        # Final event
        elif event_type == "completed":
            final = chunk.get("content", "")
            if final and not content_parts:
                # Some models return full content in completed event
                content_parts.append(final)

        # Error handling
        elif event_type == "stream_error":
            error = chunk.get("error", "Unknown error")
            recoverable = chunk.get("recoverable", False)
            if not recoverable:
                raise Exception(f"Streaming error: {error}")
            print(f"\nWarning: {error}", flush=True)

    return "".join(content_parts)
```

## Configuration Examples

### Maximum Streaming Performance

```yaml
overlord:
  response:
    streaming: true
    progress: false  # Disable progress for max speed

llm:
  models:
    - streaming: "anthropic/claude-3-5-haiku-latest"
      settings:
        temperature: 0.7
        max_tokens: 4096
        max_retries: 0  # No retries for streaming
```

### Rich Progress Updates

```yaml
overlord:
  response:
    streaming: true
    progress: true  # Enable progress updates

  workflow:
    auto_decomposition: true  # Progress for multi-step tasks
```

### Format-Specific Streaming

```yaml
overlord:
  response:
    streaming: true
    format: "markdown"  # Stream markdown content
```

**JSON streaming:**
```yaml
overlord:
  response:
    streaming: true
    format: "json"  # Stream JSON (wrapped at end)
```

**HTML streaming:**
```yaml
overlord:
  response:
    streaming: true
    format: "html"  # Stream HTML tags
```

## Testing Streaming

### Quick Test

```python
async def test_streaming():
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    # Count events
    events = []
    async for chunk in overlord.chat_stream(
        message="Count to 5",
        user_id="test"
    ):
        events.append(chunk)
        print(f"{chunk.get('type')}: {chunk.get('content', '')[:20]}")

    print(f"\nTotal events: {len(events)}")
    content_events = [e for e in events if e.get("type") in ("stream_chunk", "content", "text")]
    print(f"Content events: {len(content_events)}")

    if content_events:
        print("✅ Streaming working!")
    else:
        print("❌ No content received")

    await formation.stop_overlord()
```

### Performance Test

```python
import time

async def benchmark_streaming():
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    start = time.time()
    first_chunk = None
    last_chunk = None
    chunks = 0

    async for chunk in overlord.chat_stream(
        message="Explain quantum computing in detail",
        user_id="bench"
    ):
        if chunk.get("type") in ("stream_chunk", "content", "text"):
            chunks += 1
            if first_chunk is None:
                first_chunk = time.time()
            last_chunk = time.time()

    total_time = time.time() - start
    first_chunk_latency = first_chunk - start if first_chunk else 0

    print(f"Total time: {total_time:.2f}s")
    print(f"First chunk latency: {first_chunk_latency:.2f}s")
    print(f"Total chunks: {chunks}")
    print(f"Avg chunk interval: {(last_chunk - first_chunk) / chunks:.3f}s")

    await formation.stop_overlord()
```

## Common Patterns

### Collect Full Content

```python
async def get_full_response(message: str) -> str:
    """Collect complete response from stream."""
    content = []

    async for chunk in overlord.chat_stream(message=message, user_id="user"):
        if chunk.get("type") in ("stream_chunk", "content", "text"):
            content.append(chunk.get("content") or chunk.get("text", ""))

    return "".join(content)

# Usage
response = await get_full_response("What is AI?")
print(response)
```

### Progress Bar

```python
from tqdm import tqdm

async def stream_with_progress(message: str):
    """Stream with progress bar."""
    pbar = None

    async for chunk in overlord.chat_stream(message=message, user_id="user"):
        if chunk.get("type") == "progress":
            progress = chunk.get("progress", 0)
            if pbar is None:
                pbar = tqdm(total=100, desc="Processing")
            pbar.update(progress - pbar.n)
        elif chunk.get("type") in ("stream_chunk", "content"):
            if pbar:
                pbar.close()
                pbar = None
            print(chunk.get("content", ""), end="")

    if pbar:
        pbar.close()
```

### Timeout Handling

```python
import asyncio

async def stream_with_timeout(message: str, timeout: float = 30.0):
    """Stream with timeout."""
    try:
        async with asyncio.timeout(timeout):
            async for chunk in overlord.chat_stream(message=message, user_id="user"):
                if chunk.get("type") in ("stream_chunk", "content"):
                    print(chunk.get("content", ""), end="")
    except asyncio.TimeoutError:
        print(f"\nStream timed out after {timeout}s")
```

## Troubleshooting

### No Events Received

```python
# Check configuration
print(f"Streaming enabled: {overlord.response.streaming}")

# Check stream is actually streaming
stream = overlord.chat_stream(message="Test", user_id="test")
print(f"Stream type: {type(stream)}")

# Consume with debugging
async for chunk in stream:
    print(f"Received: {chunk}")  # Should see events
```

### Missing Content

```python
# Handle ALL content event types
async for chunk in stream:
    event_type = chunk.get("type")

    # Check all possible content events
    if event_type in ("stream_chunk", "content", "text", "completed"):
        content = chunk.get("content") or chunk.get("text", "")
        if content:
            print(content, end="")
```

### Slow Streaming

```python
# Check model configuration
# Some models stream faster than others
llm:
  models:
    - streaming: "anthropic/claude-3-5-haiku-latest"  # Fast
    # vs
    - streaming: "openai/gpt-4o"  # Slower but higher quality
```

## Next Steps

- **[Full Documentation](streaming.md)** - Complete streaming guide
- **[Troubleshooting](streaming-troubleshooting.md)** - Detailed problem solving
- **[Response Formats](response-formats.md)** - Format compatibility
- **[E2E Tests](../../e2e/tests/10_streaming/)** - Working examples

## Quick Reference

### Minimal Example
```python
async for chunk in overlord.chat_stream(message="Hi", user_id="user"):
    if chunk["type"] == "stream_chunk":
        print(chunk["content"], end="")
```

### Production Example
```python
async for chunk in overlord.chat_stream(message=msg, user_id=uid):
    t = chunk.get("type")
    if t in ("stream_chunk", "content", "text"):
        print(chunk.get("content") or chunk.get("text", ""), end="")
    elif t == "progress":
        print(f"\n[{chunk['status']}]")
    elif t == "stream_error" and not chunk.get("recoverable"):
        raise Exception(chunk["error"])
```

### Enable Streaming
```yaml
overlord:
  response:
    streaming: true  # That's it!
```
