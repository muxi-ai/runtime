# Async Operations Guide

**Complete guide to asynchronous request processing in MUXI Runtime**

## Table of Contents
- [Overview](#overview)
- [When to Use Async](#when-to-use-async)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Async Decision Logic](#async-decision-logic)
- [Webhook System](#webhook-system)
- [Request Lifecycle](#request-lifecycle)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Overview

MUXI Runtime supports **asynchronous request processing** for long-running operations. Instead of keeping connections open for minutes, the system:

1. Accepts the request and returns immediately with a `request_id`
2. Processes the request in the background
3. Delivers results via webhook when complete

This enables:
- **Better UX**: No timeout issues, users get instant acknowledgment
- **Scalability**: Handle more concurrent requests without blocking
- **Flexibility**: Client can poll status or wait for webhooks
- **Reliability**: Survive client disconnections during processing

---

## When to Use Async

### Automatic Decision (Recommended)

The runtime **automatically decides** whether to use async based on:

1. **Time estimation**: If expected processing time > `threshold_seconds`
2. **Complexity analysis**: High complexity scores trigger async mode
3. **Workflow decomposition**: Multi-task workflows often need async
4. **Explicit flags**: User or application can force async mode

### Manual Control

You can explicitly control async behavior:

```python
# Force async mode
response = await overlord.chat(
    message="Generate a comprehensive market analysis",
    user_id="user123",
    session_id="session456",
    use_async=True  # Force async
)

# Force sync mode
response = await overlord.chat(
    message="What is 2 + 2?",
    user_id="user123",
    session_id="session456",
    use_async=False  # Force sync
)

# Let system decide (default)
response = await overlord.chat(
    message="Analyze this document",
    user_id="user123",
    session_id="session456"
    # use_async not specified - system decides
)
```

### Typical Use Cases

**Async Recommended**:
- Complex research or analysis tasks
- Multi-step workflows with multiple LLM calls
- Document processing or generation
- Tasks estimated >30 seconds
- Batch operations

**Sync Recommended**:
- Simple Q&A (e.g., "What is 2+2?")
- Interactive conversations
- Real-time streaming responses
- Quick lookups or calculations
- Approval flows (user needs to respond)

---

## Architecture

### High-Level Flow

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ 1. POST /chat (async request)
       ▼
┌──────────────────────────────────┐
│             Overlord             │
│  ┌────────────────────────────┐  │
│  │   Async Decision Logic     │  │
│  │  - Complexity analysis     │  │
│  │  - Time estimation         │  │
│  │  - Webhook availability    │  │
│  └────────────────────────────┘  │
└──────┬────────────────┬──────────┘
       │                │
       │ 2. Immediate   │ 3. Background
       │    response    │    processing
       ▼                ▼
┌─────────────┐   ┌──────────────┐
│   Client    │   │ Background   │
│             │   │   Executor   │
│  request_id │   │              │
│  status     │   └──────┬───────┘
│             │          │
│             │          │ 4. Complete
│             │          ▼
│             │   ┌──────────────┐
│             │◄──┤   Webhook    │
│             │   │   Delivery   │
└─────────────┘   └──────────────┘
```

### Key Components

#### 1. **Request Analyzer** (`src/muxi/formation/overlord/request_analyzer.py`)
- Analyzes request complexity
- Estimates processing time
- Provides recommendations for async/sync mode

#### 2. **Async Decision Logic** (`overlord.py`)
- Central decision point for async mode
- Considers multiple factors (complexity, time, webhooks, approval needs)
- Returns boolean decision with rationale

#### 3. **Background Executor** (`overlord.py`)
- Executes async requests in background tasks
- Tracks active async requests
- Manages timeouts and cancellation

#### 4. **Webhook Manager** (`src/muxi/services/webhook_manager.py`)
- Handles webhook delivery with retries
- Validates webhook URLs
- Provides delivery confirmation

#### 5. **Request Tracker** (`src/muxi/services/request_tracker.py`)
- Tracks request status (processing, completed, failed)
- Provides status query API
- Supports cancellation

---

## Configuration

### Formation Configuration

```yaml
# Basic async configuration
async:
  # Webhook URL for async results delivery
  webhook_url: "https://your-app.com/webhooks/muxi"

  # Time threshold for async decision (seconds)
  threshold_seconds: 30

  # Enable/disable time estimation
  enable_estimation: true

  # Webhook retry configuration
  webhook_retries: 3
  webhook_timeout: 10

# Workflow configuration affects async decisions
overlord:
  config:
    # Enable automatic workflow decomposition
    auto_decomposition: true

    # Complexity threshold for workflows (0-10 scale)
    complexity_threshold: 5.0

    # Approval threshold (workflows >= this need approval)
    plan_approval_threshold: 7.0
```

### Runtime Configuration Override

You can override webhook URL per request:

```python
# Override webhook URL for this specific request
response = await overlord.chat(
    message="Long running task",
    user_id="user123",
    session_id="session456",
    use_async=True,
    webhook_url="https://different-webhook.com/callback"  # Override
)
```

### Webhook URL Priority

1. `webhook_url` parameter in `chat()` call
2. `async.webhook_url` in formation YAML
3. No webhook → sync mode only

---

## Async Decision Logic

### Decision Process

```python
async def _determine_async_mode(
    self,
    message: str,
    user_id: str,
    session_id: str,
    agent_name: Optional[str] = None,
    use_async: Optional[bool] = None
) -> bool:
    """
    Determine whether to process request asynchronously.

    Priority Order:
    1. Explicit use_async parameter (highest priority)
    2. Approval needs (force sync for approval flows)
    3. Webhook availability (no webhook = no async)
    4. Complexity analysis
    5. Time estimation
    6. Default: sync mode
    """
```

### Decision Factors

#### 1. **Explicit Flag** (Highest Priority)
```python
if use_async is not None:
    return use_async  # User/app decision wins
```

#### 2. **Approval Requirements**
```python
if await self.would_need_workflow_approval(message, agent_name):
    return False  # Force sync for interactive approval
```

#### 3. **Webhook Availability**
```python
if not self.webhook_url:
    return False  # Can't do async without webhook
```

#### 4. **Complexity Analysis**
```python
complexity = await self.request_analyzer.analyze_complexity(message)
if complexity >= 7.0:  # High complexity
    return True  # Likely needs async
```

#### 5. **Time Estimation**
```python
estimated_time = await self.time_estimator.estimate(message, agent_name)
if estimated_time > self.async_threshold_seconds:
    return True  # Will take too long for sync
```

### Complexity Scoring

Requests are scored on a **0-10 scale**:

| Score | Category | Description | Example |
|-------|----------|-------------|---------|
| 0-2 | Trivial | Simple queries, calculations | "What is 2+2?" |
| 3-4 | Simple | Basic information lookup | "When was Python created?" |
| 5-6 | Moderate | Multi-step reasoning | "Compare Python and JavaScript" |
| 7-8 | Complex | Research, analysis | "Analyze market trends for EVs" |
| 9-10 | Very Complex | Multi-task workflows | "Research competitors, create report, generate presentation" |

**Factors considered**:
- Message length and structure
- Number of questions/requests
- Keywords (analyze, research, create, generate)
- Required capabilities (vision, audio, tools)
- Historical patterns for similar requests

---

## Webhook System

### Webhook Payload Format

```json
{
  "id": "req_abc123xyz",
  "object": "response",
  "status": "completed",
  "timestamp": 1728403200000,
  "formation_id": "my_formation",
  "user_id": "user123",
  "processing_time": 45.23,
  "processing_mode": "async",
  "webhook_url": "https://your-app.com/webhooks/muxi",
  "error": null,
  "response": [
    {
      "type": "text",
      "text": "# Analysis Complete\n\nYour requested analysis..."
    },
    {
      "type": "artifact",
      "artifact_type": "document",
      "identifier": "market_analysis_2024",
      "title": "Market Analysis Report",
      "content": "..."
    }
  ]
}
```

### Webhook Delivery

**Retry Logic**:
- Initial delivery attempt immediately after completion
- Exponential backoff on failures: 1s, 2s, 4s
- Configurable retry count (default: 3)
- Timeout per attempt (default: 10s)

**Failure Handling**:
```python
{
  "status": "failed",
  "error": {
    "type": "webhook_delivery_failed",
    "message": "Failed to deliver webhook after 3 attempts",
    "last_error": "Connection timeout",
    "attempts": 3
  }
}
```

**Security**:
- HTTPS recommended for production
- Optional webhook signing (future enhancement)
- Validate webhook URL format before accepting

### Implementing a Webhook Endpoint

**Python/FastAPI Example**:
```python
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

@app.post("/webhooks/muxi")
async def handle_muxi_webhook(request: Request):
    payload = await request.json()

    # Extract key information
    request_id = payload["id"]
    status = payload["status"]

    if status == "completed":
        response_text = payload["response"][0]["text"]
        # Process successful response
        await process_completion(request_id, response_text)

    elif status == "failed":
        error = payload["error"]
        # Handle failure
        await handle_failure(request_id, error)

    return {"status": "received"}
```

**Node.js/Express Example**:
```javascript
app.post('/webhooks/muxi', async (req, res) => {
  const payload = req.body;

  console.log(`Received webhook for request ${payload.id}`);

  if (payload.status === 'completed') {
    // Process successful response
    await processCompletion(payload.id, payload.response);
  } else if (payload.status === 'failed') {
    // Handle failure
    await handleFailure(payload.id, payload.error);
  }

  res.json({ status: 'received' });
});
```

---

## Request Lifecycle

### Async Request Flow

```
1. Request Submission
   ├─ Client sends request
   ├─ Overlord analyzes complexity
   ├─ Decision: use async mode
   └─ Return immediate response

2. Immediate Response
   {
     "request_id": "req_abc123",
     "status": "processing",
     "webhook_url": "https://...",
     "estimated_time": 45
   }

3. Background Processing
   ├─ Agent selection
   ├─ Tool execution
   ├─ LLM calls
   ├─ Memory updates
   └─ Result generation

4. Webhook Delivery
   ├─ Attempt delivery
   ├─ Retry on failure
   └─ Mark request complete

5. Optional Status Polling
   GET /requests/{request_id}/status
```

### Status Tracking

**Check Request Status**:
```python
# Via Python SDK
status = await overlord.get_request_status(request_id)

# Via HTTP API
GET /api/v1/requests/{request_id}/status
```

**Status Response**:
```json
{
  "request_id": "req_abc123",
  "status": "processing",  // processing, completed, failed, cancelled
  "started_at": "2024-10-08T10:30:00Z",
  "completed_at": null,
  "processing_time": 23.5,
  "progress": {
    "current_step": "executing_tools",
    "total_steps": 4,
    "percent": 50
  }
}
```

### Request Cancellation

**Cancel In-Progress Request**:
```python
# Via Python SDK
await overlord.cancel_request(request_id)

# Via HTTP API
POST /api/v1/requests/{request_id}/cancel
```

**Cancellation Response**:
```json
{
  "request_id": "req_abc123",
  "status": "cancelled",
  "message": "Request cancelled successfully"
}
```

---

## Testing

### Unit Testing Async Logic

```python
import pytest
from src.muxi.formation.overlord import Overlord

@pytest.mark.asyncio
async def test_async_decision_high_complexity():
    overlord = await setup_overlord(webhook_url="http://test.com")

    # High complexity should trigger async
    decision = await overlord._determine_async_mode(
        message="Research the top 50 AI companies and create detailed analysis",
        user_id="test",
        session_id="test"
    )

    assert decision is True
```

### Integration Testing with Webhooks

```python
import pytest
import httpx
from pathlib import Path

@pytest.mark.asyncio
async def test_async_request_with_webhook():
    # Start test webhook server
    webhook_server = await start_webhook_server(port=8765)

    # Load formation with webhook config
    overlord = await load_formation_with_webhook("http://localhost:8765")

    # Send async request
    response = await overlord.chat(
        message="Complex analysis task",
        use_async=True
    )

    # Verify immediate response
    assert "request_id" in response
    assert response["status"] == "processing"

    # Wait for webhook delivery
    webhook = await webhook_server.wait_for_webhook(
        request_id=response["request_id"],
        timeout=60
    )

    # Verify webhook payload
    assert webhook["status"] == "completed"
    assert webhook["id"] == response["request_id"]
    assert len(webhook["response"]) > 0
```

### E2E Testing

See `e2e/tests/9_async/` for comprehensive async operation tests:

- **test_9a1**: Force async mode
- **test_9a2**: Force sync mode
- **test_9a3a/b**: Auto mode selection (simple vs complex)
- **test_9a3b+**: Workflow with approval
- **test_9a4/9a5**: Webhook configuration
- **test_9b1**: Request lifecycle (status, cancellation)
- **test_9c1/2/3**: Advanced scenarios (failures, timeouts, conflicts)

---

## Troubleshooting

### Common Issues

#### 1. **Async request becomes sync**

**Symptoms**: Expected async but got sync response

**Causes**:
- No webhook URL configured
- Request requires approval (forces sync)
- Complexity below threshold
- Time estimate below threshold

**Solution**:
```python
# Check configuration
assert formation.async_config.webhook_url is not None

# Check if approval is forcing sync
if await overlord.would_need_workflow_approval(message, agent):
    # Approval flows are always sync

# Explicitly force async
response = await overlord.chat(message, use_async=True)
```

#### 2. **Webhook not delivered**

**Symptoms**: Request completes but no webhook received

**Causes**:
- Webhook URL unreachable
- Firewall/network issues
- Webhook endpoint returns error
- URL formatting issues

**Solution**:
```bash
# Test webhook URL manually
curl -X POST https://your-webhook.com/endpoint \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# Check webhook server logs
docker-compose logs webhook-server

# Verify URL in formation
webhook_url: "https://your-app.com/webhook"  # Must be accessible
```

#### 3. **Request timeout**

**Symptoms**: Request status stuck in "processing"

**Causes**:
- LLM API timeout
- Tool execution hanging
- Network issues
- Infinite loops in agent logic

**Solution**:
```python
# Check request status
status = await overlord.get_request_status(request_id)

# Cancel if stuck
if status["processing_time"] > 300:  # 5 minutes
    await overlord.cancel_request(request_id)

# Check logs for errors
```

#### 4. **Status polling not working**

**Symptoms**: GET /requests/{id}/status returns 404

**Causes**:
- Request not tracked (sync mode used)
- Request ID incorrect
- Request expired from tracker

**Solution**:
```python
# Only async requests are tracked
if response.get("status") == "processing":
    # This is async, can poll status
    status = await get_status(response["request_id"])
else:
    # This was sync, response is complete
```

### Debug Logging

Enable debug logging to understand async decisions:

```yaml
logging:
  level: "DEBUG"
  format: "json"

overlord:
  debug:
    log_async_decisions: true  # Log why async was chosen
    log_complexity_scores: true
    log_time_estimates: true
```

**Log Output**:
```json
{
  "event": "async_decision",
  "request_id": "req_abc",
  "decision": "async",
  "reason": "complexity_threshold_exceeded",
  "complexity_score": 7.5,
  "time_estimate": 45,
  "webhook_available": true
}
```

---

## Best Practices

### 1. **Always Configure Webhooks for Production**
```yaml
async:
  webhook_url: "https://your-production-app.com/webhooks/muxi"
  webhook_retries: 5  # More retries for production
```

### 2. **Handle Both Sync and Async Responses**
```python
response = await overlord.chat(message, user_id, session_id)

if isinstance(response, dict) and response.get("status") == "processing":
    # Async response - wait for webhook
    request_id = response["request_id"]
    # Store request_id, poll status, etc.
else:
    # Sync response - process immediately
    process_response(response)
```

### 3. **Implement Idempotent Webhook Handlers**
```python
@app.post("/webhook")
async def handle_webhook(payload: dict):
    request_id = payload["id"]

    # Check if already processed
    if await is_processed(request_id):
        return {"status": "already_processed"}

    # Process webhook
    await process_webhook(payload)

    # Mark as processed
    await mark_processed(request_id)

    return {"status": "ok"}
```

### 4. **Monitor Async Request Performance**
```python
# Track metrics
metrics = {
    "async_requests_total": count,
    "avg_processing_time": avg_time,
    "webhook_success_rate": success_rate,
    "timeout_rate": timeout_rate
}
```

### 5. **Test Both Modes**
- Test with `use_async=True` explicitly
- Test with `use_async=False` explicitly
- Test with auto-detection (no parameter)
- Test webhook delivery and retries
- Test status polling and cancellation

---

## Related Documentation

- [Deferred Async Execution](./workflow/deferred_async_execution.md) - Approval-aware async
- [Request Lifecycle](./request-lifecycle.md) - Complete request flow
- [Workflow Orchestration](./workflow/orchestration.md) - Workflow system
- [API Reference](./api/formation-api-implemented.yaml) - HTTP API endpoints

---

## Additional Resources

### Code References
- `src/muxi/formation/overlord/overlord.py` - Async decision logic
- `src/muxi/formation/overlord/request_analyzer.py` - Complexity analysis
- `src/muxi/services/webhook_manager.py` - Webhook delivery
- `src/muxi/services/request_tracker.py` - Status tracking
- `e2e/tests/9_async/` - Complete async test suite

### Configuration Examples
- `test-formations/async-example/formation.afs` - Example async formation
- `e2e/tests/9_async/formations/formation-async/formation.afs` - Test formation

---

**Last Updated**: October 8, 2025
**Version**: 1.0
**Maintainer**: MUXI Runtime Team
