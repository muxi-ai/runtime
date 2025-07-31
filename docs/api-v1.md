# Formation API v1

## Overview

This guide covers the Formation API endpoint structure with resource-based paths and authentication via API keys.

## Endpoint Structure

### Resource-Based URL Structure

All endpoints use clean resource-based paths with `/v1` prefix. Authentication determines access level:

### Formation Management Endpoints (require X-Muxi-Admin-Key)

| Resource | Path | Methods | Description |
|----------|------|---------|-------------|
| Config | `/v1/config` | GET | Full formation configuration |
| Status | `/v1/status` | GET | Formation status snapshot |
| Overlord | `/v1/overlord` | GET | Overlord configuration |
| Overlord | `/v1/overlord/persona` | GET | Overlord persona |
| Agents | `/v1/agents` | GET, POST | List and create agents |
| Agents | `/v1/agents/{agent_id}` | PATCH, DELETE | Update and delete agents |
| Secrets | `/v1/secrets` | GET, POST | List and create secrets |
| Secrets | `/v1/secrets/{key}` | PUT, DELETE | Update and delete secrets |
| MCP | `/v1/mcp` | GET, PATCH | MCP defaults configuration |
| MCP Servers | `/v1/mcp/servers` | GET, POST | List and create MCP servers |
| MCP Servers | `/v1/mcp/servers/{server_id}` | GET, PATCH, DELETE | Manage individual MCP servers |
| MCP Tools | `/v1/mcp/tools` | GET | List available MCP tools |
| MCP Tools | `/v1/mcp/tools/call` | POST | Execute MCP tools |
| LLM | `/v1/llm/settings` | GET, PATCH | LLM configuration |
| LLM | `/v1/llm/settings/{item}` | DELETE | Reset LLM settings |
| Logging | `/v1/logging` | GET | Logging configuration |
| Logging | `/v1/logging/streams/{name}` | PATCH | Update logging streams |
| Memory | `/v1/memory` | GET, PATCH | Memory configuration |
| Memory | `/v1/memory/{item}` | DELETE | Reset memory settings |
| Async | `/v1/async` | GET, PATCH | Async behavior settings |
| Scheduler | `/v1/scheduler` | GET, PATCH | Scheduler configuration |
| Scheduler | `/v1/scheduler/jobs/{id}` | DELETE | Remove scheduled jobs |
| A2A | `/v1/a2a` | GET | A2A configuration |
| A2A | `/v1/a2a/outbound` | PATCH | Update A2A outbound settings |
| A2A | `/v1/a2a/outbound/{item}` | DELETE | Reset A2A settings |

### User Interaction Endpoints (require X-Muxi-Client-Key)

| Resource | Path | Methods | Description |
|----------|------|---------|-------------|
| Chat | `/v1/chat` | POST | Send messages (with streaming) |
| Events | `/v1/events/{user_id}` | GET | SSE event stream |
| Jobs | `/v1/jobs/{user_id}` | GET | List async jobs |
| Jobs | `/v1/jobs/{user_id}/{job_id}` | DELETE | Cancel async jobs |
| Memories | `/v1/memories/{user_id}` | GET, POST | Get and create user memories |
| Memories | `/v1/memories/{user_id}/{memory_id}` | DELETE | Delete user memories |

### Public Endpoints (no authentication)

| Resource | Path | Methods | Description |
|----------|------|---------|-------------|
| Health | `/health` | GET | Server health check |

## API Usage Examples

### JavaScript/TypeScript
```javascript
// Admin operations (formation management)
const adminResponse = await fetch('/v1/agents', {
  method: 'GET',
  headers: {
    'X-Muxi-Admin-Key': adminKey,
    'Content-Type': 'application/json'
  }
});

// Client operations (user interactions)
const chatResponse = await fetch('/v1/chat', {
  method: 'POST',
  headers: {
    'X-Muxi-Client-Key': clientKey,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ message: "Hello!", user_id: "user123" })
});

// Create a secret (admin) - note: key will be normalized to uppercase
const secretResponse = await fetch('/v1/secrets', {
  method: 'POST',
  headers: {
    'X-Muxi-Admin-Key': adminKey,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ key: "new-api-key", value: "sk-1234567890" })
});

// Update secret - all these paths update the same secret
await fetch('/v1/secrets/new-api-key', { method: 'PUT', ... });
await fetch('/v1/secrets/NEW_API_KEY', { method: 'PUT', ... });
await fetch('/v1/secrets/new_api_key', { method: 'PUT', ... });
```

### Python
```python
import requests

# Admin operations
response = requests.get(
    f"{base_url}/v1/agents",
    headers={"X-Muxi-Admin-Key": admin_key}
)

# Client operations  
response = requests.post(
    f"{base_url}/v1/chat",
    headers={"X-Muxi-Client-Key": client_key},
    json={"message": "Hello!", "user_id": "user123"}
)

# Create a secret (admin) - note: key will be normalized to uppercase
response = requests.post(
    f"{base_url}/v1/secrets",
    headers={"X-Muxi-Admin-Key": admin_key},
    json={"key": "new-api-key", "value": "sk-1234567890"}
)

# Update secret - all these paths update the same secret
requests.put(f"{base_url}/v1/secrets/new-api-key", ...)
requests.put(f"{base_url}/v1/secrets/NEW_API_KEY", ...)
requests.put(f"{base_url}/v1/secrets/new_api_key", ...)
```

## Key Features

### 1. Resource-Based Design
- Clean, predictable URL structure
- RESTful HTTP methods (GET, POST, PATCH, DELETE)
- Consistent response envelope format

### 2. Dual Authentication System
- **Admin Key (`X-Muxi-Admin-Key`)**: Formation management
- **Client Key (`X-Muxi-Client-Key`)**: User interactions
- Case-insensitive header handling

### 3. Structured Response Format
All endpoints return consistent envelope format:
```json
{
  "object": "response_type",
  "timestamp": 1706616000000,
  "type": "event.type", 
  "request": {
    "id": "req_abc123",
    "idempotency_key": null
  },
  "success": true,
  "error": null,
  "data": {}
}
```

### 4. Streaming Support
- Server-Sent Events (SSE) for chat responses
- Real-time event streams for async job updates
- Bandwidth-optimized token streaming

### 5. Better URL Structure for Wrapping
When wrapped by multi-formation servers:
- **Clean**: `https://api.muxi.ai/v1/formation/{id}/agents`
- **Not verbose**: No redundant `/admin` or `/client` prefixes

## Configuration Management

### Secrets API

#### Key Features
- **Case-insensitive names**: Secret names are normalized to uppercase
- **Character normalization**: Non-alphanumeric characters replaced with underscores
- **Partial masking**: Response shows partial values for identification (e.g., `sk-pr••••••••hG8t`)
- **Usage protection**: Cannot delete secrets currently in use by formation

#### Name Normalization Examples
- `api-key`, `API_KEY`, `Api-Key` → all refer to `API_KEY`
- `my-secret-123` → `MY_SECRET_123`
- `user@email` → `USER_EMAIL`

#### Endpoints
- `GET /v1/secrets` - List all secrets with partially masked values
- `POST /v1/secrets` - Create new secret with JSON: `{"key": "...", "value": "..."}`
- `PUT /v1/secrets/{key}` - Update existing secret value
- `DELETE /v1/secrets/{key}` - Delete secret (blocked if in use)

#### Response Format
```json
{
  "secrets": {
    "OPENAI_API_KEY": "sk-pr••••••••hG8t",
    "DATABASE_URL": "postgresql://us••••••••5432"
  },
  "count": 2
}
```

### Resource Updates
- Use PATCH for partial updates (following REST semantics)
- Full resource retrieval with defaults filled
- Individual setting reset via DELETE

## Migration Notes

- All update operations now use PATCH instead of PUT
- Secret creation uses request body instead of path parameter
- MCP tools endpoints removed from public API (internal only)
- Case-insensitive header handling prevents client compatibility issues

## OpenAPI Specification

Full API documentation available in OpenAPI 3.0 format:
- Location: `/schemas/api/formation-api-v1-updated.yaml`
- Interactive docs: Available when server is running
- Complete endpoint definitions with request/response schemas

## Questions?

Contact the MUXI team for API support and integration assistance.