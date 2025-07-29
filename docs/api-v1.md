# Formation API v1

## Overview

This guide covers the changes made to the Formation API endpoint structure for cleaner URLs and better organization.

## Endpoint Changes

### Simplified URL Structure

All endpoints now use resource-based paths without admin/client prefixes. Authentication is handled via API keys:

### Formation Management Endpoints (require X-Admin-Key)

| Resource | Path | Description |
|----------|------|-------------|
| Agents | `/v1/agents` | List, create, update, delete agents |
| Secrets | `/v1/secrets` | Manage secrets |
| MCP | `/v1/mcp` | MCP configuration |
| MCP Servers | `/v1/mcp/servers` | Manage MCP servers |
| MCP Tools | `/v1/mcp/tools/*` | Execute MCP tools |

### User Interaction Endpoints (require X-Client-Key)

| Resource | Path | Description |
|----------|------|-------------|
| Chat | `/v1/chat` | Send messages |
| Events | `/v1/events/{user_id}` | SSE event stream |
| Jobs | `/v1/jobs/{user_id}` | Manage async jobs |
| Memories | `/v1/memories/{user_id}` | Manage user memories |

### Unchanged Endpoints

- Health endpoints remain at `/health` and `/status` (no version prefix)
- Admin endpoints remain at `/v1/admin/*`

## Authentication Changes

### MCP Endpoints
- **Before**: No authentication required
- **After**: Requires `X-Admin-Key` header (same as other admin endpoints)

## Client Code Updates

### JavaScript/TypeScript
```javascript
// Before
const response = await fetch('/v1/api/chat', {
  method: 'POST',
  headers: {
    'X-Client-Key': clientKey,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ message, user_id })
});

// After
const response = await fetch('/v1/client/chat', {
  method: 'POST',
  headers: {
    'X-Client-Key': clientKey,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ message, user_id })
});
```

### Python
```python
# Before
response = requests.post(
    f"{base_url}/v1/api/chat",
    headers={"X-Client-Key": client_key},
    json={"message": message, "user_id": user_id}
)

# After
response = requests.post(
    f"{base_url}/v1/client/chat",
    headers={"X-Client-Key": client_key},
    json={"message": message, "user_id": user_id}
)
```

## Rationale

1. **Cleaner URLs**: Resource-based paths without redundant prefixes
   - Before: `/v1/formation/{id}/admin/mcp/tools`
   - After: `/v1/formation/{id}/mcp/tools`

2. **Authentication-based Access**: API keys determine permissions, not URL paths
   - Admin endpoints require `X-Admin-Key`
   - Client endpoints require `X-Client-Key`

3. **Better for Wrapping**: Simpler paths when wrapped by server managing multiple formations

## Timeline

- Update your integrations to use the new endpoints
- Old endpoints have been removed in this version

## Questions?

Contact the MUXI team if you need assistance with the migration.
