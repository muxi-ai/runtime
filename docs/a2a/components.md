# A2A Components Guide

This guide provides detailed documentation for each component in the A2A system.

## Core Components

### 1. Agent (A2A Methods)
**Location**: `src/muxi/formation/agents/agent.py`

#### Methods

##### `send_a2a_message(agent_id, message, context=None, metadata=None)`
Sends a message to another agent (internal or external).

**Parameters**:
- `agent_id` (str): Target agent ID, can include formation hint (e.g., "agent@formation")
- `message` (str): The message content
- `context` (dict, optional): Additional context data
- `metadata` (dict, optional): Message metadata

**Returns**: Response from target agent or error

**Example**:
```python
response = await self.send_a2a_message(
    agent_id="research-agent",
    message="Find information about quantum computing",
    context={"max_results": 5}
)
```

##### `handle_a2a_message(message)`
Handles incoming A2A messages.

**Parameters**:
- `message` (dict): Incoming message in A2A format

**Returns**: Response to send back

**Internal Flow**:
1. Validates message format
2. Extracts content and context
3. Calls `process_message()` for business logic
4. Formats and returns response

### 2. A2A Service (Client)
**Location**: `src/muxi/services/a2a/client.py`

Singleton service providing A2A functionality to agents.

#### Key Attributes
- `sdk_client`: A2A SDK client instance
- `_internal_handlers`: Registry of internal message handlers

#### Methods

##### `initialize(config)`
Initializes the A2A service with configuration.

##### `send_message(from_agent, to_agent, message, context)`
Sends a message using appropriate transport.

**Internal Logic**:
1. Determines if message is internal or external
2. For internal: Direct handler invocation
3. For external: SDK client usage
4. Handles format conversions

##### `register_handler(agent_id, handler)`
Registers an internal message handler for an agent.

### 3. A2A Server
**Location**: `src/muxi/services/a2a/server.py`

FastAPI server for receiving external A2A messages.

#### Configuration
```python
A2AServer(
    overlord=overlord_instance,
    port=8181,
    host="0.0.0.0",
    auth_mode="bearer",
    shared_key="secret_key",
    formation_name="my-formation"
)
```

#### Endpoints

##### `GET /health`
Health check endpoint.

**Response**:
```json
{
    "status": "healthy",
    "formation": "my-formation",
    "agents": ["agent1", "agent2"],
    "sdk_version": "0.3.0",
    "protocol": "a2a-sdk"
}
```

##### `GET /agents`
List available agents for A2A communication.

**Response**:
```json
{
    "agents": [
        {
            "id": "agent-1",
            "name": "Research Agent",
            "description": "Handles research tasks",
            "capabilities": ["web_search", "summarization"]
        }
    ]
}
```

##### `POST /agents/{agent_id}/message`
Send message to specific agent.

**Request Body**:
```json
{
    "message": {
        "parts": [
            {"type": "text", "text": "Hello agent"}
        ]
    },
    "context": {}
}
```

##### `GET /agents/{agent_id}`
Get specific agent information.

#### Authentication
Supports multiple authentication methods:
- Bearer token
- API key
- Basic auth
- Custom headers

### 4. Registry Client
**Location**: `src/muxi/services/a2a/registry_client.py`

Manages communication with external A2A registries.

#### Methods

##### `register_agent(agent_card)`
Registers an agent with external registries.

**Parameters**:
- `agent_card`: AgentCard object with agent information

**Process**:
1. Converts to SDK format
2. Attempts registration with each registry
3. Tracks successful registrations
4. Handles failures gracefully

##### `deregister_agent(agent_id)`
Removes agent from all registries.

##### `discover_agents(query)`
Discovers agents from registries.

**Parameters**:
- `query` (str): Search query or capability

**Returns**: List of discovered agents

##### `check_health()`
Monitors registry health status.

### 5. A2A Coordinator
**Location**: `src/muxi/formation/overlord/a2a_coordinator.py`

Orchestrates A2A operations for the formation.

#### Responsibilities
- Initialize A2A server on formation startup
- Register agents with external registries
- Handle deregistration on shutdown
- Provide discovery APIs
- Manage A2A configuration

#### Key Methods

##### `startup()`
Initializes A2A subsystem:
1. Starts A2A server if configured
2. Connects to external registries
3. Registers formation agents

##### `shutdown()`
Cleanly shuts down A2A:
1. Deregisters all agents
2. Stops A2A server
3. Closes registry connections

##### `get_available_agents_for_a2a(requesting_agent_id, capability_filter)`
Returns agents available for A2A communication.

### 6. Authentication System
**Location**: `src/muxi/services/a2a/auth/`

#### Inbound Authenticator
**File**: `inbound.py`

Handles authentication for incoming A2A requests.

**Supported Methods**:
- **Bearer**: Token in Authorization header
- **API Key**: Key in X-API-Key header
- **Basic**: Username/password
- **Custom**: Arbitrary headers

**Configuration**:
```yaml
inbound:
  auth:
    type: "bearer"
    token: "${{ secrets.A2A_TOKEN }}"
```

#### Outbound Authenticator
**File**: `outbound.py`

Adds authentication to outgoing requests.

**Service-Specific Auth**:
```yaml
outbound:
  services:
    - service_id: "partner-api"
      auth:
        type: "api_key"
        key: "${{ secrets.PARTNER_KEY }}"
        header: "X-Partner-Key"
```

### 7. Discovery Service
**Location**: `src/muxi/services/a2a/discovery.py`

Provides unified agent discovery across internal and external sources.

#### Discovery Sources
1. **Local Agents**: Same formation
2. **Registry Cache**: Recently discovered
3. **External Registries**: Live lookup

#### Caching Strategy
- Cache duration: 5 minutes
- Background refresh
- Fallback to cache on registry failure

### 8. Models and Adapters
**Location**: `src/muxi/services/a2a/models.py`, `models_adapter.py`

#### Models
Internal MUXI data models:
- `AgentCard`: Agent information
- `A2AMessage`: Message format
- `AgentCapability`: Capability definition

#### Models Adapter
Converts between MUXI and SDK formats:

```python
# MUXI to SDK
sdk_agent = ModelsAdapter.to_sdk_agent_card(muxi_agent)

# SDK to MUXI  
muxi_agent = ModelsAdapter.from_sdk_agent_card(sdk_agent)
```

### 9. Agent Transport
**Location**: `src/muxi/services/a2a/agent_transport.py`

Custom transport for internal agent communication.

**URL Format**: `agent://agent-id`

**Benefits**:
- Zero network overhead
- Direct memory access
- Synchronous execution
- No serialization cost

### 10. Cache Manager
**Location**: `src/muxi/services/a2a/cache_manager.py`

Manages discovery and response caching.

#### Features
- TTL-based expiration
- Memory-efficient storage
- Thread-safe operations
- Automatic cleanup

## Component Interactions

### Message Send Flow
```
Agent.send_a2a_message()
    ↓
A2AService.send_message()
    ↓
Router.determine_transport()
    ├─ Internal: AgentTransport
    └─ External: SDK Client → HTTP
```

### Message Receive Flow
```
HTTP Request → A2A Server
    ↓
Authentication Check
    ↓
Route to Agent
    ↓
Agent.handle_a2a_message()
    ↓
Process and Return Response
```

### Discovery Flow
```
Agent Request
    ↓
Discovery Service
    ├─ Check Local Agents
    ├─ Check Cache
    └─ Query Registries
        ↓
    Merge and Return Results
```

## Configuration Integration

Each component reads configuration from the formation YAML:

```yaml
a2a:
  enabled: true
  
  inbound:
    enabled: true
    port: 8181
    auth:
      type: "bearer"
      token: "secret"
  
  outbound:
    enabled: true
    registries:
      - "https://registry.example.com"
    services:
      - service_id: "external-api"
        auth:
          type: "api_key"
          key: "api-secret"
```

Components automatically configure themselves based on these settings during initialization.