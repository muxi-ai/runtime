# A2A Registry System

This guide covers the A2A registry system that enables agent discovery across formations.

## Overview

The A2A registry is a central service that:
- Maintains a directory of available agents
- Enables agent discovery by capability
- Handles agent lifecycle (registration/deregistration)
- Provides health monitoring

## Registry Protocol

The registry implements the [A2A Protocol](https://a2a-protocol.org) specification.

### Endpoints

#### 1. Register Agent
```http
POST /register
Content-Type: application/json

{
  "id": "research-agent",
  "name": "Research Agent",
  "description": "Performs web research",
  "capabilities": ["web_search", "summarization"],
  "endpoint": "https://formation.example.com/agents/research-agent",
  "metadata": {
    "version": "1.0.0",
    "formation": "research-formation"
  }
}
```

**Response**:
```json
{
  "success": true,
  "agent_id": "research-agent",
  "registry_id": "reg_abc123"
}
```

#### 2. Deregister Agent
```http
DELETE /agents/{agent_id}
```

**Response**:
```json
{
  "success": true,
  "agent_id": "research-agent"
}
```

#### 3. Discover Agents
```http
GET /discover?capability=web_search&limit=10
```

**Response**:
```json
{
  "agents": [
    {
      "id": "research-agent",
      "name": "Research Agent",
      "description": "Performs web research",
      "capabilities": ["web_search", "summarization"],
      "endpoint": "https://formation.example.com/agents/research-agent"
    }
  ],
  "total": 1
}
```

#### 4. Health Check
```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "registry_version": "1.0.0",
  "agent_count": 42,
  "uptime_seconds": 3600
}
```

## Running a Registry

### Using MUXI's Registry Script

MUXI provides a reference registry implementation:

```bash
# Start registry on default port (9090)
python utils/a2a_registry.py

# Custom port
python utils/a2a_registry.py --port 8080

# With authentication
python utils/a2a_registry.py --auth-token "secret-token"
```

### Registry Features

The reference implementation includes:
- RESTful API following A2A spec
- In-memory storage (add persistence as needed)
- Health monitoring
- Optional authentication
- CORS support
- Request logging

### Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY utils/a2a_registry.py .
RUN pip install fastapi uvicorn

EXPOSE 9090
CMD ["python", "a2a_registry.py"]
```

```bash
docker build -t a2a-registry .
docker run -p 9090:9090 a2a-registry
```

## Formation Configuration

### Single Registry

```yaml
a2a:
  inbound:
    registries:
      - "https://registry.example.com"
  outbound:
    registries:
      - "https://registry.example.com"
```

### Multiple Registries

```yaml
a2a:
  inbound:
    registries:
      - "https://primary-registry.com"
      - "https://backup-registry.com"
  outbound:
    registries:
      - "https://primary-registry.com"
      - "https://backup-registry.com"
      - "https://partner-registry.com"
```

## Registry Client Operation

### Registration Process

1. **Formation Startup**:
   ```
   Formation Start
       ↓
   Initialize Agents
       ↓
   Create Agent Cards
       ↓
   Register with Each Registry
       ↓
   Track Registration Status
   ```

2. **Agent Card Creation**:
   ```python
   agent_card = {
       "id": agent.id,
       "name": agent.name,
       "description": agent.description,
       "capabilities": agent.capabilities,
       "endpoint": f"https://{host}:{port}/agents/{agent.id}"
   }
   ```

3. **Multi-Registry Registration**:
   - Attempts registration with each configured registry
   - Continues on failure (best effort)
   - Tracks which registries succeeded

### Discovery Process

1. **Query Strategy**:
   - Check local cache first
   - Query all configured registries
   - Merge and deduplicate results
   - Cache results with TTL

2. **Capability Matching**:
   ```python
   # Exact match
   GET /discover?capability=web_search
   
   # Multiple capabilities (OR)
   GET /discover?capability=web_search&capability=analysis
   
   # All agents
   GET /discover
   ```

### Deregistration Process

1. **Graceful Shutdown**:
   ```
   Shutdown Signal
       ↓
   Deregister from All Registries
       ↓
   Wait for Confirmation
       ↓
   Close Connections
   ```

2. **Automatic Cleanup**:
   - On formation shutdown
   - On agent removal
   - On kill signal (SIGTERM/SIGINT)

## Registry High Availability

### Load Balancing

Use a load balancer for registry HA:

```yaml
registries:
  - "https://registry-lb.example.com"  # Points to multiple instances
```

### Registry Federation

Registries can federate for broader discovery:

```
Registry A ←→ Registry B ←→ Registry C
     ↓            ↓            ↓
  Agents      Agents       Agents
```

### Health Monitoring

The client monitors registry health:

```python
# Automatic health checks
- Every 60 seconds
- Mark unhealthy after 3 failures
- Skip unhealthy registries
- Retry after recovery period
```

## Security Considerations

### Registry Authentication

Protect your registry endpoints:

```python
# Registry with bearer token
async def check_auth(request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != REGISTRY_TOKEN:
        raise HTTPException(401, "Unauthorized")
```

### Formation Authentication

Configure your formation to authenticate:

```yaml
# For registry operations
a2a:
  outbound:
    registry_auth:
      type: "bearer"
      token: "${{ secrets.REGISTRY_TOKEN }}"
```

### TLS/HTTPS

Always use HTTPS in production:

```yaml
registries:
  - "https://registry.example.com"  # Good
  # - "http://registry.example.com" # Avoid
```

## Advanced Topics

### Custom Registry Implementation

Implement the A2A registry protocol:

```python
from fastapi import FastAPI, HTTPException
from typing import Dict, List

app = FastAPI()
agents: Dict[str, dict] = {}

@app.post("/register")
async def register_agent(agent: dict):
    agents[agent["id"]] = agent
    return {"success": True, "agent_id": agent["id"]}

@app.delete("/agents/{agent_id}")
async def deregister_agent(agent_id: str):
    if agent_id in agents:
        del agents[agent_id]
        return {"success": True}
    raise HTTPException(404, "Agent not found")

@app.get("/discover")
async def discover_agents(capability: str = None):
    if capability:
        filtered = [a for a in agents.values() 
                   if capability in a.get("capabilities", [])]
    else:
        filtered = list(agents.values())
    return {"agents": filtered, "total": len(filtered)}
```

### Registry Persistence

Add persistence to the reference implementation:

```python
import sqlite3

class PersistentRegistry:
    def __init__(self, db_path="registry.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_db()
    
    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                data JSON,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

### Registry Plugins

Extend registry with plugins:

```python
class RegistryPlugin:
    async def on_register(self, agent_card: dict):
        """Called when agent registers"""
        pass
    
    async def on_deregister(self, agent_id: str):
        """Called when agent deregisters"""
        pass
    
    async def on_discover(self, query: dict, results: list):
        """Called on discovery, can modify results"""
        return results
```

### Monitoring and Metrics

Add observability to your registry:

```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics
registration_counter = Counter('a2a_registrations_total', 'Total registrations')
discovery_histogram = Histogram('a2a_discovery_duration_seconds', 'Discovery duration')
active_agents_gauge = Gauge('a2a_active_agents', 'Number of active agents')

@app.post("/register")
async def register_agent(agent: dict):
    registration_counter.inc()
    active_agents_gauge.inc()
    # ... rest of implementation
```

## Troubleshooting

### Common Issues

#### Registry Unreachable
```
Error: Failed to connect to registry at https://registry.example.com
```
**Solutions**:
- Check network connectivity
- Verify registry URL is correct
- Check firewall rules
- Verify registry is running

#### Registration Failures
```
Error: Failed to register agent: 409 Conflict
```
**Solutions**:
- Agent ID already registered
- Deregister first or use unique ID
- Check registry logs

#### Discovery Returns No Results
**Check**:
- Agents are registered
- Capability names match exactly
- Registry health status
- Network connectivity

### Debug Mode

Enable debug logging:

```yaml
logging:
  streams:
    - transport: "stdout"
      level: "debug"
      events:
        - "a2a.registry.*"
```

### Registry Logs

Check registry logs for issues:

```bash
# If using the reference implementation
python utils/a2a_registry.py --log-level DEBUG
```

## Best Practices

1. **Use Multiple Registries**: For redundancy
2. **Monitor Registry Health**: Set up alerts
3. **Secure Registry Access**: Use authentication
4. **Cache Discovery Results**: Reduce registry load
5. **Implement Retry Logic**: Handle transient failures
6. **Use HTTPS**: Always in production
7. **Version Your Agents**: Include version in metadata
8. **Regular Health Checks**: Detect issues early