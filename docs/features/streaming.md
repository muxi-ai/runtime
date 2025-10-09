# Streaming Responses

MUXI Runtime supports real-time streaming of AI responses using Server-Sent Events (SSE), allowing users to see content as it's generated rather than waiting for the complete response.

## Overview

Streaming provides several key benefits:

- **Real-time Feedback**: Users see content as it's generated
- **Improved UX**: No waiting for long responses to complete
- **Progress Updates**: Status indicators during multi-step operations
- **Interactive Control**: Pause, resume, or stop streaming mid-response
- **Lower Perceived Latency**: Users can start reading immediately

### How It Works

```
User Request → Overlord → LLM (Streaming) → SSE Events → User Interface
                                    ↓
                              Event Stream:
                              - stream_start
                              - stream_chunk (tokens...)
                              - progress_update
                              - stream_end
```

## Configuration

### Formation YAML

Enable streaming in your formation configuration:

```yaml
schema: "1.0.0"
id: "streaming-assistant"
description: "Assistant with streaming enabled"

overlord:
  persona: "You are a helpful assistant"

  # Response configuration
  response:
    format: "markdown"      # Works with all formats
    streaming: true         # Enable streaming (default: true)
    progress: true          # Show progress updates (default: true)
    widgets: true           # Future interactive elements

# LLM configuration for streaming
llm:
  models:
    - streaming: "anthropic/claude-3-5-haiku-latest"
      settings:
        temperature: 0.7
        max_tokens: 4096    # Max tokens per response
        timeout_seconds: 30
        max_retries: 0      # Retries disabled for streaming
```

### Configuration Options

#### `overlord.response.streaming`
- **Type**: `boolean`
- **Default**: `true`
- **Description**: Enable/disable streaming for all synchronous responses

#### `overlord.response.progress`
- **Type**: `boolean`
- **Default**: `true`
- **Description**: Enable progress updates during streaming

#### `llm.models.streaming`
- **Type**: `string`
- **Description**: LLM model to use for streaming responses
- **Examples**: 
  - `"anthropic/claude-3-5-haiku-latest"`
  - `"openai/gpt-4o-mini"`
  - `"openai/gpt-4o"`

## Basic Usage

### Python SDK

```python
from muxi.runtime import Formation

# Load formation
formation = Formation()
await formation.load("formation.yaml")
overlord = await formation.start_overlord()

# Stream a response
async for chunk in overlord.chat_stream(
    message="Explain quantum computing in detail",
    user_id="user_123",
    session_id="session_456"
):
    # chunk is a dict with event data
    if chunk["type"] == "stream_chunk":
        print(chunk["content"], end="", flush=True)
    elif chunk["type"] == "progress":
        print(f"\n[{chunk['status']}]", flush=True)

print("\n\nDone!")
```

### REST API

```bash
# Streaming endpoint
curl -N -H "Content-Type: application/json" \
  -d '{"message": "Explain quantum computing", "user_id": "user123", "stream": true}' \
  http://localhost:8000/api/chat/stream

# Response (Server-Sent Events):
data: {"type": "stream_start", "request_id": "req_abc123"}

data: {"type": "stream_chunk", "content": "Quantum computing is"}

data: {"type": "stream_chunk", "content": " a revolutionary"}

data: {"type": "progress", "status": "Generating response", "progress": 25}

data: {"type": "stream_chunk", "content": " approach to computing..."}

data: {"type": "stream_end", "total_tokens": 150}
```

## Event Types

### Core Streaming Events

#### `stream_start`
Indicates the beginning of a streaming response.

```json
{
  "type": "stream_start",
  "request_id": "req_abc123",
  "timestamp": 1234567890,
  "session_id": "session_456"
}
```

#### `stream_chunk`
Contains content tokens as they're generated.

```json
{
  "type": "stream_chunk",
  "content": "quantum computing is ",
  "timestamp": 1234567891
}
```

**Alternative Event Types for Content:**
- `"text"`: Text content (legacy)
- `"content"`: Direct content streaming
- `"completed"`: Final response with full content

#### `stream_end`
Marks the completion of streaming.

```json
{
  "type": "stream_end",
  "request_id": "req_abc123",
  "timestamp": 1234567900,
  "total_tokens": 150,
  "duration_ms": 10000
}
```

#### `stream_error`
Reports errors during streaming.

```json
{
  "type": "stream_error",
  "request_id": "req_abc123",
  "error": "Rate limit exceeded",
  "code": "RATE_LIMIT_ERROR",
  "recoverable": true
}
```

### Progress Events

#### `progress_update`
Provides status updates during long operations.

```json
{
  "type": "progress",
  "status": "Analyzing request...",
  "progress": 25,
  "timestamp": 1234567895
}
```

#### `status_change`
Indicates state transitions.

```json
{
  "type": "status_change",
  "from": "processing",
  "to": "completed",
  "timestamp": 1234567899
}
```

### Control Events

#### `pause_acknowledged`
Confirms pause request received.

```json
{
  "type": "pause_acknowledged",
  "request_id": "req_abc123",
  "timestamp": 1234567896
}
```

#### `resume_acknowledged`
Confirms resume request received.

```json
{
  "type": "resume_acknowledged",
  "request_id": "req_abc123",
  "timestamp": 1234567897
}
```

#### `stop_acknowledged`
Confirms stop request received.

```json
{
  "type": "stop_acknowledged",
  "request_id": "req_abc123",
  "timestamp": 1234567898,
  "partial_content": "quantum computing is a revol..."
}
```

## Advanced Features

### Stream Interruption

Control streaming mid-response:

```python
# Start streaming
stream = overlord.chat_stream(
    message="Write a comprehensive guide to quantum computing",
    user_id="user_123",
    session_id="session_456"
)

# Consume some events
async for chunk in stream:
    print(chunk["content"], end="")
    
    # Stop after certain condition
    if some_condition:
        await stream.aclose()  # Stop the stream
        break
```

### Progress Tracking

Monitor progress during complex operations:

```python
progress_updates = []

async for chunk in overlord.chat_stream(message="Complex task"):
    if chunk["type"] == "progress":
        progress_updates.append({
            "status": chunk["status"],
            "progress": chunk.get("progress", 0),
            "timestamp": chunk["timestamp"]
        })
        print(f"Progress: {chunk['status']} ({chunk.get('progress', 0)}%)")
    elif chunk["type"] == "stream_chunk":
        print(chunk["content"], end="")
```

### Content Extraction

Extract complete content from stream:

```python
async def collect_stream_content(stream):
    """Collect all content from a stream."""
    content_parts = []
    
    async for chunk in stream:
        # Content can come in multiple event types
        if chunk["type"] in ("content", "text", "stream_chunk"):
            content = chunk.get("content") or chunk.get("text", "")
            content_parts.append(content)
        elif chunk["type"] == "completed":
            # Final event may contain full content
            final_content = chunk.get("content", "")
            if final_content:
                content_parts.append(final_content)
    
    return "".join(content_parts)

# Usage
content = await collect_stream_content(
    overlord.chat_stream(message="Explain quantum computing")
)
print(f"Complete response: {content}")
```

### Error Handling

Handle streaming errors gracefully:

```python
try:
    async for chunk in overlord.chat_stream(message="Generate report"):
        if chunk["type"] == "stream_error":
            error_code = chunk.get("code")
            error_msg = chunk.get("error")
            recoverable = chunk.get("recoverable", False)
            
            if recoverable:
                print(f"Warning: {error_msg} (continuing...)")
            else:
                print(f"Fatal error: {error_msg}")
                break
        elif chunk["type"] == "stream_chunk":
            print(chunk["content"], end="")
            
except asyncio.TimeoutError:
    print("Stream timed out")
except Exception as e:
    print(f"Stream error: {e}")
```

## Integration Patterns

### Web Application (SSE)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()

@app.post("/chat/stream")
async def chat_stream(message: str, user_id: str):
    """Stream chat responses using Server-Sent Events."""
    
    async def event_generator():
        async for chunk in overlord.chat_stream(
            message=message,
            user_id=user_id,
            session_id=f"web_{user_id}"
        ):
            # Format as SSE
            yield f"data: {json.dumps(chunk)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

**Client-side (JavaScript):**

```javascript
const eventSource = new EventSource('/chat/stream?message=Hello&user_id=123');

eventSource.onmessage = (event) => {
    const chunk = JSON.parse(event.data);
    
    if (chunk.type === 'stream_chunk') {
        document.getElementById('response').textContent += chunk.content;
    } else if (chunk.type === 'progress') {
        document.getElementById('status').textContent = chunk.status;
    } else if (chunk.type === 'stream_end') {
        eventSource.close();
    }
};

eventSource.onerror = (error) => {
    console.error('Stream error:', error);
    eventSource.close();
};
```

### CLI Tool

```python
import click
import asyncio

@click.command()
@click.argument('question')
async def ask(question: str):
    """Ask a question with streaming response."""
    formation = Formation()
    await formation.load("formation.yaml")
    overlord = await formation.start_overlord()
    
    # Stream to terminal
    async for chunk in overlord.chat_stream(
        message=question,
        user_id="cli_user"
    ):
        if chunk["type"] in ("stream_chunk", "content", "text"):
            content = chunk.get("content") or chunk.get("text", "")
            click.echo(content, nl=False)
        elif chunk["type"] == "progress":
            # Show progress in status line
            click.echo(f"\n[{chunk['status']}]", err=True)
    
    click.echo("\n")  # Final newline
    await formation.stop_overlord()

if __name__ == "__main__":
    asyncio.run(ask())
```

### React Application

```typescript
import { useState, useEffect } from 'react';

function StreamingChat() {
  const [content, setContent] = useState('');
  const [status, setStatus] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  const askQuestion = async (question: string) => {
    setIsStreaming(true);
    setContent('');

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: question, user_id: 'user123' })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));

          if (data.type === 'stream_chunk') {
            setContent(prev => prev + data.content);
          } else if (data.type === 'progress') {
            setStatus(data.status);
          } else if (data.type === 'stream_end') {
            setIsStreaming(false);
            setStatus('Complete');
          }
        }
      }
    }
  };

  return (
    <div>
      <div className="status">{status}</div>
      <div className="content">{content}</div>
      <button 
        onClick={() => askQuestion('Explain quantum computing')}
        disabled={isStreaming}
      >
        Ask Question
      </button>
    </div>
  );
}
```

## Format Compatibility

Streaming works with all response formats:

### Markdown Streaming

```yaml
overlord:
  response:
    format: "markdown"
    streaming: true
```

**Output:**
```
# Quantum Computing

Quantum computing is...

## Key Principles
- **Superposition**: ...
- **Entanglement**: ...
```

### JSON Streaming

```yaml
overlord:
  response:
    format: "json"
    streaming: true
```

**Output (streamed as JSON chunks):**
```json
{"type": "stream_chunk", "content": "{\"explanation\": \"Quantum"}
{"type": "stream_chunk", "content": " computing is..."}
```

### HTML Streaming

```yaml
overlord:
  response:
    format: "html"
    streaming: true
```

**Output:**
```html
<h1>Quantum Computing</h1>
<p>Quantum computing is a revolutionary...
```

### Plain Text Streaming

```yaml
overlord:
  response:
    format: "text"
    streaming: true
```

**Output:**
```
Quantum computing is a revolutionary approach...
```

## Performance Characteristics

### Timing Metrics (from e2e tests)

- **First Chunk Latency**: ~1-2 seconds
- **Chunk Interval**: ~0.1-0.5 seconds
- **Total Duration**: Depends on response length
- **Average Throughput**: ~20-50 tokens/second

### Token Streaming

```python
# Analyze streaming performance
timings = []
start_time = time.time()

async for chunk in overlord.chat_stream(message="Long explanation"):
    if chunk["type"] == "stream_chunk":
        elapsed = time.time() - start_time
        timings.append(elapsed)
        token_count = len(chunk["content"].split())
        print(f"Chunk at {elapsed:.2f}s: {token_count} tokens")

# Calculate metrics
avg_interval = sum(timings[i+1] - timings[i] for i in range(len(timings)-1)) / (len(timings)-1)
print(f"Average chunk interval: {avg_interval:.3f}s")
```

### Expected Performance

From e2e test benchmarks:
- **Simple queries**: 5-10 second total duration
- **Complex queries**: 20-30 second total duration
- **Multi-step operations**: 30-60 second duration with progress updates

## Best Practices

### 1. Always Handle All Event Types

```python
# ❌ Wrong: Only handling stream_chunk
async for chunk in stream:
    print(chunk["content"])  # May fail on other event types

# ✅ Correct: Handle all event types
async for chunk in stream:
    event_type = chunk.get("type", "unknown")
    
    if event_type in ("stream_chunk", "content", "text"):
        content = chunk.get("content") or chunk.get("text", "")
        print(content, end="")
    elif event_type == "progress":
        print(f"\n[{chunk['status']}]")
    elif event_type == "stream_error":
        print(f"\nError: {chunk['error']}")
        break
```

### 2. Use Timeouts

```python
# ❌ Wrong: No timeout
async for chunk in overlord.chat_stream(message="Long task"):
    process(chunk)

# ✅ Correct: With timeout
try:
    async with asyncio.timeout(60.0):  # 60 second timeout
        async for chunk in overlord.chat_stream(message="Long task"):
            process(chunk)
except asyncio.TimeoutError:
    print("Stream timed out")
```

### 3. Buffer Content Appropriately

```python
# ✅ Good: Collect content efficiently
content_buffer = []

async for chunk in stream:
    if chunk["type"] in ("stream_chunk", "content", "text"):
        content = chunk.get("content") or chunk.get("text", "")
        content_buffer.append(content)
        
        # Flush buffer periodically (every 10 chunks)
        if len(content_buffer) >= 10:
            full_content = "".join(content_buffer)
            process(full_content)
            content_buffer = []

# Process remaining content
if content_buffer:
    full_content = "".join(content_buffer)
    process(full_content)
```

### 4. Clean Up Resources

```python
# ✅ Good: Proper cleanup
stream = None
try:
    stream = overlord.chat_stream(message="Question")
    async for chunk in stream:
        process(chunk)
finally:
    if stream:
        await stream.aclose()  # Always close stream
```

### 5. Monitor Progress for Long Operations

```python
# ✅ Good: Show progress to users
last_progress = 0

async for chunk in overlord.chat_stream(message="Complex analysis"):
    if chunk["type"] == "progress":
        progress = chunk.get("progress", 0)
        if progress > last_progress:
            print(f"Progress: {progress}%")
            last_progress = progress
    elif chunk["type"] == "stream_chunk":
        print(chunk["content"], end="")
```

## Troubleshooting

See [Streaming Troubleshooting Guide](streaming-troubleshooting.md) for detailed troubleshooting information.

### Quick Diagnostics

```python
async def diagnose_streaming():
    """Diagnose streaming issues."""
    formation = Formation()
    await formation.load("formation.yaml")
    overlord = await formation.start_overlord()
    
    # Check configuration
    print(f"Streaming enabled: {overlord.response.streaming}")
    print(f"Progress enabled: {overlord.response.progress}")
    
    # Test basic streaming
    event_count = 0
    content_count = 0
    
    async for chunk in overlord.chat_stream(
        message="Test message",
        user_id="test"
    ):
        event_count += 1
        if chunk.get("type") in ("stream_chunk", "content", "text"):
            content_count += 1
        print(f"Event {event_count}: {chunk.get('type')}")
    
    print(f"\nTotal events: {event_count}")
    print(f"Content events: {content_count}")
    
    if content_count == 0:
        print("❌ No content events received!")
    else:
        print("✅ Streaming working")
    
    await formation.stop_overlord()
```

## Related Documentation

- **[Quick Start Guide](streaming-quickstart.md)** - 5-minute guide to streaming
- **[Troubleshooting Guide](streaming-troubleshooting.md)** - Common issues and solutions
- **[Response Formats](response-formats.md)** - Format compatibility with streaming
- **[Observability](../observability.md)** - Event monitoring and logging
- **[E2E Tests](../../e2e/tests/10_streaming/)** - Working code examples

## Conclusion

Streaming responses provide a superior user experience for AI interactions by delivering content in real-time. MUXI Runtime's streaming implementation is production-ready with comprehensive event types, progress tracking, and format compatibility.

Choose streaming for:
- Interactive chat interfaces
- Long-form content generation
- Multi-step operations
- User-facing applications

Use synchronous responses for:
- API integrations requiring complete responses
- Batch processing
- Operations where streaming overhead isn't justified
