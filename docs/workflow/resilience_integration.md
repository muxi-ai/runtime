# MUXI Workflow Resilience Integration

**Version**: 1.0
**Date**: July 29, 2025
**Status**: Production Ready

## Overview

The MUXI Runtime Workflow System now includes a comprehensive resilience layer that provides automatic error recovery, user-friendly error messages, and graceful degradation for workflow execution. This integration wraps the standard `WorkflowExecutor` with `ResilientWorkflowExecutor` to handle failures intelligently.

## Architecture

### Resilience Layer Components

```
┌─────────────────────┐
│     Overlord        │
└──────────┬──────────┘
           │ Uses
           ▼
┌─────────────────────┐     ┌────────────────────┐
│ResilientWorkflowExecutor│──►│ WorkflowExecutor   │
│                     │     │                    │
│ • Error Classification │     │ • Task Execution   │
│ • Retry Logic       │     │ • Agent Routing    │
│ • User Messages     │     │ • Parallel Tasks   │
│ • Fallback Strategies│     │                    │
└─────────────────────┘     └────────────────────┘
           │
           ▼
┌─────────────────────┐     ┌────────────────────┐
│ Error Handlers      │     │ Resilience Config  │
│ • Circuit Breakers  │     │ • Retry Settings   │
│ • Recovery Manager  │     │ • Timeout Configs  │
│ • Fallback Provider │     │ • Error Strategies │
└─────────────────────┘     └────────────────────┘
```

## Implementation

### 1. ResilientWorkflowExecutor

Located in `src/muxi/formation/workflow/resilient_executor.py`:

```python
class ResilientWorkflowExecutor:
    """
    Resilient wrapper for WorkflowExecutor that provides:
    - Automatic error classification and recovery
    - User-friendly error messages
    - Exponential backoff retry logic
    - Graceful degradation strategies
    """

    def __init__(self, agent_registry: Dict[str, Agent], config: WorkflowConfig):
        self.executor = WorkflowExecutor(agent_registry, config)
        self.error_classifier = ErrorClassifier()
        self.retry_manager = RetryManager(config.retry)
        self.message_formatter = UserMessageFormatter()
```

### 2. Error Classification

The system classifies errors into categories for appropriate handling:

```python
class ErrorType(Enum):
    NETWORK_TIMEOUT = "network_timeout"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TEMPORARY_FAILURE = "temporary_failure"
    PERMANENT_FAILURE = "permanent_failure"
    UNKNOWN = "unknown"

class ErrorSeverity(Enum):
    RECOVERABLE = "recoverable"      # Can retry
    PARTIAL_FAILURE = "partial"       # Can provide partial results
    CRITICAL = "critical"             # Cannot proceed
```

### 3. User-Friendly Error Messages

Instead of generic "there was an error" messages, the system provides context-aware explanations:

```python
ERROR_MESSAGES = {
    ErrorType.NETWORK_TIMEOUT: {
        "mcp_tool": "The {tool} service is taking longer than expected to respond.",
        "suggestion": "The system will retry automatically with exponential backoff."
    },
    ErrorType.AUTHENTICATION: {
        "linear": "Unable to authenticate with Linear API. Please check your credentials.",
        "suggestion": "Verify your Linear API token is correctly configured."
    },
    ErrorType.RATE_LIMIT: {
        "default": "The service has rate-limited our requests.",
        "suggestion": "Waiting before retrying to respect rate limits."
    }
}
```

## Configuration

### Formation YAML Configuration

```yaml
overlord:
  config:
    # Enable resilience features
    circuit_breaker: true
    error_recovery: true

    workflow:
      # Error recovery strategy
      error_recovery: "retry_with_backoff"  # Options: fail_fast, skip_and_continue

      # Retry configuration
      retry:
        max_attempts: 5              # Maximum retry attempts
        initial_delay: 2.0           # Initial delay in seconds
        backoff_factor: 2.0          # Exponential backoff multiplier
        max_delay: 120.0             # Maximum delay between retries
        retry_on_errors:             # Error types to retry
          - "timeout"
          - "rate_limit"
          - "temporary_failure"
          - "connection_error"

      # Timeout configuration
      timeouts:
        task_timeout: 300            # 5 minutes per task
        workflow_timeout: 1800       # 30 minutes total
        enable_adaptive_timeout: true # Adjust based on complexity
```

### Integration in Overlord

The Overlord automatically uses the resilient executor:

```python
# In overlord.py
from muxi.runtime.formation.workflow.resilient_executor import ResilientWorkflowExecutor

# During initialization
self.workflow_executor = ResilientWorkflowExecutor(
    agent_registry=self.agents,
    config=self.workflow_config
)
```

## Retry Mechanism

### Exponential Backoff Implementation

```python
async def retry_with_exponential_backoff(
    func: Callable,
    max_attempts: int = 5,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    max_delay: float = 120.0
) -> Any:
    """
    Retry with exponential backoff:
    - Attempt 1: immediate
    - Attempt 2: 2s delay
    - Attempt 3: 4s delay
    - Attempt 4: 8s delay
    - Attempt 5: 16s delay
    """
    for attempt in range(max_attempts):
        try:
            return await func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise

            delay = min(initial_delay * (backoff_factor ** attempt), max_delay)
            await asyncio.sleep(delay)
```

## Error Handling Examples

### 1. MCP Tool Timeout

**Without Resilience:**
```
Error: there was an error
```

**With Resilience:**
```
The Linear API is taking longer than expected to respond.
Retrying in 2 seconds... (attempt 2/5)
```

### 2. Authentication Failure

**Without Resilience:**
```
Error: 401 Unauthorized
```

**With Resilience:**
```
Unable to authenticate with Linear API.
Please check that your Linear API token is correctly configured.
The research has been completed, but the Linear issue could not be created.

Research Summary:
[Full research content provided]
```

### 3. Rate Limiting

**Without Resilience:**
```
Error: 429 Too Many Requests
```

**With Resilience:**
```
The service has rate-limited our requests.
Waiting 30 seconds before retrying to respect rate limits...
Retry attempt 2/5 starting...
```

## Best Practices

### 1. Configuration Guidelines

- Set `max_attempts` based on service reliability (3-5 for most services)
- Use exponential backoff to avoid overwhelming services
- Configure service-specific retry settings in MCP server configs
- Enable circuit breakers for frequently failing services

### 2. Error Recovery Strategies

- **retry_with_backoff**: Best for transient failures (network, timeouts)
- **skip_and_continue**: For non-critical tasks in workflows
- **fail_fast**: When immediate failure notification is needed

### 3. Monitoring and Observability

The resilience layer integrates with the observability system:

```python
# Metrics tracked
- retry_attempts_total
- retry_success_rate
- error_classification_counts
- fallback_usage_rate
- circuit_breaker_trips
```

## Testing Resilience

### 1. Demo Script

See `tests/e1e/day_7/demo_10_workflows.py` for examples of resilience in action:

```python
# Simulates various failure scenarios
- Timeout with retry and recovery
- Authentication failure with fallback
- Partial success with user notification
```

### 2. Integration Tests

The resilience layer is tested with:
- Real MCP server timeouts
- Authentication failures
- Rate limiting scenarios
- Network interruptions

## Migration Guide

### Existing Formations

No changes required! The resilience layer is automatically active when:

```yaml
overlord:
  config:
    circuit_breaker: true    # Enable circuit breakers
    error_recovery: true     # Enable recovery strategies
```

### Custom Error Handling

To add custom error handling for specific services:

```python
# In your agent or MCP configuration
ERROR_HANDLERS = {
    "my_service": {
        "timeout": "My service is experiencing delays. Your request is queued.",
        "auth": "Please reconnect your My Service account in settings."
    }
}
```

## Future Enhancements

1. **Adaptive Retry Strategies**: Learn optimal retry patterns per service
2. **Predictive Circuit Breaking**: Anticipate failures before they occur
3. **Cross-Workflow Learning**: Share resilience patterns across workflows
4. **Custom Recovery Actions**: User-defined recovery strategies

## Related Documentation

- [Workflow Orchestration](orchestration.md) - Core workflow system
- [Workflow Technical Guide](technical_guide.md) - Implementation details
- [MCP Implementation Guide](../mcp/implementation-guide.md) - MCP error handling
