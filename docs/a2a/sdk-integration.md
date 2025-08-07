# A2A SDK Integration Guide

This guide documents how MUXI Runtime integrates with the official A2A SDK v0.3.0.

## SDK Overview

The A2A SDK provides protocol-compliant implementations for agent-to-agent communication.

### Key SDK Components

```python
from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest,
    SendMessageResponse, 
    Message,
    TextPart,
    DataPart,
    AgentCard,
    Role
)
```

## Architecture Philosophy

### Service Layer Pattern

MUXI uses a service layer pattern where agents don't directly use the SDK:

```
Agent → A2A Service → SDK → Network
```

**Benefits**:
- Agents remain simple and focused
- SDK changes don't affect agents
- Centralized error handling
- Consistent abstractions

### Why Not Direct SDK Usage?

1. **Separation of Concerns**: Agents focus on business logic
2. **Protocol Abstraction**: Hide protocol details from agents
3. **Easier Testing**: Mock service layer, not SDK
4. **Migration Path**: Change SDK without touching agents

## SDK Integration Points

### 1. A2A Client Initialization
**Location**: `src/muxi/services/a2a/client.py`

```python
# SDK client initialization
import httpx
from a2a.client import A2AClient

# Create httpx client (required by SDK)
httpx_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0),
    follow_redirects=True,
)

# Initialize SDK client
sdk_client = A2AClient(
    httpx_client=httpx_client,
    url="https://registry.example.com"
)
```

### 2. Message Sending
**Location**: `src/muxi/services/a2a/client.py`

```python
# Convert MUXI format to SDK format
from a2a.types import SendMessageRequest, Message, TextPart, DataPart

# MUXI format
muxi_message = {
    "message": "Hello agent",
    "context": {"key": "value"}
}

# Convert to SDK format
sdk_message = Message(
    parts=[
        TextPart(text=muxi_message["message"]),
        DataPart(data=muxi_message["context"])
    ]
)

# Send via SDK
request = SendMessageRequest(
    agent_id="target-agent",
    message=sdk_message
)
response = await sdk_client.send_message(request)
```

### 3. Registry Operations
**Location**: `src/muxi/services/a2a/registry_client.py`

```python
# Agent registration
from a2a.types import AgentCard

agent_card = AgentCard(
    id="my-agent",
    name="My Agent",
    description="Does something useful",
    capabilities=["research", "analysis"]
)

await sdk_client.register(agent_card)

# Agent discovery
agents = await sdk_client.discover("research")
```

## Type Conversions

### Models Adapter
**Location**: `src/muxi/services/a2a/models_adapter.py`

The adapter converts between MUXI and SDK types:

```python
class ModelsAdapter:
    @staticmethod
    def to_sdk_agent_card(muxi_agent: Dict) -> AgentCard:
        """Convert MUXI agent format to SDK AgentCard"""
        return AgentCard(
            id=muxi_agent["id"],
            name=muxi_agent.get("name", muxi_agent["id"]),
            description=muxi_agent.get("description", ""),
            capabilities=muxi_agent.get("capabilities", [])
        )
    
    @staticmethod
    def from_sdk_agent_card(sdk_card: AgentCard) -> Dict:
        """Convert SDK AgentCard to MUXI format"""
        return {
            "id": sdk_card.id,
            "name": sdk_card.name,
            "description": sdk_card.description,
            "capabilities": sdk_card.capabilities,
            "type": "external",
            "transport": "http"
        }
```

### Message Format Conversion

```python
# MUXI internal format
muxi_message = {
    "from_agent": "agent-a",
    "to_agent": "agent-b", 
    "message": "Hello",
    "context": {"data": "value"}
}

# SDK format
sdk_message = Message(
    parts=[
        TextPart(text="Hello"),
        DataPart(data={"data": "value"})
    ]
)

# Conversion utilities
def to_sdk_message(muxi_msg: Dict) -> Message:
    parts = []
    if "message" in muxi_msg:
        parts.append(TextPart(text=muxi_msg["message"]))
    if "context" in muxi_msg:
        parts.append(DataPart(data=muxi_msg["context"]))
    return Message(parts=parts)
```

## SDK Usage Patterns

### 1. Singleton Service Pattern

```python
class A2AService:
    """Singleton service wrapping SDK"""
    
    def __new__(cls):
        if not hasattr(cls, '_instance'):
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.sdk_client = None
            self._initialized = True
    
    async def initialize(self, config):
        """Initialize SDK client once"""
        if self.sdk_client is None:
            self.sdk_client = A2AClient(...)
```

### 2. Graceful Degradation

```python
async def send_external_message(self, ...):
    """Send with fallback on SDK failure"""
    try:
        # Try SDK first
        response = await self.sdk_client.send_message(...)
        return response
    except SDKException:
        # Fall back to direct HTTP if needed
        return await self._direct_http_fallback(...)
```

### 3. Multi-Registry Support

```python
class RegistryClient:
    """Support multiple registries via SDK"""
    
    def __init__(self, registries: List[str]):
        self.sdk_clients = {}
        for registry_url in registries:
            client = A2AClient(
                httpx_client=self._create_httpx_client(),
                url=registry_url
            )
            self.sdk_clients[registry_url] = client
    
    async def discover_all(self, capability: str):
        """Discover from all registries"""
        all_agents = []
        for client in self.sdk_clients.values():
            try:
                agents = await client.discover(capability)
                all_agents.extend(agents)
            except Exception:
                continue  # Skip failed registry
        return all_agents
```

## Migration from Direct HTTP

### Before (Direct HTTP)
```python
# Old direct HTTP approach
async def register_agent(self, agent_info):
    response = await httpx.post(
        f"{self.registry_url}/register",
        json=agent_info
    )
    return response.json()
```

### After (SDK)
```python
# New SDK approach
async def register_agent(self, agent_info):
    agent_card = ModelsAdapter.to_sdk_agent_card(agent_info)
    await self.sdk_client.register(agent_card)
```

## Error Handling

### SDK Exceptions

The SDK raises specific exceptions that we handle:

```python
from a2a.exceptions import (
    A2AException,
    RegistrationError,
    DiscoveryError,
    MessageError
)

try:
    await sdk_client.send_message(request)
except MessageError as e:
    # Handle message-specific errors
    logger.error(f"Failed to send message: {e}")
except A2AException as e:
    # Handle general A2A errors
    logger.error(f"A2A operation failed: {e}")
```

### Timeout Handling

```python
# Configure timeout at client creation
httpx_client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=5.0,      # Connection timeout
        read=30.0,        # Read timeout
        write=10.0,       # Write timeout
        pool=5.0          # Pool timeout
    )
)
```

## Performance Optimization

### Connection Pooling

The SDK uses httpx which provides connection pooling:

```python
# Reuse connections across requests
httpx_client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_keepalive_connections=20,
        max_connections=100,
        keepalive_expiry=30.0
    )
)
```

### Async Operations

All SDK operations are async for efficiency:

```python
# Parallel operations
async def discover_multiple(capabilities: List[str]):
    tasks = [
        sdk_client.discover(cap) 
        for cap in capabilities
    ]
    results = await asyncio.gather(*tasks)
    return results
```

## Testing with SDK

### Mock SDK for Testing

```python
# tests/mocks/mock_a2a_sdk.py
class MockA2AClient:
    """Mock SDK client for testing"""
    
    async def send_message(self, request):
        # Return mock response
        return SendMessageResponse(
            success=True,
            message_id="mock_123"
        )
    
    async def register(self, agent_card):
        # Mock registration
        pass
```

### Integration Tests

```python
# tests/integration/test_a2a_sdk.py
async def test_sdk_message_flow():
    """Test real SDK integration"""
    # Use real SDK with test registry
    client = A2AClient(
        httpx_client=httpx.AsyncClient(),
        url="http://test-registry:9090"
    )
    
    # Test actual protocol flow
    response = await client.send_message(...)
    assert response.success
```

## SDK Configuration

### Environment Variables

```python
# SDK configuration from environment
import os

SDK_CONFIG = {
    "registry_url": os.getenv("A2A_REGISTRY_URL"),
    "timeout": int(os.getenv("A2A_TIMEOUT", "30")),
    "max_retries": int(os.getenv("A2A_MAX_RETRIES", "3"))
}
```

### Formation Configuration

```yaml
# Map formation config to SDK config
a2a:
  outbound:
    registries:
      - "https://registry.example.com"
    default_timeout_seconds: 30
    default_retry_attempts: 3
```

## Future SDK Features

### Planned SDK v0.4.0 Features

1. **Streaming Support**: For large responses
2. **Batch Operations**: Multiple messages in one call
3. **WebSocket Transport**: Real-time communication
4. **Metrics API**: Built-in observability

### Preparing for Updates

Structure code to minimize SDK version impact:

```python
# Version-specific imports
try:
    from a2a.v4 import StreamingClient
    HAS_STREAMING = True
except ImportError:
    HAS_STREAMING = False

# Conditional features
if HAS_STREAMING:
    # Use new streaming API
else:
    # Fall back to standard API
```

## Best Practices

### 1. Always Use Service Layer
```python
# Good: Agent uses service
await self.send_a2a_message(...)

# Bad: Agent uses SDK directly
await sdk_client.send_message(...)
```

### 2. Handle SDK Unavailability
```python
if self.sdk_client is None:
    # SDK not initialized, use fallback
    return await self._internal_only_mode(...)
```

### 3. Log SDK Operations
```python
observability.observe(
    event_type="a2a.sdk.operation",
    data={
        "operation": "send_message",
        "agent_id": agent_id,
        "duration_ms": duration
    }
)
```

### 4. Version Compatibility
```python
# Check SDK version
from a2a import __version__ as sdk_version

if sdk_version < "0.3.0":
    raise RuntimeError("A2A SDK 0.3.0+ required")
```