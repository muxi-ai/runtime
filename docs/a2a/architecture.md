# A2A Architecture Overview

## System Design

The A2A (Agent-to-Agent) communication system in MUXI Runtime follows a layered architecture that separates concerns and provides clean abstractions.

## Architecture Layers

### 1. Agent Layer
The top layer where agents interact with A2A functionality through simple APIs.

**Location**: `src/muxi/formation/agents/agent.py`

**Key Methods**:
- `send_a2a_message()` - Send messages to other agents
- `handle_a2a_message()` - Receive and process incoming messages
- `process_message()` - Business logic for handling messages

**Design Principle**: Agents should focus on business logic, not communication protocols.

### 2. Service Layer
The middle layer that provides A2A services to agents while abstracting protocol details.

**Location**: `src/muxi/services/a2a/`

**Components**:
- `client.py` - A2A service singleton for message sending
- `server.py` - HTTP server for receiving external A2A messages
- `registry_client.py` - Client for external registry operations
- `discovery.py` - Agent discovery mechanisms
- `auth/` - Authentication subsystem

**Design Principle**: All A2A protocol logic lives here, not in agents.

### 3. SDK Layer
The bottom layer that handles A2A protocol compliance using the official SDK.

**Dependencies**:
- `a2a-sdk` - Official A2A SDK v0.3.0
- Protocol types and message formats
- HTTP transport implementation

**Design Principle**: Use SDK for all protocol operations to ensure compliance.

## Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Agent Layer                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Agent A   │  │   Agent B   │  │   Agent C   │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                 │                 │               │
│         └─────────────────┴─────────────────┘               │
│                           │                                 │
├───────────────────────────┼─────────────────────────────────┤
│                    Service Layer                            │
│                           │                                 │
│  ┌────────────────────────▼────────────────────────┐       │
│  │              A2A Service (Singleton)             │       │
│  │                                                  │       │
│  │  ┌─────────────┐  ┌──────────────┐             │       │
│  │  │   Router    │  │ SDK Client   │             │       │
│  │  │             │  │              │             │       │
│  │  │ - Internal  │  │ - Send Msg   │             │       │
│  │  │ - External  │  │ - Format     │             │       │
│  │  └─────────────┘  └──────────────┘             │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ A2A Server   │  │  Registry    │  │ Discovery    │     │
│  │              │  │  Client      │  │              │     │
│  │ - HTTP API   │  │              │  │ - Local      │     │
│  │ - Auth       │  │ - Register   │  │ - External   │     │
│  │ - Handler    │  │ - Discover   │  │ - Unified    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                         SDK Layer                           │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │               A2A SDK v0.3.0                       │    │
│  │                                                    │    │
│  │  - Protocol Types (Message, AgentCard, etc.)      │    │
│  │  - HTTP Transport                                 │    │
│  │  - Authentication                                 │    │
│  │  - Registry Protocol                              │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. A2A Coordinator
**Location**: `src/muxi/formation/overlord/a2a_coordinator.py`

Manages A2A lifecycle for the formation:
- Initializes A2A server and registry client
- Handles agent registration/deregistration
- Manages external registry connections
- Provides discovery APIs

### 2. A2A Service (Singleton)
**Location**: `src/muxi/services/a2a/client.py`

Central service for all A2A operations:
- Routes messages internally or externally
- Manages SDK client instance
- Handles format conversions
- Provides unified messaging API

### 3. A2A Server
**Location**: `src/muxi/services/a2a/server.py`

HTTP server for receiving external messages:
- FastAPI-based implementation
- SDK-compatible endpoints
- Authentication middleware
- Message routing to agents

### 4. Registry Client
**Location**: `src/muxi/services/a2a/registry_client.py`

Manages external registry interactions:
- Agent registration/deregistration
- Discovery operations
- Health monitoring
- Multi-registry support

### 5. Unified Transport
**Location**: `src/muxi/formation/overlord/unified_a2a_messaging.py`

Provides transparent message routing:
- Automatic internal/external routing
- Transport hint support
- Fallback mechanisms
- Error handling

## Data Flow

### Internal A2A Message Flow
```
Agent A → A2A Service → Router → Agent B (same formation)
```

### External A2A Message Flow
```
Agent A → A2A Service → SDK Client → HTTP → Remote A2A Server → Agent B
```

### Discovery Flow
```
Agent → Discovery Service → Local Cache → Registry Client → External Registry
```

## Design Decisions

### 1. Service Layer Abstraction
**Decision**: Agents use service layer, not SDK directly

**Rationale**: 
- Keeps agents simple and focused
- Centralizes protocol logic
- Easier SDK upgrades
- Consistent error handling

### 2. Singleton A2A Service
**Decision**: One A2A service instance per runtime

**Rationale**:
- Centralized message routing
- Shared SDK client
- Consistent state management
- Resource efficiency

### 3. SDK-Based Implementation
**Decision**: Use official A2A SDK for all protocol operations

**Rationale**:
- Protocol compliance guaranteed
- Reduced maintenance burden
- Future compatibility
- Community support

### 4. Transport Abstraction
**Decision**: Support multiple transports (agent://, http://, https://)

**Rationale**:
- Flexible deployment options
- Performance optimization
- Backward compatibility
- Future extensibility

## Security Architecture

### Authentication Layers
1. **Formation API Keys** - For client access to formation
2. **A2A Authentication** - For inter-formation communication
3. **Transport Security** - HTTPS for external communication

### Trust Model
- Internal agents trust each other (same formation)
- External agents require authentication
- Registry operations require authentication
- Configurable authentication methods

## Performance Considerations

### Caching
- Discovery results cached for efficiency
- Registry responses cached with TTL
- Authentication results cached

### Connection Pooling
- HTTP client connection pooling
- Persistent registry connections
- Efficient resource usage

### Async Operations
- All A2A operations are async
- Non-blocking message handling
- Concurrent request support

## Extensibility Points

### 1. Custom Transports
Add new transport protocols by implementing transport interface

### 2. Authentication Methods
Extend authentication with new methods (OAuth, mTLS, etc.)

### 3. Message Formats
Support additional message formats while maintaining compatibility

### 4. Discovery Mechanisms
Add new discovery sources (DNS, Consul, etc.)

## Future Enhancements

1. **Message Queue Integration** - Support for async messaging
2. **Circuit Breakers** - Resilience for external communication
3. **Metrics and Tracing** - Enhanced observability
4. **Load Balancing** - Multiple instances of same agent
5. **Message Encryption** - End-to-end encryption support