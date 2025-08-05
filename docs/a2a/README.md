# Agent-to-Agent (A2A) Communication Architecture

## Overview

The Agent-to-Agent (A2A) communication system in MUXI Runtime enables agents to collaborate both within a single formation (internal A2A) and across different formations (external A2A). The system is built on the [A2A Protocol](https://a2a-protocol.org) and uses the official A2A SDK for protocol compliance.

## Table of Contents

1. [Architecture Overview](architecture.md) - High-level system design
2. [Components Guide](components.md) - Detailed component documentation
3. [Message Flow](message-flow.md) - How messages travel between agents
4. [Authentication](authentication.md) - Security and authentication mechanisms
5. [Configuration Guide](configuration.md) - How to configure A2A
6. [SDK Integration](sdk-integration.md) - A2A SDK usage and migration
7. [Registry System](registry.md) - External registry integration
8. [Troubleshooting](troubleshooting.md) - Common issues and solutions

## Quick Start

### Enable A2A in Your Formation

```yaml
# formation.yaml
a2a:
  enabled: true

  # For receiving A2A messages from other formations
  inbound:
    enabled: true
    port: 8181
    registries:
      - "https://registry.example.com"
    auth:
      type: "bearer"
      token: "${{ secrets.A2A_BEARER_TOKEN }}"

  # For sending A2A messages to other formations
  outbound:
    enabled: true
    registries:
      - "https://registry.example.com"
    services:
      - service_id: "partner-formation"
        auth:
          type: "bearer"
          token: "${{ secrets.PARTNER_TOKEN }}"
```

### Send an A2A Message

```python
# From within an agent
response = await self.send_a2a_message(
    agent_id="calendar-agent",
    message="Schedule a meeting for tomorrow at 3pm",
    context={"priority": "high"}
)
```

## Key Concepts

### Internal vs External A2A

- **Internal A2A**: Communication between agents in the same formation
  - Direct in-memory routing
  - No network overhead
  - Always available

- **External A2A**: Communication between agents in different formations
  - Uses HTTP/HTTPS transport
  - Requires registry for discovery
  - Optional authentication

### A2A Service Architecture

```
┌─────────────────────────────────────────────────────┐
│                      Formation A                    │
│                                                     │
│  ┌─────────┐     ┌───────────────┐     ┌─────────┐  │
│  │ Agent 1 │────▶│  A2A Service  │────▶│ Agent 2 │  │
│  └─────────┘     │               │     └─────────┘  │
│                  │  - Router     │                  │
│                  │  - SDK Client │                  │
│                  │  - Auth       │                  │
│                  └──────┬────────┘                  │
│                         │                           │
└─────────────────────────┼───────────────────────────┘
                          │ HTTP/HTTPS
                          ▼
                  ┌──────────────┐
                  │ A2A Registry │
                  └──────────────┘
                          │
                          ▼
┌─────────────────────────┼───────────────────────────┐
│                      Formation B                    │
│                         │                           │
│                  ┌──────▼────────┐                  │
│                  │  A2A Server   │                  │
│                  │               │                  │
│  ┌─────────┐     │  - Auth       │     ┌─────────┐  │
│  │ Agent 3 │◀────│  - Router     │◀────│ Agent 4 │  │
│  └─────────┘     │  - Handler    │     └─────────┘  │
│                  └───────────────┘                  │
└─────────────────────────────────────────────────────┘
```

## Design Principles

1. **Protocol Compliance**: Strict adherence to A2A Protocol specification
2. **SDK-First**: Use official A2A SDK for all protocol operations
3. **Service Layer**: Agents use high-level service API, not raw protocol
4. **Security by Default**: Authentication required for external A2A
5. **Graceful Degradation**: System works even if external registry is down
6. **Observability**: Comprehensive logging and metrics

## Common Use Cases

### 1. Task Delegation
```python
# Weather agent delegates to news agent
await self.send_a2a_message(
    agent_id="news-agent",
    message="Get weather-related news for Seattle"
)
```

### 2. Information Gathering
```python
# Research agent gathers data from multiple sources
weather = await self.send_a2a_message("weather-agent", "Current weather in NYC")
traffic = await self.send_a2a_message("traffic-agent", "Traffic conditions in NYC")
```

### 3. Cross-Formation Collaboration
```python
# Agent in Formation A requests help from Formation B
response = await self.send_a2a_message(
    agent_id="expert-agent@formation-b",
    message="Analyze this financial report",
    context={"report_url": "https://..."}
)
```

## Next Steps

- Read the [Architecture Overview](architecture.md) for system design details
- See [Configuration Guide](configuration.md) for setup instructions
- Check [Message Flow](message-flow.md) to understand request lifecycle
- Review [Authentication](authentication.md) for security setup
