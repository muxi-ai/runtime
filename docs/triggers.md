# Trigger System

**Philosophy**: Triggers are requests. They use the same patterns, responses, and IDs as any other request in MUXI.

The trigger system provides a webhook-friendly interface for external systems to initiate formation actions through template-based message generation.

## Core Concept

Triggers = **Webhook-Friendly Requests**

```
Webhook JSON → Template Rendering → Chat Message → Standard Request Processing
```

The only difference between triggers and regular requests is **where the message comes from**:
- Regular `/chat`: User provides message directly
- Triggers: Template + data → rendered message

Everything else (authentication, processing, responses, IDs) is identical.

## Quick Start

### 1. Create a Trigger Template

Create `formations/my-formation/triggers/github-issue.md`:

```markdown
New GitHub issue from ${{ data.repository }}:

**Issue #${{ data.issue.number }}**: ${{ data.issue.title }}
**Author**: ${{ data.issue.author }}

Please analyze and suggest next steps.
```

### 2. Send a Trigger Request

```bash
curl -X POST http://localhost:8271/v1/formations/my-formation/triggers/github-issue \
  -H "X-Muxi-Client-Key: YOUR_CLIENT_KEY" \
  -H "X-Muxi-User-Id: webhook-user" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "repository": "muxi/runtime",
      "issue": {
        "number": 123,
        "title": "Bug in login flow",
        "author": "alice"
      }
    },
    "use_async": true
  }'
```

### 3. Receive Standard API Response

```json
{
  "object": "request",
  "timestamp": 1706616000000,
  "type": "request.processing",
  "request": {
    "id": "req_abc123",
    "idempotency_key": null
  },
  "success": true,
  "error": null,
  "data": {
    "status": "processing"
  }
}
```

## API Reference

### Execute Trigger

```http
POST /v1/formations/{formation_id}/triggers/{trigger_name}
```

**Headers** (Required):
- `X-Muxi-Client-Key`: Client API key
- `X-Muxi-User-Id`: User ID (optional, defaults to "0")

**Request Body**:
```json
{
  "data": {
    // Event data for template rendering
  },
  "session_id": "optional-session-id",
  "use_async": true  // or false for synchronous
}
```

**Response (Async - default)**:
```json
{
  "object": "request",
  "type": "request.processing",
  "request": {"id": "req_abc123"},
  "success": true,
  "data": {"status": "processing"}
}
```

**Response (Sync)**:
```json
{
  "object": "request",
  "type": "request.completed",
  "request": {"id": "req_abc123"},
  "success": true,
  "data": {
    "status": "completed",
    "response": "LLM's full response text here..."
  }
}
```

### List Triggers

```http
GET /v1/formations/{formation_id}/triggers
```

**Response**:
```json
{
  "object": "list",
  "type": "list.retrieved",
  "request": {"id": "req_xyz789"},
  "success": true,
  "data": {
    "formation_id": "my-formation",
    "triggers": ["github-issue", "linear-ticket"],
    "count": 2
  }
}
```

## Template Syntax

Templates use `${{ data.* }}` for data substitution:

### Simple Access
```markdown
Hello ${{ data.name }}!
```
Data: `{"name": "World"}` → Result: `Hello World!`

### Nested Access
```markdown
Issue #${{ data.issue.number }}: ${{ data.issue.title }}
```
Data: `{"issue": {"number": 123, "title": "Bug"}}` → Result: `Issue #123: Bug`

### Multi-Level Nesting
```markdown
User: ${{ data.user.profile.name }}
```
Data: `{"user": {"profile": {"name": "Alice"}}}` → Result: `User: Alice`

## Processing Modes

### Async Mode (Default, Recommended for Webhooks)

```json
{
  "data": {...},
  "use_async": true
}
```

- Returns immediately with `request_id`
- Processes in background
- Non-blocking for webhook caller
- **Best for webhook integrations**

### Sync Mode (For Interactive Use)

```json
{
  "data": {...},
  "use_async": false
}
```

- Waits for LLM completion
- Returns full response text
- Blocks until complete
- **Use for testing or interactive scenarios**

Note: Triggers **never stream** - they return complete responses.

## Example Templates

### GitHub Issue

**File**: `triggers/github-issue.md`
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

**Request**:
```bash
curl -X POST http://localhost:8271/v1/formations/my-formation/triggers/github-issue \
  -H "X-Muxi-Client-Key: YOUR_CLIENT_KEY" \
  -H "X-Muxi-User-Id: github-webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "repository": "muxi/runtime",
      "issue": {
        "number": 456,
        "title": "Memory leak in overlord",
        "author": "bob",
        "state": "open",
        "labels": "bug, critical",
        "body": "Observing gradual memory increase over 24 hours..."
      }
    }
  }'
```

### Linear Ticket

**File**: `triggers/linear-ticket.md`
```markdown
Linear ticket update from ${{ data.team }}:

**Ticket**: ${{ data.ticket.identifier }}
**Title**: ${{ data.ticket.title }}
**Status**: ${{ data.ticket.status }}
**Priority**: ${{ data.ticket.priority }}

**Action**: ${{ data.action }}

Please review and suggest next steps.
```

### Deployment Notification

**File**: `triggers/deployment-notification.md`
```markdown
Deployment to ${{ data.environment }}:

**Service**: ${{ data.service }}
**Version**: ${{ data.version }}
**Status**: ${{ data.status }}
**Deployed by**: ${{ data.deployer }}

**Changes**: ${{ data.changes }}

**Health Checks**:
- API: ${{ data.health.api }}
- Database: ${{ data.health.database }}

Please monitor and report any anomalies.
```

## Error Handling

Triggers use standard API error responses:

### Missing Template Data

```json
{
  "object": "error",
  "type": "error.validation",
  "request": {"id": "req_err123"},
  "success": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Template rendering failed: Data key 'data.issue.number' not found. Available keys: ['title', 'author']"
  }
}
```

### Trigger Not Found

```json
{
  "object": "error",
  "type": "error.not_found",
  "request": {"id": "req_err456"},
  "success": false,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Trigger template 'unknown' not found at: /path/to/triggers/unknown.md"
  }
}
```

## Authentication

All trigger endpoints require:
- **`X-Muxi-Client-Key`**: Client API key (required)
- **`X-Muxi-User-Id`**: User ID for multi-user isolation (optional, defaults to "0")

## Formation Isolation

- Triggers are formation-scoped
- Each formation has its own `triggers/` directory
- No cross-formation access
- Formation ID validated on every request

## Best Practices

### 1. Template Design
- Keep templates focused and specific
- Provide clear context for the LLM
- Include actionable instructions
- Use nested data for organization

### 2. Async for Webhooks
```json
{"use_async": true}  // ✅ Best for webhooks
```
Webhooks expect fast acknowledgment, not long-lived connections.

### 3. Naming Conventions
- Use descriptive names: `github-issue-opened` not `gh-1`
- Follow consistent patterns across triggers
- Document expected data structure

### 4. Error Monitoring
- Monitor trigger executions via observability
- Set up alerts for failed triggers
- Log webhook payloads for debugging

### 5. Testing
```bash
# Test with sample data before deploying webhook
curl -X POST .../triggers/my-trigger \
  -H "X-Muxi-Client-Key: test_key" \
  -d '{"data": {...}, "use_async": false}'  # Sync for testing
```

## Observability

All trigger executions emit standard request events:

```python
# Request received
event_type: ConversationEvents.REQUEST_RECEIVED
data: {"request_id": "req_abc123", "trigger_name": "github-issue", ...}

# Request completed
event_type: ConversationEvents.RESPONSE_COMPLETED
data: {"request_id": "req_abc123", ...}

# Request failed
event_type: ConversationEvents.REQUEST_FAILED
data: {"request_id": "req_abc123", "error": "...", ...}
```

Track triggers like any other request using `request_id`.

## Webhook Integration Examples

### GitHub Webhook

1. **Create trigger template** in your formation
2. **Configure GitHub webhook**:
   - URL: `https://your-muxi.com/v1/formations/my-formation/triggers/github-issue`
   - Content type: `application/json`
   - Secret: Use for HMAC validation (implement in middleware)
   - Events: Issues, Pull requests, etc.

3. **Transform GitHub payload** (optional middleware):
```javascript
// Middleware to transform GitHub webhook to trigger format
app.post('/github-webhook', (req, res) => {
  const triggerPayload = {
    data: {
      repository: req.body.repository.full_name,
      issue: {
        number: req.body.issue.number,
        title: req.body.issue.title,
        author: req.body.issue.user.login,
        state: req.body.issue.state,
        body: req.body.issue.body
      }
    }
  };
  
  // Forward to MUXI trigger
  fetch('http://localhost:8271/v1/formations/my-formation/triggers/github-issue', {
    method: 'POST',
    headers: {
      'X-Muxi-Client-Key': process.env.MUXI_CLIENT_KEY,
      'X-Muxi-User-Id': 'github-webhook',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(triggerPayload)
  });
  
  res.status(200).send('OK');
});
```

### Linear Webhook

Similar pattern - transform Linear webhook payload to match your trigger template's expected data structure.

## Limitations

- Templates use simple regex substitution (no Jinja2)
- No conditional logic in templates (LLM handles that)
- No loops or iteration
- Formation-scoped only (not global)

## Why No Jinja2?

Triggers are for **data transformation**, not logic:
- Simple patterns are more secure
- Templates stay declarative
- LLM handles the "intelligence" part
- Easier to debug and maintain

If you need conditional logic, handle it in the LLM response, not the template.

## Workflow Approvals

Triggers automatically **bypass workflow approvals** regardless of complexity threshold. This is intentional because:

1. **Webhooks are already automated** - the triggering system made the decision
2. **No one to approve** - webhooks are fire-and-forget, not interactive
3. **Manual approval doesn't make sense** - if you want approval, build it into the external system before calling the trigger

If a trigger's request would normally require manual approval (high complexity score), it will be executed automatically without waiting for approval.

**For regular chat requests**, you can also bypass workflow approval programmatically:

```python
await overlord.chat(
    message="Complex task that would normally require approval",
    bypass_workflow_approval=True  # Skip approval for automated scenarios
)
```

This is useful for:
- Automated scripts
- Scheduled tasks
- Internal system operations
- Any scenario where manual approval doesn't make sense

## Comparison with /chat

| Feature | /chat | /triggers/{name} |
|---------|-------|------------------|
| Message source | Request body | Template + data |
| Response type | SSE stream (sync) or job (async) | Complete response (no streaming) |
| User ID | Header or body | Header only |
| Use case | Interactive chat | Webhook integration |
| Authentication | Same (X-Muxi-Client-Key) | Same |
| Response format | Standard API envelope | Standard API envelope |
| Request ID | Standard (req_*) | Standard (req_*) |

Both are requests - triggers are just webhook-optimized.

## FAQ

**Q: Why don't triggers stream responses?**
A: Webhooks expect quick acknowledgment, not long-lived SSE connections. Use async mode for webhooks.

**Q: Can I use triggers for interactive chat?**
A: You can, but `/chat` is better suited. Triggers are optimized for webhooks.

**Q: Do triggers have different rate limits?**
A: No - triggers are requests. They use the same rate limiting as `/chat`.

**Q: Can I get the trigger execution status later?**
A: Yes - use the `request_id` with request status endpoints (when implemented).

**Q: Why use X-Muxi-User-Id header instead of body?**
A: Consistency - all MUXI API endpoints use this pattern. Keeps request bodies focused on domain data.

## Summary

Triggers = Webhook-friendly requests that:
1. Render templates with event data
2. Process like any other request
3. Return standard API responses
4. Use the same authentication and IDs
5. Appear in the same observability logs

**Remember**: If you're doing something special for triggers, you're probably doing it wrong. Triggers should use the same code paths as regular requests.
