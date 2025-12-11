# Streaming - Troubleshooting Guide

Common issues and solutions when working with MUXI Runtime streaming, based on real-world issues from e2e tests and production deployments.

## No Content Received

### Issue: Stream Events But No Content

**Symptoms:**
```python
async for chunk in overlord.chat_stream(message="Question"):
    print(chunk)
    # Prints: {"type": "progress", "status": "Processing..."}
    # Prints: {"type": "completed", "content": "The answer is..."}
    # But content extraction returns empty string
```

**Root Cause:**
The `"completed"` event contains the final response content, but code only checks for `"content"` or `"text"` event types.

**Diagnosis:**
```python
content_events = []
all_events = []

async for chunk in overlord.chat_stream(message="Test"):
    all_events.append(chunk)
    if chunk.get("type") in ("content", "text"):
        content_events.append(chunk)
    print(f"Event: {chunk.get('type')} - Has content: {'content' in chunk}")

print(f"Total events: {len(all_events)}")
print(f"Content events (old way): {len(content_events)}")

# Check for completed events
completed_events = [e for e in all_events if e.get("type") == "completed"]
print(f"Completed events: {len(completed_events)}")
if completed_events:
    print(f"Completed content length: {len(completed_events[0].get('content', ''))}")
```

**Solution:**
```python
# ❌ Wrong: Only checks "content" and "text" types
async for chunk in stream:
    if chunk.get("type") in ("content", "text"):
        print(chunk["content"])

# ✅ Correct: Include "completed" event type
async for chunk in stream:
    if chunk.get("type") in ("content", "text", "completed", "stream_chunk"):
        content = chunk.get("content") or chunk.get("text", "")
        if content:
            print(content, end="")
```

**Why This Happens:**
MUXI Runtime can stream content in multiple event types:
- `"stream_chunk"`: Real-time token streaming
- `"content"`: Direct content events
- `"text"`: Text content events  
- `"completed"`: Final event with complete response (IMPORTANT!)

The `"completed"` event often contains the full LLM response.

---

## Slow Streaming Performance

### Issue: Events Take 10+ Seconds Each

**Symptoms:**
- First event arrives quickly (~1-2s)
- Subsequent events take 10-15 seconds each
- Total stream duration very long

**Diagnosis:**
```python
import time

event_times = []
start = time.time()

async for chunk in overlord.chat_stream(message="Question"):
    event_times.append(time.time() - start)
    print(f"Event {len(event_times)} at {event_times[-1]:.2f}s: {chunk.get('type')}")

# Analyze intervals
intervals = [event_times[i+1] - event_times[i] for i in range(len(event_times)-1)]
avg_interval = sum(intervals) / len(intervals) if intervals else 0
print(f"\nAverage interval: {avg_interval:.2f}s")
print(f"Max interval: {max(intervals):.2f}s" if intervals else "N/A")
```

**Expected Performance (from e2e tests):**
- **Normal**: 0.1-0.5 second intervals between chunks
- **Slow**: 5-15 second intervals (planning/thinking events)
- **Very Slow**: 30+ seconds (complex workflow operations)

**Common Causes:**

#### 1. Workflow Decomposition Overhead
```yaml
# Configuration may be triggering workflows
overlord:
  workflow:
    auto_decomposition: true
    complexity_threshold: 4.0  # Too low - triggers for simple queries
```

**Solution:**
```yaml
overlord:
  workflow:
    auto_decomposition: true
    complexity_threshold: 8.0  # Higher threshold for complex tasks only
```

#### 2. Progress Events vs Content Events
```python
# Slow events are often progress/meta events, not content
async for chunk in stream:
    event_type = chunk.get("type")
    print(f"{event_type}: ", end="")
    
    if event_type in ("progress", "thinking", "planning"):
        print("(meta event - expect delay)")
    elif event_type in ("content", "text", "stream_chunk"):
        print("(content event - should be fast)")
```

**Meta Events** (slower):
- `progress`: Status updates
- `thinking`: Reasoning steps
- `planning`: Agent coordination
- Can take 5-15 seconds each

**Content Events** (faster):
- `stream_chunk`: Real-time tokens
- `content`: Direct content
- `text`: Text content
- Should arrive every 0.1-0.5 seconds

#### 3. LLM Model Speed
```yaml
# Slower model
llm:
  models:
    - streaming: "openai/gpt-4o"  # High quality but slower

# Faster model
llm:
  models:
    - streaming: "anthropic/claude-3-5-haiku-latest"  # Faster streaming
```

**Solution:**
Choose faster models for streaming if speed is critical.

---

## No Streaming (Batch Response)

### Issue: Getting Complete Response Instead of Stream

**Symptoms:**
```python
# Expected: Multiple chunks
# Actual: Single complete response
async for chunk in overlord.chat_stream(message="Question"):
    print("Got chunk!")  # Only prints once
```

**Diagnosis:**
```python
# Check configuration
print(f"Streaming enabled: {overlord.response.streaming}")

# Check response
chunks = []
async for chunk in overlord.chat_stream(message="Test"):
    chunks.append(chunk)

print(f"Total chunks: {len(chunks)}")
if len(chunks) == 1:
    print("❌ Getting batch response, not streaming")
else:
    print("✅ Streaming working")
```

**Common Causes:**

#### 1. Streaming Disabled in Formation
```yaml
# ❌ Wrong: Streaming disabled
overlord:
  response:
    streaming: false

# ✅ Correct: Streaming enabled
overlord:
  response:
    streaming: true
```

#### 2. Using Wrong Method
```python
# ❌ Wrong: Using sync method (no streaming)
response = await overlord.chat(message="Question")
print(response.content)  # Complete response

# ✅ Correct: Using stream method
async for chunk in overlord.chat_stream(message="Question"):
    print(chunk["content"], end="")
```

#### 3. Model Doesn't Support Streaming
Some LLM models don't support streaming. Check model configuration:

```yaml
llm:
  models:
    - streaming: "model/that-supports-streaming"
      # NOT all models support streaming
```

---

## Stream Timeout

### Issue: Stream Times Out Before Completion

**Symptoms:**
```
asyncio.TimeoutError: Stream timed out after 30s
```

**Diagnosis:**
```python
import time

start = time.time()

try:
    async with asyncio.timeout(30.0):
        async for chunk in overlord.chat_stream(message="Long task"):
            elapsed = time.time() - start
            print(f"[{elapsed:.1f}s] {chunk.get('type')}")
except asyncio.TimeoutError:
    print(f"Timeout after {time.time() - start:.1f}s")
```

**Solutions:**

#### 1. Increase Timeout
```python
# ❌ Wrong: Too short timeout
async with asyncio.timeout(30.0):
    async for chunk in stream:
        process(chunk)

# ✅ Correct: Longer timeout for complex tasks
async with asyncio.timeout(120.0):  # 2 minutes
    async for chunk in stream:
        process(chunk)
```

#### 2. No Timeout for Long Operations
```python
# For very long operations, don't use timeout
async for chunk in overlord.chat_stream(message="Complex analysis"):
    # Will run until completion
    process(chunk)
```

#### 3. Check Model Timeout Settings
```yaml
llm:
  models:
    - streaming: "anthropic/claude-3-5-haiku-latest"
      settings:
        timeout_seconds: 60  # Increase model timeout
```

---

## Missing Progress Updates

### Issue: No Progress Events During Long Operations

**Symptoms:**
- Stream appears stuck
- No status updates
- Only final completed event

**Diagnosis:**
```python
progress_events = []

async for chunk in overlord.chat_stream(message="Complex task"):
    if chunk.get("type") == "progress":
        progress_events.append(chunk)
        print(f"Progress: {chunk.get('status')}")

print(f"Total progress events: {len(progress_events)}")
```

**Solution:**

#### 1. Enable Progress in Formation
```yaml
# ❌ Wrong: Progress disabled
overlord:
  response:
    streaming: true
    progress: false

# ✅ Correct: Progress enabled
overlord:
  response:
    streaming: true
    progress: true
```

#### 2. Simple Tasks Don't Emit Progress
Progress events are primarily for multi-step workflows:

```python
# Simple query - unlikely to have progress events
"What is 2+2?"

# Complex task - will have progress events
"Analyze this 50-page document and create a comprehensive summary"
```

#### 3. Workflow Required for Progress
```yaml
overlord:
  workflow:
    auto_decomposition: true  # Enable for progress tracking
```

---

## Event Type Confusion

### Issue: Getting Unexpected Event Types

**Symptoms:**
```python
# Expected: "stream_chunk"
# Actual: "progress", "thinking", "planning", "completed"
```

**Understanding Event Types:**

#### Meta Events (Workflow/Process)
- `progress`: Status updates
- `thinking`: Internal reasoning
- `planning`: Agent coordination
- `status_change`: State transitions

#### Content Events (Actual Response)
- `stream_chunk`: Real-time tokens
- `content`: Content streaming
- `text`: Text content
- `completed`: Final response (contains full content)

#### Control Events
- `stream_start`: Stream beginning
- `stream_end`: Stream completion
- `stream_error`: Error occurred
- `pause_acknowledged`: Pause confirmed
- `resume_acknowledged`: Resume confirmed
- `stop_acknowledged`: Stop confirmed

**Solution:**
Handle all event types appropriately:

```python
async for chunk in stream:
    event_type = chunk.get("type", "unknown")
    
    # Content events - display to user
    if event_type in ("stream_chunk", "content", "text", "completed"):
        content = chunk.get("content") or chunk.get("text", "")
        if content:
            print(content, end="")
    
    # Progress events - show status
    elif event_type in ("progress", "thinking", "planning"):
        status = chunk.get("status") or chunk.get("content", "")
        print(f"\n[{status}]", flush=True)
    
    # Control events - handle accordingly
    elif event_type == "stream_error":
        handle_error(chunk)
    elif event_type == "stream_end":
        print("\nComplete!")
    
    # Unknown events - log for debugging
    else:
        print(f"\nUnknown event: {event_type}", flush=True)
```

---

## API Connection Issues

### Issue: Streaming Fails with API Errors

**Symptoms:**
```
Stream error: Anthropic API authentication failed
Circuit breaker triggered
Falling back to OpenAI
```

**Diagnosis:**
```python
# Check event stream for errors
errors = []

async for chunk in overlord.chat_stream(message="Test"):
    if chunk.get("type") == "stream_error":
        errors.append(chunk)
        print(f"Error: {chunk.get('error')}")
        print(f"Recoverable: {chunk.get('recoverable')}")

print(f"Total errors: {len(errors)}")
```

**Common Causes:**

#### 1. Invalid API Keys
```yaml
# Check API key configuration
llm:
  api_keys:
    anthropic: "${{ secrets.ANTHROPIC_API_KEY }}"  # Is this set?
```

**Solution:**
```bash
# Verify secrets file
cat formation-dir/secrets.enc  # Should exist
cat formation-dir/.key          # Should exist

# Check if decryption works
python -c "from muxi.runtime import Formation; f = Formation(); f.load('formation.yaml')"
```

#### 2. Rate Limiting
```python
# Stream error: Rate limit exceeded
# Solution: Use fallback model or retry with backoff
```

```yaml
llm:
  models:
    - streaming: "anthropic/claude-3-5-haiku-latest"
      settings:
        max_retries: 0  # Disable retries for streaming (default)
        fallback_model: "openai/gpt-4o-mini"  # Fallback on error
```

#### 3. Circuit Breaker Triggered
Multiple failures trigger circuit breaker:

```python
# Look for circuit breaker events in logs
# Circuit breaker triggered after 3 failures
# Automatic recovery after timeout
```

**Solution:**
Wait for circuit breaker to reset (usually 60 seconds) or restart formation.

---

## Memory/Resource Issues

### Issue: Stream Consumes Too Much Memory

**Symptoms:**
- Memory usage grows during streaming
- Out of memory errors
- Slow performance

**Diagnosis:**
```python
import psutil
import os

process = psutil.Process(os.getpid())

memory_samples = []

async for chunk in overlord.chat_stream(message="Long response"):
    mem = process.memory_info().rss / 1024 / 1024  # MB
    memory_samples.append(mem)
    
    if len(memory_samples) % 10 == 0:
        print(f"Memory: {mem:.1f} MB")

print(f"Peak memory: {max(memory_samples):.1f} MB")
print(f"Memory growth: {memory_samples[-1] - memory_samples[0]:.1f} MB")
```

**Solutions:**

#### 1. Don't Buffer Entire Response
```python
# ❌ Wrong: Buffering everything
all_content = []
async for chunk in stream:
    all_content.append(chunk)  # Memory grows unbounded

# ✅ Correct: Process and discard
async for chunk in stream:
    process_chunk(chunk)  # Process immediately
    # Don't store unless needed
```

#### 2. Limit Stream Duration
```python
# Limit number of events
max_events = 100
event_count = 0

async for chunk in stream:
    event_count += 1
    if event_count >= max_events:
        await stream.aclose()
        break
```

#### 3. Use Event Streaming to External System
Instead of buffering in memory, stream directly to output:

```python
# Stream to file
with open("response.txt", "w") as f:
    async for chunk in stream:
        if chunk.get("type") in ("content", "text", "stream_chunk"):
            f.write(chunk.get("content", ""))
            f.flush()
```

---

## Database Warnings (Non-Blocking)

### Issue: PostgreSQL Warnings During Streaming

**Symptoms:**
```
WARNING: Failed to create pgvector extension
WARNING: role "ran" does not exist
```

**Impact:**
These are **non-blocking warnings**. Streaming continues normally using local memory mode.

**Diagnosis:**
```python
# Check if warnings affect functionality
try:
    content = []
    async for chunk in overlord.chat_stream(message="Test"):
        if chunk.get("type") in ("content", "text", "completed"):
            content.append(chunk.get("content", ""))
    
    if content:
        print("✅ Streaming works despite database warnings")
    else:
        print("❌ Streaming affected by database issues")
except Exception as e:
    print(f"❌ Database issues blocking streaming: {e}")
```

**Solution:**
Database warnings can be safely ignored for streaming tests. The system falls back to local memory mode automatically.

To fix permanently:
```yaml
# Disable persistent memory if not needed
memory:
  persistent:
    enabled: false  # Use local memory only
```

Or configure PostgreSQL properly:
```bash
# Create the role
createuser -s ran

# Or use different connection string
# formation.afs (or .yaml):
memory:
  persistent:
    connection_string: "${{ secrets.POSTGRES_URI }}"
```

---

## Debugging Strategies

### Enable Debug Logging

```python
import logging

# See all streaming events
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(message)s'
)

async for chunk in overlord.chat_stream(message="Test"):
    # Check logs for detailed event processing
    print(chunk)
```

### Comprehensive Diagnostic Script

```python
async def diagnose_streaming_issues():
    """Comprehensive streaming diagnostics."""
    from muxi.runtime import Formation
    import time
    
    print("=== Streaming Diagnostics ===\n")
    
    # 1. Check configuration
    formation = Formation()
    await formation.load("formation.yaml")
    overlord = await formation.start_overlord()
    
    print(f"✓ Formation loaded")
    print(f"✓ Streaming enabled: {overlord.response.streaming}")
    print(f"✓ Progress enabled: {overlord.response.progress}")
    
    # 2. Test basic streaming
    print("\n=== Basic Stream Test ===")
    events = []
    start = time.time()
    
    try:
        async with asyncio.timeout(30.0):
            async for chunk in overlord.chat_stream(
                message="Count to 3",
                user_id="diagnostic"
            ):
                events.append(chunk)
                event_type = chunk.get("type")
                print(f"Event {len(events)}: {event_type}")
                
                if len(events) >= 20:  # Limit for diagnostics
                    break
    except asyncio.TimeoutError:
        print("! Stream timed out")
    
    duration = time.time() - start
    
    # 3. Analyze events
    print(f"\n=== Event Analysis ===")
    print(f"Total events: {len(events)}")
    print(f"Duration: {duration:.2f}s")
    
    event_types = {}
    for event in events:
        t = event.get("type", "unknown")
        event_types[t] = event_types.get(t, 0) + 1
    
    print("Event types:")
    for t, count in event_types.items():
        print(f"  {t}: {count}")
    
    # 4. Check for content
    content_events = [e for e in events if e.get("type") in ("content", "text", "stream_chunk", "completed")]
    print(f"\nContent events: {len(content_events)}")
    
    if content_events:
        print("✅ Content streaming working")
        for i, event in enumerate(content_events[:3]):  # Show first 3
            content = event.get("content") or event.get("text", "")
            print(f"  Sample {i+1}: {content[:50]}...")
    else:
        print("❌ No content events received")
    
    # 5. Check for errors
    error_events = [e for e in events if e.get("type") == "stream_error"]
    if error_events:
        print(f"\n⚠️  {len(error_events)} error events:")
        for err in error_events:
            print(f"  {err.get('error')}")
    else:
        print("\n✓ No error events")
    
    # 6. Performance metrics
    if len(events) > 1:
        timestamps = [time.time() for _ in events]  # Approximate
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        print(f"\nAverage interval: {avg_interval:.3f}s")
    
    await formation.stop_overlord()
    
    print("\n=== Diagnostic Complete ===")

# Run diagnostics
asyncio.run(diagnose_streaming_issues())
```

---

## Getting Help

### Information to Provide

When reporting streaming issues:

1. **Configuration:**
   ```yaml
   overlord:
     response:
       streaming: true
       progress: true
   ```

2. **Event log:**
   ```python
   # First 10 events with types
   ```

3. **Performance metrics:**
   ```
   Total events: 8
   Content events: 1
   Duration: 24.58s
   Average interval: 11.14s
   ```

4. **Error messages:**
   ```
   Stream error: [exact error message]
   ```

5. **Code snippet:**
   ```python
   # How you're consuming the stream
   ```

### Related Documentation

- **[Streaming Guide](streaming.md)** - Complete feature documentation
- **[Quick Start](streaming-quickstart.md)** - Get started in 5 minutes
- **[Response Formats](response-formats.md)** - Format compatibility
- **[E2E Tests](../../e2e/tests/10_streaming/)** - Working examples

### Common Solutions Summary

| Problem | Quick Fix |
|---------|-----------|
| No content | Include `"completed"` event type in content extraction |
| Slow streaming | Normal for meta events; check `complexity_threshold` |
| No streaming | Set `streaming: true` in formation.yaml |
| Timeout | Increase timeout or remove for long operations |
| No progress | Set `progress: true` and enable workflows |
| API errors | Check API keys and fallback configuration |
| Memory issues | Don't buffer entire response; process incrementally |

---

## Testing Your Fix

```python
async def test_fix():
    """Test if streaming issues are resolved."""
    formation = Formation()
    await formation.load("formation.yaml")
    overlord = await formation.start_overlord()
    
    # Test content extraction
    content_parts = []
    
    async for chunk in overlord.chat_stream(
        message="Say 'hello world'",
        user_id="test"
    ):
        # Include ALL content event types
        if chunk.get("type") in ("content", "text", "stream_chunk", "completed"):
            content = chunk.get("content") or chunk.get("text", "")
            if content:
                content_parts.append(content)
    
    full_content = "".join(content_parts)
    
    if "hello" in full_content.lower():
        print("✅ Streaming fix working - got content!")
    else:
        print(f"❌ Still broken - content: {full_content}")
    
    await formation.stop_overlord()

asyncio.run(test_fix())
```
