# MUXI MCP API Reference

**🔧 Complete API Reference for Production MCP Integration**

This document provides a comprehensive reference for MUXI's production-ready MCP implementation.

## 🚀 MCPService

The main service class for MCP operations. Uses singleton pattern for thread-safe operations.

### Getting Started

```python
from muxi.services.mcp.service import MCPService

# Get the singleton instance
service = MCPService.get_instance()
```

## Server Management

### `register_mcp_server()`

Register a new MCP server with intelligent auto-detection.

```python
async def register_mcp_server(
    self,
    server_id: str,
    url: Optional[str] = None,
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    working_directory: Optional[str] = None,
    transport_type: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    request_timeout: Optional[int] = None
) -> str
```

**Examples**:

```python
# HTTP server with auto-detection
await service.register_mcp_server(
    server_id="api_server",
    url="http://localhost:8002/mcp"
)

# Command-line server
await service.register_mcp_server(
    server_id="filesystem",
    command="npx @modelcontextprotocol/server-filesystem /tmp"
)

# Authenticated server
await service.register_mcp_server(
    server_id="secure_api",
    url="https://api.example.com/mcp",
    headers={"Authorization": "Bearer token"},
    request_timeout=30
)
```

### `disconnect_server()`

```python
await service.disconnect_server("server_id")
```

### `reconnect_server()`

```python
success = await service.reconnect_server("server_id")
```

## Tool Operations

### `invoke_tool()`

Execute a tool on an MCP server.

```python
async def invoke_tool(
    self,
    server_id: str,
    tool_name: str,
    parameters: Optional[Dict[str, Any]] = None,
    request_timeout: Optional[int] = None
) -> Dict[str, Any]
```

**Result Format**:
```python
{
    "status": "success" | "error",
    "result": Any,  # Tool result (if successful)
    "error": str,   # Error message (if failed)
    "metadata": {
        "execution_time": float,
        "server_id": str,
        "tool_name": str
    }
}
```

**Example**:
```python
result = await service.invoke_tool(
    server_id="filesystem",
    tool_name="list_directory",
    parameters={"path": "/tmp"},
    request_timeout=10
)

if result["status"] == "success":
    files = result["result"]["content"]
    print(f"Found {len(files)} files")
else:
    print(f"Error: {result['error']}")
```

### `list_tools()`

```python
tools = await service.list_tools("server_id")
for tool_name, schema in tools.items():
    print(f"Tool: {tool_name} - {schema.get('description', 'N/A')}")
```

## Resource Operations

### `list_resources()`

```python
resources = await service.list_resources("server_id")
```

### `read_resource()`

```python
content = await service.read_resource(
    server_id="content_server",
    uri="file:///path/to/document.txt"
)
```

## Monitoring & Diagnostics

### `health_check()`

```python
is_healthy = await service.health_check("server_id")
```

### `get_connection_info()`

```python
info = service.get_connection_info("server_id")
print(f"Transport: {info['transport_type']}")
print(f"Status: {info['status']}")
print(f"Requests: {info['request_count']}")
```

### `get_transport_cache_stats()`

```python
stats = service.get_transport_cache_stats()
print(f"Cache hits: {stats['hits']}")
print(f"Hit ratio: {stats['hit_ratio']:.2%}")
```

## Error Handling

### Exception Classes

```python
from muxi.services.mcp.base import (
    MCPConnectionError,
    MCPTimeoutError,
    MCPRequestError,
    MCPConfigurationError
)
```

### Error Handling Pattern

```python
try:
    result = await service.invoke_tool(
        server_id="api_server",
        tool_name="process_data",
        parameters={"data": "example"}
    )

    if result["status"] == "success":
        return result["result"]
    else:
        logging.error(f"Tool failed: {result['error']}")

except MCPConnectionError as e:
    logging.error(f"Connection failed: {e}")
    await service.reconnect_server(e.server_id)

except MCPTimeoutError as e:
    logging.warning(f"Operation timed out: {e}")

except MCPRequestError as e:
    logging.error(f"Request failed: {e}")
```

## Properties

### `active_servers`

```python
for server_id in service.active_servers:
    print(f"Active server: {server_id}")
```

### `tool_registry`

```python
for server_id, tools in service.tool_registry.items():
    print(f"Server {server_id} has {len(tools)} tools")
```

## Advanced Usage

### Concurrent Operations

```python
# Register multiple servers concurrently
tasks = [
    service.register_mcp_server("server1", url="http://localhost:8001/mcp"),
    service.register_mcp_server("server2", url="http://localhost:8002/mcp"),
    service.register_mcp_server("server3", command="npx server3")
]

results = await asyncio.gather(*tasks, return_exceptions=True)
```

### Health Monitoring

```python
async def monitor_servers():
    for server_id in service.active_servers:
        try:
            is_healthy = await service.health_check(server_id)
            if not is_healthy:
                await service.reconnect_server(server_id)
        except Exception as e:
            logging.error(f"Health check failed: {e}")
```

### Performance Optimization

```python
# Use transport caching (enabled by default)
stats = service.get_transport_cache_stats()
if stats['hit_ratio'] < 0.8:
    # Consider optimizing server registration patterns
    pass

# Clear cache if needed
service.clear_transport_cache()
```

---

This API reference covers the essential methods for integrating with MUXI's production-ready MCP implementation. All methods are fully tested and production-ready with comprehensive error handling and performance optimization.
