# Deferred Async Execution Guide

## Overview

The MUXI Runtime implements an elegant deferred async execution system that ensures workflow approval flows remain synchronous and interactive while still allowing asynchronous execution after approval is obtained.

## Problem Statement

Previously, the overlord would make async decisions early in the request processing pipeline. When a workflow required user approval, the system might switch to async mode before presenting the plan to the user, breaking the interactive approval flow and creating a disjointed user experience.

## Solution

The system now implements an **approval-aware** async decision logic that:

1. Detects when workflow approval will be required
2. Forces synchronous execution for approval flows
3. Re-evaluates async execution after approval is obtained
4. Executes approved workflows asynchronously when appropriate

## Architecture

### Key Components

#### 1. Approval Detection (`would_need_workflow_approval`)
```python
async def would_need_workflow_approval(
    self, 
    message: str, 
    agent_name: Optional[str]
) -> bool
```

This method quickly checks if a request will require workflow approval by:
- Checking if auto-decomposition is enabled
- Verifying no specific agent was requested
- Analyzing request complexity
- Comparing against approval thresholds

#### 2. Approval-Aware Async Decision (`_determine_async_mode`)

The async decision logic now includes an approval check:
```python
# Check if this would need approval - if so, force sync
if await self.overlord.would_need_workflow_approval(message, agent_name):
    return False  # Force sync mode for approval flows
```

#### 3. Post-Approval Async Re-evaluation (`_should_execute_workflow_async`)

After approval is obtained, the system re-evaluates whether the workflow execution should be async:
```python
async def _should_execute_workflow_async(
    self, 
    workflow: Workflow, 
    original_message: str
) -> bool
```

This considers:
- Webhook URL availability
- Time estimator predictions
- Task complexity scores
- Configured thresholds

#### 4. Async Workflow Execution

When async execution is appropriate, the system:
- Returns an immediate response to the user
- Executes the workflow in the background
- Sends webhook notifications on completion

## Configuration

### Required Configuration for Async Execution

```yaml
async:
  webhook_url: "https://your-webhook-endpoint.com/webhook"
  threshold_seconds: 30  # Optional, defaults to 30
```

### Workflow Configuration

```yaml
overlord:
  config:
    auto_decomposition: true
    complexity_threshold: 5.0
    plan_approval_threshold: 7.0
```

## User Experience Flow

### 1. Synchronous Approval Flow
```
User Request → Complexity Analysis → Needs Approval → Force Sync Mode
→ Present Plan → User Approves → Re-evaluate Async → Execute (sync/async)
```

### 2. No Approval Needed Flow
```
User Request → Complexity Analysis → No Approval Needed 
→ Normal Async Decision → Execute (sync/async based on time)
```

### 3. Explicit Async Override
```
User Request (use_async=True) → Skip All Checks → Execute Async
```

## API Usage

### Standard Request (Auto-Detection)
```python
response = await overlord.chat(
    message="Complex task requiring workflow",
    user_id="user123",
    # use_async not specified - system auto-detects
)
```

### Force Synchronous
```python
response = await overlord.chat(
    message="Complex task",
    user_id="user123",
    use_async=False  # Explicit sync
)
```

### Force Asynchronous
```python
response = await overlord.chat(
    message="Complex task",
    user_id="user123",
    use_async=True  # Explicit async, bypasses approval checks
)
```

## Webhook Notifications

When workflows execute asynchronously, completion notifications are sent to the configured webhook URL:

```json
{
    "request_id": "req_123",
    "workflow_id": "wf_456",
    "status": "completed",
    "timestamp": "2025-07-30T12:00:00Z",
    "result": {
        "success": true,
        "content": "Workflow completed successfully",
        "artifacts": []
    }
}
```

Error notifications include:
```json
{
    "request_id": "req_123",
    "workflow_id": "wf_456", 
    "status": "failed",
    "timestamp": "2025-07-30T12:00:00Z",
    "error": "Error message here"
}
```

## Best Practices

1. **Always Configure Webhook URL** for async execution
   - Without a webhook URL, all workflows execute synchronously
   - Ensure your webhook endpoint can handle the notification payload

2. **Set Appropriate Thresholds**
   - `complexity_threshold`: When to trigger workflows (default: 5.0)
   - `plan_approval_threshold`: When to require approval (default: 7.0)
   - `async_threshold_seconds`: Time threshold for async (default: 30s)

3. **Handle Webhook Failures**
   - The system will attempt to send webhooks but won't retry on failure
   - Implement retry logic in your webhook handler if needed

4. **Monitor Background Execution**
   - Use observability events to track workflow progress
   - Check webhook notifications for completion status

## Observability Events

The system emits several observability events:

- `ASYNC_THRESHOLD_DETECTED` - When async decision is made
- `force_sync_for_approval` - When approval forces sync mode
- `post_approval_execution` - When re-evaluating after approval
- `ASYNC_PROCESSING_FAILED` - When async execution fails

## Testing

The implementation includes comprehensive test coverage:

- **Unit Tests**: Each component tested in isolation
- **Integration Tests**: End-to-end workflow scenarios
- **Edge Cases**: Missing configs, network failures, exceptions

Run tests with:
```bash
pytest tests/test_deferred_async_*.py -v
```

## Migration Guide

The deferred async execution system is **backward compatible**. Existing code will continue to work:

- Explicit `use_async=True/False` is still respected
- Workflows without approval requirements are unaffected
- No configuration changes required for existing setups

To enable the new behavior:
1. Ensure `auto_decomposition` is enabled
2. Set appropriate approval thresholds
3. Configure webhook URL for async execution

## Troubleshooting

### Workflows Always Execute Synchronously

Check:
- Is a webhook URL configured?
- Are workflows exceeding the time threshold?
- Is approval required (forcing sync)?

### Approval Flows Going Async

This should not happen with the new system. If it does:
- Verify the implementation is deployed
- Check for explicit `use_async=True`
- Review observability logs

### Webhook Not Received

Verify:
- Webhook URL is accessible
- No network/firewall issues
- Check observability logs for webhook errors

## Implementation Details

The elegant solution required only ~50 lines of code changes across 2 files:

1. **`overlord.py`**: Added approval detection and async execution methods
2. **`chat_orchestrator.py`**: Enhanced async decision logic

This minimal change ensures maximum compatibility while solving the core problem of approval flows being disrupted by async execution.