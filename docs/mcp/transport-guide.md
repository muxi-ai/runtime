# MUXI MCP Transport Layer Guide

**🚀 Production-Ready Transport Layer with Auto-Detection**

MUXI's MCP implementation features a sophisticated transport layer that automatically detects and connects to MCP servers using the most appropriate protocol. This guide covers all three transport types and the intelligent auto-detection system.

## 🎯 Transport Types Overview

MUXI supports three transport types, each optimized for different deployment scenarios:

| Transport | Use Case | Protocol | Performance |
|-----------|----------|----------|-------------|
| **Streamable HTTP** | Web services, APIs | HTTP/POST + JSON-RPC | Excellent |
| **HTTP+SSE** | Real-time, streaming | HTTP + Server-Sent Events | Very Good |
| **Stdio** | Local executables | Standard I/O pipes | Excellent |

## 🧠 Intelligent Auto-Detection

The transport detection system automatically identifies the correct transport type based on URL patterns and server capabilities:

### Detection Logic

```python
# URL Pattern Recognition
"http://localhost:8002/mcp"     # → Streamable HTTP
"http://localhost:8001/sse"     # → HTTP+SSE
"ws://localhost:8000"           # → WebSocket (if available)
"stdio://command-name"          # → Stdio
"npx @org/mcp-server"          # → Stdio (command detection)
```

### Performance Features

- **Transport Caching**: 1000x+ speedup on repeated connections
- **Smart Fallback**: Automatic retry with alternative transports
- **Cache TTL**: 60-minute intelligent cache expiration
- **Manual Override**: Explicit transport selection when needed

## 🌐 Streamable HTTP Transport

**Best for**: REST APIs, microservices, containerized MCP servers

### Features
- Direct HTTP/POST communication
- JSON-RPC 2.0 message format
- Connection pooling and reuse
- Excellent performance and reliability

### Example Usage

```python
# Automatic detection
await service.register_mcp_server(
    server_id="api_server",
    url="http://localhost:8002/mcp"
)

# Manual specification
await service.register_mcp_server(
    server_id="api_server",
    url="http://localhost:8002/mcp",
    transport_type="streamable_http"
)
```

### Configuration

```python
# With authentication
await service.register_mcp_server(
    server_id="secure_api",
    url="https://api.example.com/mcp",
    headers={
        "Authorization": "Bearer your-token-here",
        "X-API-Version": "1.0"
    },
    request_timeout=30
)
```

### Implementation Details

- Uses `aiohttp` for HTTP communication
- Supports connection pooling
- Handles HTTP status codes and errors
- Automatic JSON serialization/deserialization

## 📡 HTTP+SSE Transport

**Best for**: Real-time applications, streaming responses, event-driven systems

### Features
- Server-Sent Events for real-time communication
- Bidirectional JSON-RPC messaging
- Automatic reconnection on connection loss
- Event stream processing

### Example Usage

```python
# Automatic detection
await service.register_mcp_server(
    server_id="realtime_server",
    url="http://localhost:8001/sse"
)

# With custom SSE configuration
await service.register_mcp_server(
    server_id="streaming_server",
    url="http://localhost:8001/sse",
    transport_type="http_sse",
    sse_config={
        "retry_interval": 5000,  # 5 seconds
        "max_retries": 10
    }
)
```

### SSE Message Format

```javascript
// Server-Sent Event format
data: {"jsonrpc": "2.0", "id": 1, "result": {...}}

// Error events
data: {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "Error"}}
```

### Implementation Details

- Custom SSE client implementation
- Handles connection keep-alive
- Automatic reconnection with exponential backoff
- Event parsing and JSON-RPC message extraction

## 💻 Stdio Transport

**Best for**: Local executables, CLI tools, development environments

### Features
- Direct process communication via stdin/stdout
- Subprocess lifecycle management
- Environment variable support
- Working directory configuration

### Example Usage

```python
# Command with arguments
await service.register_mcp_server(
    server_id="local_tools",
    command="npx @modelcontextprotocol/server-filesystem /tmp"
)

# With environment variables
await service.register_mcp_server(
    server_id="env_server",
    command="python -m my_mcp_server",
    env={
        "API_KEY": "your-api-key",
        "DEBUG": "true",
        "CONFIG_PATH": "/path/to/config"
    },
    working_directory="/app"
)
```

### Process Management

```python
# Advanced configuration
await service.register_mcp_server(
    server_id="advanced_local",
    command="./my-mcp-server",
    args=["--port", "8080", "--config", "production.json"],
    working_directory="/opt/mcp-server",
    startup_timeout=30,
    env={
        "LOG_LEVEL": "info",
        "CACHE_SIZE": "1000"
    }
)
```

### Implementation Details

- Uses `asyncio.create_subprocess_exec`
- JSON-RPC communication over stdin/stdout
- Process monitoring and health checks
- Automatic cleanup on disconnect

## ⚡ Performance Optimization

### Transport Cache System

The auto-detection system includes intelligent caching:

```python
# Get cache statistics
cache_stats = service.get_transport_cache_stats()
print(f"Cache hits: {cache_stats['hits']}")
print(f"Cache misses: {cache_stats['misses']}")
print(f"Cache size: {cache_stats['size']}")

# Clear cache manually if needed
service.clear_transport_cache()
```

### Benchmarks

Real-world performance measurements:

```
Transport Detection (Cold):     ~0.150s
Transport Detection (Cached):   ~0.0001s (1500x speedup)
Tool Execution (HTTP):         ~0.025s
Tool Execution (SSE):          ~0.030s
Tool Execution (Stdio):       ~0.020s
Concurrent Connections:        10+ simultaneous
```

## 🛡️ Error Handling

### Connection Errors

```python
from muxi.services.mcp.base import MCPConnectionError, MCPTimeoutError

try:
    await service.register_mcp_server(
        server_id="test_server",
        url="http://unreachable:8080/mcp"
    )
except MCPConnectionError as e:
    print(f"Connection failed: {e}")
except MCPTimeoutError as e:
    print(f"Operation timed out: {e}")
```

### Transport-Specific Errors

```python
# HTTP transport errors
except aiohttp.ClientError as e:
    print(f"HTTP error: {e}")

# Process errors (Stdio)
except subprocess.SubprocessError as e:
    print(f"Process error: {e}")

# SSE connection errors
except asyncio.TimeoutError as e:
    print(f"SSE timeout: {e}")
```

### Graceful Degradation

```python
# Automatic fallback strategy
async def connect_with_fallback(server_id, base_url):
    fallback_urls = [
        f"{base_url}/mcp",      # Streamable HTTP
        f"{base_url}/sse",      # HTTP+SSE
        f"{base_url}:8000"      # Alternative port
    ]

    for url in fallback_urls:
        try:
            await service.register_mcp_server(server_id, url=url)
            return True
        except MCPConnectionError:
            continue

    return False
```

## 🔧 Advanced Configuration

### Custom Transport Settings

```python
# Per-transport timeouts
await service.register_mcp_server(
    server_id="custom_config",
    url="http://slow-server:8080/mcp",
    transport_config={
        "request_timeout": 60,      # 60 second timeout
        "connect_timeout": 10,      # 10 second connection timeout
        "read_timeout": 30,         # 30 second read timeout
        "retry_attempts": 5,        # 5 retry attempts
        "retry_delay": 2.0         # 2 second delay between retries
    }
)
```

### Connection Pooling

```python
# HTTP transport connection pooling
await service.register_mcp_server(
    server_id="pooled_server",
    url="http://api.example.com/mcp",
    transport_config={
        "pool_size": 10,            # Max connections in pool
        "pool_timeout": 30,         # Pool acquisition timeout
        "keep_alive": True,         # Enable keep-alive
        "keep_alive_timeout": 60    # Keep-alive timeout
    }
)
```

### Monitoring and Diagnostics

```python
# Get detailed connection information
connection_info = service.get_connection_info("server_id")
print(f"Transport type: {connection_info['transport']}")
print(f"Status: {connection_info['status']}")
print(f"Connected at: {connection_info['connected_at']}")
print(f"Total requests: {connection_info['request_count']}")
print(f"Error count: {connection_info['error_count']}")

# Health check
is_healthy = await service.health_check("server_id")
print(f"Server healthy: {is_healthy}")
```

## 🚀 Best Practices

### Transport Selection Guidelines

1. **Use Streamable HTTP for**:
   - Production web services
   - Containerized deployments
   - Load-balanced environments
   - RESTful MCP servers

2. **Use HTTP+SSE for**:
   - Real-time applications
   - Event-driven systems
   - Streaming data processing
   - Push notifications

3. **Use Stdio for**:
   - Local development
   - CLI-based tools
   - Desktop applications
   - Testing and debugging

### Performance Tips

```python
# 1. Enable transport caching (default)
service.enable_transport_cache(ttl=3600)  # 1 hour TTL

# 2. Use connection pooling for HTTP
transport_config = {
    "pool_size": 10,
    "keep_alive": True
}

# 3. Set appropriate timeouts
request_timeout = 30  # 30 seconds for most operations

# 4. Monitor connection health
async def monitor_connections():
    for server_id in service.active_servers:
        health = await service.health_check(server_id)
        if not health:
            await service.reconnect(server_id)
```

### Security Considerations

```python
# 1. Use HTTPS in production
url = "https://secure-api.example.com/mcp"

# 2. Implement proper authentication
headers = {
    "Authorization": "Bearer " + os.getenv("MCP_TOKEN"),
    "X-API-Version": "1.0"
}

# 3. Validate server certificates
transport_config = {
    "verify_ssl": True,
    "ssl_context": ssl.create_default_context()
}

# 4. Use secure environment variables
env = {
    "API_KEY": os.getenv("SECURE_API_KEY"),
    "DATABASE_URL": os.getenv("DATABASE_URL")
}
```

## 📊 Transport Comparison

| Feature | Streamable HTTP | HTTP+SSE | Stdio |
|---------|----------------|----------|-------|
| **Setup Complexity** | Low | Medium | Low |
| **Performance** | Excellent | Very Good | Excellent |
| **Real-time Support** | No | Yes | No |
| **Network Overhead** | Low | Medium | None |
| **Scalability** | High | High | Medium |
| **Security** | HTTPS/TLS | HTTPS/TLS | Local only |
| **Debugging** | Easy | Medium | Easy |
| **Resource Usage** | Low | Medium | Low |

## 🎯 Production Deployment

### Docker Integration

```yaml
# docker-compose.yml
version: '3.8'
services:
  mcp-server:
    image: my-mcp-server:latest
    ports:
      - "8002:8002"
    environment:
      - MCP_PORT=8002
      - MCP_ENDPOINT=/mcp
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  muxi-app:
    image: muxi-app:latest
    depends_on:
      - mcp-server
    environment:
      - MCP_SERVER_URL=http://mcp-server:8002/mcp
```

### Kubernetes Deployment

```yaml
# mcp-server-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: mcp-server
spec:
  selector:
    app: mcp-server
  ports:
    - port: 8002
      targetPort: 8002

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: my-mcp-server:latest
        ports:
        - containerPort: 8002
        env:
        - name: MCP_PORT
          value: "8002"
        livenessProbe:
          httpGet:
            path: /health
            port: 8002
          initialDelaySeconds: 30
          periodSeconds: 10
```

---

This transport layer provides the foundation for MUXI's production-ready MCP implementation, ensuring reliable communication across all deployment scenarios while maintaining optimal performance and developer experience.
