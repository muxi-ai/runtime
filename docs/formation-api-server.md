# Formation API Server

The Formation API Server is a FastAPI-based HTTP server that exposes MUXI formation capabilities via REST API endpoints. It provides both administrative operations (formation management) and client operations (user interactions) through a dual-key authentication system.

## Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                 Formation API Server                   │
├────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Health       │  │ Admin        │  │ Client       │  │
│  │ Routes       │  │ Routes       │  │ Routes       │  │
│  │              │  │              │  │              │  │
│  │ /health      │  │ /v1/*        │  │ /v1/*        │  │
│  │ /status      │  │ (admin key)  │  │ (client key) │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Authentication & Security Layer                  │  │
│  │ • Dual API Key System (Admin/Client)             │  │
│  │ • Thread-safe operations                         │  │
│  │ • Secret masking in logs                         │  │
│  │ • Asyncio-safe signal handling                   │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ MUXI Formation Core                              │  │
│  │ • Configuration Management                       │  │
│  │ • Overlord Integration                           │  │
│  │ • Memory Systems                                 │  │
│  │ • MCP Integration                                │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

## Quick Start

> **Note:** Formation config files support three extensions (in priority order): `.afs` (Agent Formation Schema - preferred), `.yaml`, and `.yml`.

### 1. Configuration

Add a `server` section to your formation config file:

```yaml
# formation.yaml
schema: "1.0.0"
id: "my-api-formation"

server:
  host: "0.0.0.0"      # Default: 0.0.0.0
  port: 3000           # Default: 3000
  api_keys:
    admin_key: "${{ secrets.FORMATION_ADMIN_API_KEY }}"
    client_key: "${{ secrets.FORMATION_CLIENT_API_KEY }}"

# Your overlord and agents configuration...
overlord:
  # ... overlord config
```

### 2. Start the Server

```python
from muxi import Formation

async def main():
    # Load formation
    formation = Formation()
    await formation.load("my-formation.yaml")

    # Start server (auto-starts overlord if needed)
    server = formation.start_server()

# Run the server
import asyncio
asyncio.run(main())
```

### 3. API Usage

```bash
# Health check (no auth required)
curl http://localhost:3000/health

# List agents (admin key required)
curl -H "X-Muxi-Admin-Key: sk_muxi_admin_..." http://localhost:3000/v1/agents

# Chat with formation (client key required)
curl -X POST \
  -H "X-Muxi-Client-Key: sk_muxi_client_..." \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "user_id": "user123"}' \
  http://localhost:3000/v1/chat

# Create a secret (admin key required)
curl -X POST \
  -H "X-Muxi-Admin-Key: sk_muxi_admin_..." \
  -H "Content-Type: application/json" \
  -d '{"key": "NEW_API_KEY", "value": "secret_value"}' \
  http://localhost:3000/v1/secrets
```

## Authentication System

The Formation API uses a dual-key authentication system:

### Admin Key (`X-Muxi-Admin-Key`)
- **Purpose**: Formation management operations
- **Endpoints**: `/v1/*` (admin operations)
- **Capabilities**:
  - Add/remove/update agents
  - Manage secrets and configuration
  - MCP server management
  - LLM, logging, memory, scheduler settings
  - A2A configuration
  - Server administration

### Client Key (`X-Muxi-Client-Key`)
- **Purpose**: User interactions
- **Endpoints**: `/v1/*` (client operations)
- **Capabilities**:
  - Chat with formation
  - Memory operations
  - Async job management
  - User-specific operations

### Auto-Generated Keys (Development)

If no API keys are provided, the server auto-generates them:

```
⚠️  AUTO-GENERATED API KEYS - DEVELOPMENT ONLY
═══════════════════════════════════════════════════════════
🔒 The following API keys were automatically generated
   because none were provided in your formation configuration.

⚠️  WARNING: This is NOT recommended for production use!
   Please configure proper API keys in your formation.yaml

📋 Generated API Keys:
   Admin API Key:  sk_muxi_admin_xyz123...
   Client API Key: sk_muxi_client_abc456...
```

## API Endpoints

### Health & Status
- `GET /health` - Server health check
- `GET /status` - Server status information

### Admin Operations (require `X-Muxi-Admin-Key`)
- `GET /v1/config` - Full formation configuration
- `GET /v1/status` - Formation status snapshot
- `GET /v1/overlord` - Overlord configuration
- `GET /v1/overlord/persona` - Overlord persona
- `GET /v1/agents` - List all agents
- `POST /v1/agents` - Add new agent
- `PATCH /v1/agents/{agent_id}` - Update agent
- `DELETE /v1/agents/{agent_id}` - Remove agent
- `GET /v1/secrets` - List secrets (masked values)
- `POST /v1/secrets` - Create secret (JSON body)
- `PUT /v1/secrets/{key}` - Update secret
- `DELETE /v1/secrets/{key}` - Delete secret
- `GET /v1/mcp` - MCP defaults configuration
- `PATCH /v1/mcp` - Update MCP defaults
- `GET /v1/mcp/servers` - List MCP servers
- `POST /v1/mcp/servers` - Create MCP server
- `GET /v1/mcp/servers/{server_id}` - Get MCP server
- `PATCH /v1/mcp/servers/{server_id}` - Update MCP server
- `DELETE /v1/mcp/servers/{server_id}` - Delete MCP server
- `GET /v1/mcp/tools` - List available MCP tools
- `POST /v1/mcp/tools/call` - Execute MCP tool
- `GET /v1/llm/settings` - LLM configuration
- `PATCH /v1/llm/settings` - Update LLM settings
- `DELETE /v1/llm/settings/{item}` - Reset LLM setting
- `GET /v1/logging` - Logging configuration
- `PATCH /v1/logging/streams/{name}` - Update logging stream
- `GET /v1/memory` - Memory configuration
- `PATCH /v1/memory` - Update memory configuration
- `DELETE /v1/memory/{item}` - Reset memory setting
- `GET /v1/async` - Async behavior settings
- `PATCH /v1/async` - Update async settings
- `GET /v1/scheduler` - Scheduler configuration
- `PATCH /v1/scheduler` - Update scheduler
- `DELETE /v1/scheduler/jobs/{id}` - Remove scheduled job
- `GET /v1/a2a` - A2A configuration
- `PATCH /v1/a2a/outbound` - Update A2A outbound settings
- `DELETE /v1/a2a/outbound/{item}` - Reset A2A setting

### Client Operations (require `X-Muxi-Client-Key`)
- `POST /v1/chat` - Send message to formation (with SSE streaming)
- `GET /v1/events/{user_id}` - SSE stream for async updates
- `GET /v1/jobs/{user_id}` - List async jobs
- `DELETE /v1/jobs/{user_id}/{job_id}` - Cancel job
- `GET /v1/memories/{user_id}` - Get user memories
- `POST /v1/memories/{user_id}` - Create user memory
- `DELETE /v1/memories/{user_id}/{memory_id}` - Delete memory

## Server Management

### Starting the Server

#### Blocking Mode (Default)
```python
# Blocks until server is stopped
server = formation.start_server()
```

#### Non-blocking Mode
```python
# Returns awaitable for proper error handling
try:
    server = await formation.start_server(block=False)
    print("Server started successfully!")
except Exception as e:
    print(f"Server startup failed: {e}")
```

### Server Instance Management

The Formation class tracks server instances to prevent conflicts:

```python
# Check if server is running
if formation.is_server_running():
    print("Server is already running")

# Starting a second server raises an error
try:
    formation.start_server()  # Will raise RuntimeError
except RuntimeError as e:
    print(f"Error: {e}")  # "A Formation server is already running..."
```

### Graceful Shutdown

```python
# Stop server gracefully
await server.stop()

# Or stop entire formation (includes server)
formation.stop()
```

## Client Libraries & SDKs

### Python Client Example

```python
import httpx
import json

class FormationClient:
    def __init__(self, base_url: str, client_key: str):
        self.base_url = base_url
        self.headers = {
            "X-Muxi-Client-Key": client_key,
            "Content-Type": "application/json"
        }

    async def chat(self, message: str, user_id: str = None):
        async with httpx.AsyncClient() as client:
            payload = {"message": message}
            if user_id:
                payload["user_id"] = user_id
            response = await client.post(
                f"{self.base_url}/v1/chat",
                json=payload,
                headers=self.headers
            )
            return response.json()

# Usage
client = FormationClient("http://localhost:3000", "sk_muxi_client_...")
response = await client.chat("Hello, MUXI!")
```

### JavaScript/TypeScript Client

```typescript
class FormationClient {
    constructor(
        private baseUrl: string,
        private clientKey: string
    ) {}

    async chat(message: string, userId?: string): Promise<any> {
        const headers: Record<string, string> = {
            'X-Muxi-Client-Key': this.clientKey,
            'Content-Type': 'application/json'
        };

        if (userId) {
            headers['X-User-Id'] = userId;
        }

        const payload = { message };
        if (userId) {
            payload.user_id = userId;
        }
        
        const response = await fetch(`${this.baseUrl}/v1/chat`, {
            method: 'POST',
            headers,
            body: JSON.stringify(payload)
        });

        return response.json();
    }
}

// Usage
const client = new FormationClient('http://localhost:3000', 'sk_muxi_client_...');
const response = await client.chat('Hello, MUXI!');
```

## Security Features

### API Key Security
- **Constant-time comparison**: Prevents timing attacks
- **Secure generation**: Uses `secrets` module for cryptographically secure randomness
- **Masked logging**: API keys never appear in observability logs

### Secret Management
- **Consistent masking**: All secrets show as `••••••••` in API responses
- **No length disclosure**: Masking doesn't reveal secret length information
- **Secure storage**: Integration with Formation's secrets manager

### Thread Safety
- **Config modifications**: Thread-safe with proper locking
- **Concurrent requests**: Safe handling of simultaneous API calls
- **Resource management**: Proper cleanup and state management

## Advanced Configuration

### Server Configuration Options

```yaml
server:
  host: "127.0.0.1"    # Bind to localhost only
  port: 8080           # Custom port

  # API Keys (production)
  api_keys:
    admin_key: "${{ secrets.FORMATION_ADMIN_API_KEY }}"
    client_key: "${{ secrets.FORMATION_CLIENT_API_KEY }}"

# Optional: CORS settings, SSL, etc. (future enhancements)
```

### Observability Integration

The server emits structured observability events:

```python
# Server startup
{
    "event_type": "server.started",
    "service": "formation_api_server",
    "host": "0.0.0.0",
    "port": 3000,
    "formation_id": "my-formation",
    "endpoints_count": 15
}

# Chat request
{
    "event_type": "conversation.request_received",
    "service": "formation_api_server",
    "endpoint": "/api/chat",
    "user_id": "user123",
    "session_id": "sess456",
    "agent_id": "my-agent"
}
```

## Error Handling

### Common Error Responses

```json
{
    "detail": "Invalid admin API key",
    "status_code": 403
}
```

```json
{
    "detail": "Agent 'nonexistent' not found",
    "status_code": 404
}
```

```json
{
    "detail": "A Formation server is already running. Stop the existing server before starting a new one.",
    "status_code": 500
}
```

### Client-Side Error Handling

```python
import httpx

async def robust_chat(client, message):
    try:
        response = await client.post("/api/chat", json={"message": message})
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            print("Authentication failed - check your client key")
        elif e.response.status_code == 503:
            print("Overlord not available - formation may not be started")
        else:
            print(f"API error: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        print(f"Connection error: {e}")
```

## Performance Considerations

### Async Architecture
- **Non-blocking I/O**: FastAPI with async/await throughout
- **Concurrent requests**: Handles multiple simultaneous API calls
- **Streaming responses**: Server-sent events for real-time updates

### Resource Management
- **Connection pooling**: Efficient HTTP connection handling
- **Memory management**: Proper cleanup of resources
- **Background tasks**: Async job processing without blocking

### Scaling Recommendations
- **Reverse proxy**: Use nginx or similar for production
- **Load balancing**: Multiple Formation instances with shared state
- **API rate limiting**: Implement rate limiting for production use

## Troubleshooting

### Common Issues

#### Server Won't Start
```
RuntimeError: A Formation server is already running
```
**Solution**: Check if server is running with `formation.is_server_running()` and stop it first.

#### Authentication Errors
```
403 Forbidden: Invalid admin API key
```
**Solution**: Verify API keys in formation.yaml and check header format (`X-Muxi-Admin-Key` vs `X-Muxi-Client-Key`).

#### Overlord Not Available
```
503 Service Unavailable: Overlord not available
```
**Solution**: Ensure `formation.start_overlord()` was called before starting the server.

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Start server with verbose output
server = formation.start_server()
```

### Health Checks

Monitor server health:

```bash
# Basic health check
curl http://localhost:3000/health

# Detailed status (if implemented)
curl http://localhost:3000/status
```

## Roadmap & Future Enhancements

### Near-term (Next Release)
- [ ] Rate limiting and request throttling
- [ ] WebSocket support for real-time bidirectional communication
- [ ] Batch API operations
- [ ] Enhanced MCP routing with load balancing

### Medium-term
- [ ] SSL/TLS configuration
- [ ] API versioning support
- [ ] OpenAPI 3.1 spec generation
- [ ] Prometheus metrics integration

### Long-term
- [ ] GraphQL endpoint alternative
- [ ] Plugin system for custom endpoints
- [ ] Distributed formation clustering
- [ ] Advanced caching strategies

## Contributing

The Formation API Server is part of the MUXI Runtime project. For development:

1. **Setup**: Follow the main MUXI development setup
2. **Testing**: Run formation API tests with `pytest tests/api/`
3. **Linting**: Ensure code quality with `flake8` and `pyright`
4. **Documentation**: Update this doc when adding new features

### Code Structure

```
src/muxi/formation/server/
├── server.py          # Main FormationServer class
├── auth.py            # Authentication dependencies
├── middleware.py      # Request/response middleware
├── responses.py       # Response utilities
├── utils.py           # Helper utilities
└── routes/
    ├── health.py      # Health & status endpoints
    ├── admin/         # Admin management endpoints
    │   ├── agents.py  # Agent management
    │   ├── secrets.py # Secret management
    │   ├── config.py  # Configuration endpoints
    │   ├── overlord.py # Overlord endpoints
    │   ├── mcp.py     # MCP management
    │   ├── llm.py     # LLM settings
    │   ├── logging.py # Logging configuration
    │   ├── memory.py  # Memory configuration
    │   ├── async_routes.py # Async settings
    │   ├── scheduler.py # Scheduler configuration
    │   └── a2a.py     # A2A configuration
    └── client/        # Client interaction endpoints
        ├── chat.py    # Chat endpoints
        ├── events.py  # SSE event streams
        ├── jobs.py    # Async job management
        └── memory.py  # User memory management
```

---

*This documentation reflects the current state of the Formation API Server as of the latest development session. For the most up-to-date information, refer to the source code and test files.*
