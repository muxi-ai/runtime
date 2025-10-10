# Trigger System

The MUXI trigger system provides a webhook-like interface for external systems to initiate formation actions with template-based message generation.

## Overview

Triggers allow you to:
- Accept external event data via HTTP POST
- Transform event data using templates with `${{ data.* }}` syntax
- Process events asynchronously or synchronously
- Integrate with external systems (GitHub, Linear, monitoring tools, etc.)

## Architecture

```
External System → Trigger Endpoint → Template Rendering → Formation Chat
     (JSON)           (HTTP POST)         (${{ data.* }})       (Message)
```

## API Endpoints

### Execute Trigger

```http
POST /v1/formations/{formation_id}/triggers/{trigger_name}
X-Client-Key: YOUR_CLIENT_KEY_HERE
Content-Type: application/json

{
  "data": {
    "key1": "value1",
    "nested": {
      "key2": "value2"
    }
  },
  "user_id": "0",
  "session_id": "optional-session",
  "use_async": true
}
```

**Response (Async)**:
```json
{
  "status": "queued",
  "trigger_id": "trigger_abc123",
  "job_id": "job_def456"
}
```

**Response (Sync)**:
```json
{
  "status": "completed",
  "trigger_id": "trigger_abc123",
  "message": "Rendered message..."
}
```

### List Triggers

```http
GET /v1/formations/{formation_id}/triggers
X-Client-Key: YOUR_CLIENT_KEY_HERE
```

**Response**:
```json
{
  "formation_id": "my-formation",
  "triggers": ["github-issue", "linear-ticket", "deployment-notification"],
  "count": 3
}
```

## Template Syntax

Triggers use markdown templates with `${{ data.* }}` placeholders for data substitution.

### Simple Substitution

```markdown
Hello ${{ data.name }}!
```

With data: `{"name": "World"}`  
Result: `Hello World!`

### Nested Data Access

```markdown
Issue #${{ data.issue.number }}: ${{ data.issue.title }}
Author: ${{ data.issue.author }}
```

With data:
```json
{
  "issue": {
    "number": 123,
    "title": "Bug fix",
    "author": "alice"
  }
}
```

Result:
```
Issue #123: Bug fix
Author: alice
```

### Multi-level Nesting

```markdown
User: ${{ data.user.profile.name }} (${{ data.user.profile.email }})
```

Template syntax supports arbitrary nesting depth using dot notation.

## Creating Triggers

1. **Create trigger directory** in your formation:
   ```bash
   mkdir -p formations/my-formation/triggers
   ```

2. **Create trigger template** (e.g., `github-issue.md`):
   ```markdown
   New GitHub issue from ${{ data.repository }}:
   
   **Issue #${{ data.issue.number }}**: ${{ data.issue.title }}
   
   **Author**: ${{ data.issue.author }}
   **State**: ${{ data.issue.state }}
   **Labels**: ${{ data.issue.labels }}
   
   **Description**:
   ${{ data.issue.body }}
   
   Please analyze this issue and provide:
   1. A summary of the problem
   2. Potential impact assessment
   3. Suggested priority level
   4. Relevant code areas to investigate
   ```

3. **Configure webhook** in external system:
   - URL: `https://your-server.com/v1/formations/my-formation/triggers/github-issue`
   - Method: `POST`
   - Headers: `X-Client-Key: YOUR_CLIENT_KEY_HERE`
   - Content-Type: `application/json`

## Example Templates

### GitHub Issue Trigger

**File**: `formations/my-formation/triggers/github-issue.md`

```markdown
New GitHub issue from ${{ data.repository }}:

**Issue #${{ data.issue.number }}**: ${{ data.issue.title }}

**Author**: ${{ data.issue.author }}
**State**: ${{ data.issue.state }}
**Labels**: ${{ data.issue.labels }}

**Description**:
${{ data.issue.body }}

Please analyze this issue and suggest next steps.
```

**Usage**:
```bash
curl -X POST https://your-server.com/v1/formations/my-formation/triggers/github-issue \
  -H "X-Client-Key: YOUR_CLIENT_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "repository": "muxi/runtime",
      "issue": {
        "number": 123,
        "title": "Add trigger system",
        "author": "alice",
        "state": "open",
        "labels": "enhancement, api",
        "body": "We need a trigger system for webhooks..."
      }
    }
  }'
```

### Linear Ticket Trigger

**File**: `formations/my-formation/triggers/linear-ticket.md`

```markdown
Linear ticket update from ${{ data.team }}:

**Ticket**: ${{ data.ticket.identifier }}
**Title**: ${{ data.ticket.title }}
**Status**: ${{ data.ticket.status }}
**Priority**: ${{ data.ticket.priority }}
**Assignee**: ${{ data.ticket.assignee }}

**Description**:
${{ data.ticket.description }}

**Action**: ${{ data.action }}

Please review this ticket update and provide recommended next steps.
```

### Deployment Notification Trigger

**File**: `formations/my-formation/triggers/deployment-notification.md`

```markdown
Deployment notification for ${{ data.service }}:

**Environment**: ${{ data.environment }}
**Version**: ${{ data.version }}
**Status**: ${{ data.status }}
**Deployed by**: ${{ data.deployer }}
**Timestamp**: ${{ data.timestamp }}

**Changes**:
${{ data.changes }}

**Health Checks**:
- API Status: ${{ data.health.api }}
- Database: ${{ data.health.database }}
- Cache: ${{ data.health.cache }}

Please monitor this deployment and report any anomalies.
```

## Processing Modes

### Async Mode (Default)

```json
{
  "data": {...},
  "use_async": true
}
```

- Returns immediately with `job_id`
- Processing happens in background
- No blocking on caller
- Recommended for webhook integrations

### Sync Mode

```json
{
  "data": {...},
  "use_async": false
}
```

- Waits for formation to process message
- Returns rendered message
- Blocks until complete
- Use for interactive or testing scenarios

## Error Handling

### Template Rendering Errors

**Missing Key**:
```json
{
  "error": "Template rendering failed: Data key 'data.missing' not found. Available keys: ['existing']",
  "type": "ValueError"
}
```

**Non-dict Access**:
```json
{
  "error": "Template rendering failed: Cannot access 'field' in non-dict value at 'data.name.field'",
  "type": "ValueError"
}
```

### System Errors

**Trigger Not Found**:
```json
{
  "error": "Trigger template 'unknown' not found at: /path/to/triggers/unknown.md"
}
```

**Overlord Unavailable**:
```json
{
  "error": "Overlord not available"
}
```

## Security

### Authentication

All trigger endpoints require client key authentication:
```http
X-Client-Key: YOUR_CLIENT_KEY_HERE
```

### Formation Isolation

Triggers are formation-scoped:
- Each formation has its own `triggers/` directory
- Triggers cannot access other formations
- Formation ID must match the request

### Input Validation

- Template rendering validates data structure
- Missing keys result in clear error messages
- No code execution - only string substitution

## Best Practices

1. **Template Design**:
   - Keep templates focused and specific
   - Provide clear context in rendered messages
   - Include actionable instructions for the formation

2. **Data Structure**:
   - Use nested objects to organize related data
   - Keep key names descriptive and consistent
   - Document expected data shape for webhook integrations

3. **Error Handling**:
   - Test templates with sample data before deploying
   - Monitor trigger execution logs via observability
   - Set up alerts for failed trigger executions

4. **Performance**:
   - Use async mode for webhook integrations
   - Batch related events if possible
   - Monitor formation load and scale as needed

5. **Naming**:
   - Use descriptive trigger names (e.g., `github-issue-opened`)
   - Follow consistent naming conventions
   - Document trigger purpose and expected data

## Observability

All trigger executions emit observability events:

```python
# Trigger received
event_type: ConversationEvents.REQUEST_RECEIVED
data: {
    "trigger_name": "github-issue",
    "trigger_id": "trigger_abc123",
    "formation_id": "my-formation",
    ...
}

# Trigger completed
event_type: ConversationEvents.RESPONSE_COMPLETED
data: {
    "trigger_id": "trigger_abc123",
    ...
}

# Trigger failed
event_type: ConversationEvents.REQUEST_FAILED
data: {
    "trigger_id": "trigger_abc123",
    "error": "...",
    "error_type": "ValueError"
}
```

## Testing

### Manual Testing

```bash
# Test with curl
curl -X POST http://localhost:8271/v1/formations/test-formation/triggers/test-trigger \
  -H "X-Client-Key: YOUR_CLIENT_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "test": "value"
    },
    "use_async": false
  }'
```

### Unit Testing

See `tests/unit/test_trigger_rendering.py` for template rendering tests.

### Integration Testing

See `tests/e2e/` for full trigger flow tests.

## Limitations

- Templates use simple regex-based substitution (no Jinja2 features)
- No conditional logic in templates
- No loops or iteration over lists
- Formation-scoped only (not global)
- Requires client key authentication

## Future Enhancements

Potential future additions:
- Jinja2 template engine support
- Conditional rendering
- Loop support for lists
- Template validation tooling
- Trigger execution history API
- Rate limiting per trigger
- Trigger-specific permissions
