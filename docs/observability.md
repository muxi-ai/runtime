# MUXI Observability System

## Overview

The MUXI observability system provides comprehensive event tracking and logging for all runtime operations. It uses a dual-event architecture to separate infrastructure events from user request lifecycle tracking, with highly configurable output destinations and formats.

## Key Concepts

### Event Types

MUXI uses two distinct event categories:

1. **SystemEvents**: Infrastructure and operational events
   - Server startup/shutdown
   - Service initialization
   - MCP/A2A operations
   - Error conditions
   - Always routed to stdout for server monitoring

2. **ConversationEvents**: User request lifecycle tracking
   - Request received/completed/failed
   - Agent selection and responses
   - Memory operations
   - Document processing
   - Routed according to formation configuration

### Event Structure

All events follow a consistent JSON-Lines format:

```json
{
  "id": "evt_abc123",
  "timestamp": 1234567890,
  "level": "info",
  "muxi_version": "1.0.0",
  "server": "hostname",
  "event": "request.received",
  "session_id": "session_123",
  "request": {
    "id": "req_xyz789",
    "status": "processing",
    "started": 1234567890,
    "duration_ms": 0,
    "formation_id": "my-formation",
    "user_id": "user_456"
  },
  "data": {
    "custom": "fields"
  }
}
```

## Configuration

Observability is configured in the formation YAML under the `logging` section:

```yaml
logging:
  level: info                    # Minimum level: debug, info, warning, error
  output: stdout                 # Output destination: stdout, file, stream, trail
  path: /var/log/muxi.jsonl     # For file output
  events:                       # Event filter patterns (optional)
    - "request.*"
    - "agent.*"
    - "memory.*"
  streams:                      # Advanced streaming configuration
    - transport: stream
      destination: https://logs.example.com/events
      format: jsonl
      auth:
        type: bearer
        token: "${{ secrets.LOG_TOKEN }}"
```

### Output Destinations

1. **stdout** (default): Events printed to standard output
2. **file**: Events written to specified file path
3. **stream**: HTTP/HTTPS streaming to external endpoints
4. **trail**: MUXI Trail integration for centralized logging

### Level Filtering

Events are filtered by level hierarchy:
- `debug`: All events
- `info`: Info, warning, and error events
- `warning`: Warning and error events only
- `error`: Error events only

### Event Filtering

Use glob patterns to filter specific events:
- `"*"`: All events
- `"request.*"`: All request events
- `"agent.selected"`: Specific event
- `"memory.long_term.*"`: All long-term memory events

## Usage

### Basic Event Emission

```python
from muxi.services import observability

# Simple event
observability.observe(
    event_type=observability.ConversationEvents.AGENT_SELECTED,
    level=observability.EventLevel.INFO,
    data={"agent_id": "assistant", "reason": "best_match"},
    description="Selected assistant agent for general query"
)

# With custom event type
observability.observe(
    event_type="custom.event",
    level=observability.EventLevel.DEBUG,
    data={"custom": "data"},
    description="Custom application event"
)
```

### Request Tracking

The overlord automatically tracks requests with context:

```python
# This happens automatically in overlord.chat() - now synchronous
with observability_manager.track_request(
    request_id="req_123",
    session_id="session_456",
    formation_id="my-formation",
    user_id="user_789"
) as context:
    # All events within this context automatically include request info
    observability.observe(
        event_type=observability.ConversationEvents.AGENT_THINKING,
        data={"agent": "assistant"}
    )
```

## Advanced Features

### Streaming Transports

Configure real-time event streaming to external services:

```yaml
logging:
  streams:
    # HTTP/HTTPS streaming
    - transport: stream
      destination: https://logs.example.com/events
      format: jsonl
      level: info
      events: ["request.*", "error.*"]

    # File transport for audit logs
    - transport: file
      destination: /var/log/muxi-audit.jsonl
      format: jsonl
      events: ["security.*", "admin.*"]

    # Multiple destinations
    - transport: stdout
      format: text
      level: error  # Only errors to stdout
```

### Format Options

Different transports support various formats:
- `jsonl`: JSON Lines (default)
- `text`: Human-readable text
- `elastic`: Elasticsearch bulk format
- `splunk`: Splunk HEC format
- `datadog`: Datadog logs format

### Authentication

Streams support multiple authentication methods:

```yaml
auth:
  type: bearer
  token: "${{ secrets.API_TOKEN }}"

# OR
auth:
  type: basic
  username: "${{ secrets.LOG_USER }}"
  password: "${{ secrets.LOG_PASS }}"

# OR
auth:
  type: api_key
  header: "X-API-Key"
  key: "${{ secrets.API_KEY }}"
```

### Health Monitoring

The observability system includes built-in health monitoring for stream destinations:

```python
# Get health status
health_summary = await observability_manager.get_health_summary()

# Check specific destination
status = await observability_manager.get_destination_health("https://logs.example.com")

# Force health check
await observability_manager.force_health_check()
```

## Best Practices

1. **Use Appropriate Levels**
   - `DEBUG`: Detailed debugging information
   - `INFO`: General informational messages
   - `WARNING`: Warning conditions that should be reviewed
   - `ERROR`: Error conditions requiring attention

2. **Include Meaningful Data**
   ```python
   # Good
   observability.observe(
       event_type=observability.ConversationEvents.AGENT_ERROR,
       level=observability.EventLevel.ERROR,
       data={
           "agent_id": agent.id,
           "error_type": "timeout",
           "duration_ms": 30000,
           "retry_count": 3
       },
       description=f"Agent {agent.id} timed out after 3 retries"
   )

   # Bad
   observability.observe(
       event_type="error",
       description="Something went wrong"
   )
   ```

3. **Use Event Patterns**
   - Follow the hierarchical naming convention: `category.subcategory.specific`
   - Examples: `request.received`, `agent.selected`, `memory.long_term.stored`

4. **Avoid Sensitive Data**
   - Never log passwords, API keys, or personal information
   - Use data masking when necessary
   - Example: Log user IDs, not user emails

5. **Performance Considerations**
   - Events are emitted asynchronously (non-blocking)
   - Use appropriate event filtering to reduce volume
   - Consider sampling for high-frequency events

## Troubleshooting

### Events Not Appearing

1. Check formation configuration:
   ```bash
   # Verify logging config is loaded
   grep -A10 "logging:" formation.afs
   ```

2. Check event level:
   ```python
   # Ensure event level >= configured level
   observability.observe(
       event_type="test.event",
       level=observability.EventLevel.INFO  # Must be >= formation level
   )
   ```

3. Check event filters:
   ```yaml
   logging:
     events: ["request.*"]  # Only request.* events will be logged
   ```

### Stream Connection Issues

1. Enable debug logging:
   ```yaml
   logging:
     level: debug
   ```

2. Check health status:
   ```python
   health = await observability_manager.get_health_summary()
   print(health)
   ```

3. Verify authentication:
   - Ensure secrets are properly configured
   - Check network connectivity
   - Verify SSL certificates for HTTPS

### Performance Issues

1. Reduce event volume:
   ```yaml
   logging:
     level: warning  # Only warnings and errors
     events:
       - "error.*"
       - "request.failed"
   ```

2. Use sampling for high-frequency events:
   ```python
   import random

   # Sample 10% of events
   if random.random() < 0.1:
       observability.observe(...)
   ```

3. Configure stream buffering:
   ```yaml
   streams:
     - transport: stream
       buffer_size: 1000
       flush_interval: 5
   ```

## Architecture Details

### Context Propagation

The observability system uses Python's `contextvars` for thread-safe context management:

1. **Request Context**: Automatically propagated through async calls
2. **Event Logger**: Configuration-aware logger available globally
3. **Thread Safety**: Each thread/task maintains its own context

### Non-Blocking Design

Events are emitted using the `@multitasking.task` decorator to ensure they never block the main application flow:

```python
@multitasking.task
def _emit_in_background():
    # Event emission happens here
    pass
```

This ensures that observability never impacts application performance.

### Extensibility

The system is designed for extensibility:

1. **Custom Formatters**: Add new output formats
2. **Custom Transports**: Implement new streaming destinations
3. **Event Processors**: Add event transformation pipelines
4. **Metrics Integration**: Export metrics from events

## Examples

### Complete Formation Example

```yaml
schema: "1.0.0"
id: "production-app"
description: "Production application with comprehensive logging"

logging:
  level: info
  output: file
  path: /var/log/muxi/app.jsonl
  events:
    - "request.*"
    - "agent.*"
    - "error.*"
  streams:
    # Real-time monitoring
    - transport: stream
      destination: https://monitor.example.com/events
      format: jsonl
      level: warning
      auth:
        type: bearer
        token: "${{ secrets.MONITOR_TOKEN }}"

    # Error aggregation
    - transport: stream
      destination: https://errors.example.com/intake
      format: splunk
      events: ["error.*", "*.failed"]
      auth:
        type: api_key
        header: "X-Splunk-Token"
        key: "${{ secrets.SPLUNK_TOKEN }}"

    # Audit trail
    - transport: file
      destination: /var/log/muxi/audit.jsonl
      events: ["admin.*", "security.*"]
      format: jsonl

agents:
  - id: assistant
    name: Assistant
    # ... agent config ...
```

### Custom Event Patterns

```python
# Application-specific events
class AppEvents:
    # User lifecycle
    USER_REGISTERED = "app.user.registered"
    USER_LOGIN = "app.user.login"
    USER_LOGOUT = "app.user.logout"

    # Business events
    ORDER_PLACED = "app.order.placed"
    PAYMENT_PROCESSED = "app.payment.processed"

    # Performance tracking
    SLOW_QUERY = "app.performance.slow_query"
    API_TIMEOUT = "app.performance.api_timeout"

# Usage
observability.observe(
    event_type=AppEvents.ORDER_PLACED,
    level=observability.EventLevel.INFO,
    data={
        "order_id": "order_123",
        "user_id": "user_456",
        "total": 99.99,
        "items": 3
    },
    description="New order placed"
)
```

## Migration Guide

If migrating from direct logging to MUXI observability:

1. Replace logger calls:
   ```python
   # Old
   logger.info("Agent selected", extra={"agent": agent_id})

   # New
   observability.observe(
       event_type=observability.ConversationEvents.AGENT_SELECTED,
       level=observability.EventLevel.INFO,
       data={"agent": agent_id},
       description="Agent selected"
   )
   ```

2. Configure formation:
   ```yaml
   logging:
     level: info
     output: file
     path: /path/to/your/logfile.jsonl
   ```

3. Update monitoring:
   - Parse JSON Lines format
   - Filter by event type
   - Use request.id for correlation

The observability system provides a powerful, flexible foundation for understanding and monitoring your MUXI applications in production.
