# Remote Desktop Agent Integration

**Version:** 0.1.0 (Draft)  
**Status:** Proposal  
**Target:** Q2 2026  

---

## Executive Summary

This document outlines how MUXI formations can interact with computer use agents running on end-user machines. The approach maintains MUXI's open-source integrity while enabling a separate commercial service for the desktop agent and tunnel infrastructure.

**Key Principle:** MUXI Runtime remains 100% open source. The desktop agent and tunnel service are separate products that happen to be compatible with MUXI (and any other MCP client).

---

## Business Model

### Separation of Concerns

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OPEN SOURCE (MUXI)                            │
│                                                                      │
│   - MUXI Runtime (Apache 2.0 / ELv2)                                │
│   - MCP client implementation                                        │
│   - DB schema for machine registry                                   │
│   - API endpoints for machine management                             │
│   - SDK/CLI for developers                                           │
│                                                                      │
│   Anyone can connect ANY MCP-compatible computer use agent.          │
│   No vendor lock-in.                                                 │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   COMMERCIAL SERVICE (Separate Brand?)               │
│                                                                      │
│   - Desktop application (computer use + MCP server + tunnel)         │
│   - Managed tunnel infrastructure                                    │
│   - Enterprise features (SSO, permissions, audit)                    │
│   - Support & SLA                                                    │
│                                                                      │
│   Optional. Users can self-host or use alternatives.                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Why Separate Branding?

| Approach | Pros | Cons |
|----------|------|------|
| **"MUXI Desktop"** | Brand recognition | OSS community may feel commercialization creep |
| **Separate brand** | Clean separation, OSS stays pure | Need to build new brand awareness |

**Recommendation:** Consider a separate brand (e.g., "Relay", "Bridge", "Conduit") for the commercial desktop service. This keeps MUXI's OSS reputation untainted while allowing aggressive monetization of the desktop product.

### Monetization

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | 1 machine, community support, rate limited |
| **Pro** | $10/user/mo | 5 machines, priority tunnel, basic support |
| **Enterprise** | Custom | Unlimited machines, SSO, audit logs, SLA, dedicated tunnel |

---

## Technical Architecture

### Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                              CLOUD                                      │
│                                                                         │
│   ┌──────────────────────┐            ┌────────────────────────────┐   │
│   │    MUXI Formation    │            │     Tunnel Server          │   │
│   │                      │            │     (Commercial Service)   │   │
│   │   ┌──────────────┐   │            │                            │   │
│   │   │ MCP Client   │───────────────▶│  agent-abc.tunnel.svc:443  │   │
│   │   └──────────────┘   │   HTTPS    │                            │   │
│   │                      │            └─────────────┬──────────────┘   │
│   │   ┌──────────────┐   │                          │                  │
│   │   │ Machine      │   │                          │                  │
│   │   │ Registry DB  │   │                       tunnel                │
│   │   └──────────────┘   │                          │                  │
│   └──────────────────────┘                          │                  │
└─────────────────────────────────────────────────────┼──────────────────┘
                                                      │
                                                      │
┌─────────────────────────────────────────────────────┼──────────────────┐
│                        USER'S MACHINE               │                   │
│                                                     │                   │
│   ┌─────────────────────────────────────────────────▼───────────────┐  │
│   │                    Desktop Agent                                 │  │
│   │                                                                  │  │
│   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │  │
│   │   │   Tunnel     │  │  MCP Server  │  │   Computer Use       │  │  │
│   │   │   Client     │──│  (HTTP)      │──│   (OpenWork/other)   │  │  │
│   │   │              │  │  Port 8080   │  │                      │  │  │
│   │   └──────────────┘  └──────────────┘  └──────────────────────┘  │  │
│   └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Desktop Agent is Just an MCP Server

The desktop agent exposes a standard MCP server over HTTP. Nothing proprietary. Any MCP client can connect to it.

**This means:**
- MUXI can connect (via our SDK)
- Claude Desktop can connect
- Any MCP-compatible tool can connect
- Self-hosted tunnel users can connect
- Direct LAN connections work too

---

## MCP Tool Schema for Computer Use Agents

A computer use MCP server SHOULD expose these tools:

### Core Tools

```yaml
tools:
  # Primary tool - natural language task execution
  - name: execute_task
    description: |
      Execute an autonomous task on this computer. The agent will 
      interpret the intent and perform necessary actions.
    inputSchema:
      type: object
      required: [intent]
      properties:
        intent:
          type: string
          description: Natural language description of what to do
          example: "Open Chrome and search for 'weather in NYC'"
        context:
          type: object
          description: Additional context to help the agent
          properties:
            background:
              type: string
              description: Relevant background information
            preferences:
              type: object
              description: User preferences for task execution
        constraints:
          type: object
          properties:
            timeout_seconds:
              type: integer
              default: 300
              description: Maximum time for task execution
            allowed_applications:
              type: array
              items:
                type: string
              description: Whitelist of applications the agent can use
            require_approval:
              type: boolean
              default: false
              description: Pause and request approval before destructive actions

  # Cancel a running task
  - name: cancel_task
    description: Cancel a currently running task
    inputSchema:
      type: object
      required: [task_id]
      properties:
        task_id:
          type: string

  # Respond to approval request
  - name: respond_to_approval
    description: Respond to a pending approval request from the agent
    inputSchema:
      type: object
      required: [approval_id, decision]
      properties:
        approval_id:
          type: string
        decision:
          type: string
          enum: [approve, deny, abort]

  # File operations
  - name: get_file
    description: Retrieve a file from this computer
    inputSchema:
      type: object
      required: [path]
      properties:
        path:
          type: string
          description: File path (absolute or relative to user home)
        
  - name: list_files
    description: List files in a directory
    inputSchema:
      type: object
      properties:
        path:
          type: string
          default: "~"
        pattern:
          type: string
          description: Glob pattern to filter files
```

### MCP Resources

```yaml
resources:
  # Agent capabilities
  - uri: agent://capabilities
    name: Agent Capabilities
    description: What this agent can do
    mimeType: application/json
    
  # Current status
  - uri: agent://status
    name: Agent Status  
    description: Current agent status (idle, busy, error)
    mimeType: application/json

  # Running task info
  - uri: agent://tasks/current
    name: Current Task
    description: Information about currently running task
    mimeType: application/json
```

### Streaming Progress (via MCP SSE)

When `execute_task` is called, progress is streamed via MCP's SSE transport:

```
event: progress
data: {"task_id": "t_123", "step": 1, "total": 5, "action": "Opening browser"}

event: progress  
data: {"task_id": "t_123", "step": 2, "total": 5, "action": "Navigating to google.com"}

event: approval_required
data: {"approval_id": "a_456", "action": "Download file", "reason": "Task requires downloading a file"}

event: complete
data: {"task_id": "t_123", "success": true, "summary": "Search completed", "result": {...}}
```

---

## MUXI Runtime Integration

### Database Schema

```sql
-- Machine registry (user can have multiple machines)
CREATE TABLE user_machines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    
    -- Machine identification
    machine_name VARCHAR(255) NOT NULL,
    machine_id VARCHAR(255) UNIQUE,  -- Hardware-derived ID for auto-registration
    
    -- Connection details
    endpoint_url VARCHAR(500) NOT NULL,  -- e.g., https://agent-abc.tunnel.svc
    api_key_hash VARCHAR(255) NOT NULL,  -- Hashed API key for MCP auth
    
    -- Metadata
    capabilities JSONB DEFAULT '[]',  -- What the agent can do
    os_info JSONB DEFAULT '{}',       -- OS, version, etc.
    last_seen_at TIMESTAMP,
    is_online BOOLEAN DEFAULT false,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_user_machines_user ON user_machines(user_id);
CREATE INDEX idx_user_machines_online ON user_machines(is_online);
```

### API Endpoints

```yaml
# Machine Management
POST   /v1/machines                    # Register a new machine
GET    /v1/machines                    # List user's machines
GET    /v1/machines/{id}               # Get machine details
PATCH  /v1/machines/{id}               # Update machine (name, etc.)
DELETE /v1/machines/{id}               # Remove machine

# Task Execution
POST   /v1/machines/{id}/tasks         # Send task to machine
GET    /v1/machines/{id}/tasks/{tid}   # Get task status
DELETE /v1/machines/{id}/tasks/{tid}   # Cancel task

# Approvals
POST   /v1/machines/{id}/approvals/{aid}  # Respond to approval request

# File Operations
GET    /v1/machines/{id}/files         # List files
GET    /v1/machines/{id}/files/*path   # Download file
```

### SDK Integration

```python
from muxi import Formation

formation = Formation.load("./my-formation")

# List user's machines
machines = await formation.machines.list(user_id="user_123")
# [Machine(id="m_abc", name="Work Laptop", is_online=True), ...]

# Execute task on a machine
result = await formation.machines.execute(
    machine_id="m_abc",
    intent="Find the Q4 report PDF and send it to me",
    constraints={"timeout_seconds": 120}
)

# Stream progress
async for event in formation.machines.execute_stream(
    machine_id="m_abc",
    intent="Fix Outlook sync issue"
):
    if event.type == "progress":
        print(f"Step {event.step}: {event.action}")
    elif event.type == "approval_required":
        # Route to user via Slack/WhatsApp
        decision = await get_user_approval(event)
        await formation.machines.respond_to_approval(
            machine_id="m_abc",
            approval_id=event.approval_id,
            decision=decision
        )
    elif event.type == "complete":
        print(f"Done: {event.summary}")
```

### CLI Integration

```bash
# List machines
muxi machines list --user user_123

# Execute task
muxi machines exec m_abc "Open Chrome and go to gmail.com"

# Get file from remote machine
muxi machines get-file m_abc "~/Documents/report.pdf" --output ./report.pdf

# Check machine status
muxi machines status m_abc
```

---

## Use Cases

### 1. Enterprise IT Support

**User (Slack):** "My Outlook won't sync"

**Formation:**
1. Identifies user, looks up their registered machines
2. Dispatches diagnostic task to user's work laptop
3. Agent checks settings, clears cache, repairs
4. Reports resolution back through Slack

**Result:** 2-minute automated resolution instead of 2-day ticket queue.

### 2. Remote File Access

**User (WhatsApp, 10 PM):** "Send me the Johnson proposal from my work computer"

**Formation:**
1. Looks up user's work machine
2. Sends `get_file` request with search intent
3. Agent finds file, returns it
4. Formation sends file to user via WhatsApp

**Result:** No more "I left it at the office."

### 3. Software Deployment

**IT Admin:** "Deploy VPN update to all sales team laptops"

**Formation:**
1. Queries machines registered to sales team users
2. Dispatches installation task to each (with approval required)
3. Users get Slack notification, approve
4. Agents install silently, report status
5. IT dashboard shows deployment progress

### 4. Compliance Verification

**Scheduled task:** "Weekly antivirus check"

**Formation:**
1. Iterates through all registered machines
2. Dispatches verification task to each online machine
3. Agents check AV status, version, last scan
4. Formation generates compliance report
5. Flags non-compliant machines for IT follow-up

---

## Roadmap

### V1 - Foundation (Q2 2026)

- [ ] Desktop agent app (OpenWork-based)
- [ ] MCP server implementation with core tools
- [ ] Tunnel infrastructure (frp/bore-based)
- [ ] MUXI Runtime: DB schema + API endpoints
- [ ] SDK: `formation.machines.*` methods
- [ ] CLI: `muxi machines` commands
- [ ] Manual machine registration flow

### V2 - Enterprise (Q3 2026)

- [ ] Auto-registration (user auth → machine registered)
- [ ] Enterprise SSO integration
- [ ] Permission policies (who can access whose machines)
- [ ] Audit logging
- [ ] Admin dashboard
- [ ] Machine groups / tags

### V3 - Scale (Q4 2026)

- [ ] Multi-region tunnel infrastructure
- [ ] Machine health monitoring
- [ ] Scheduled tasks per machine
- [ ] Cross-machine operations
- [ ] API for third-party integrations

---

## Security Considerations

### Authentication

- Machine ↔ Tunnel: mTLS or API key
- Formation ↔ Tunnel: API key per machine
- User ↔ Formation: Existing auth (via Slack/WhatsApp identity)

### Authorization

- Machines are scoped to users
- Enterprise policies control cross-user access
- Sensitive operations require real-time user approval

### Audit

- All tasks logged with timestamps
- Screenshots captured at key steps (optional)
- Approval decisions recorded with user identity

### Data Privacy

- Files transit through tunnel encrypted (TLS)
- Optional: E2E encryption (formation ↔ agent)
- Enterprise: Data residency options

---

## Open Questions

1. **Separate brand name?** What to call the commercial desktop service?
2. **Tunnel technology?** frp vs bore vs custom?
3. **Pricing model?** Per-user vs per-machine vs usage-based?
4. **Self-hosted option?** Allow enterprises to run their own tunnel server?

---

## References

- [MCP Protocol](https://modelcontextprotocol.io/)
- [OpenWork](https://github.com/accomplish-ai/openwork) - MIT licensed computer use framework
- [frp](https://github.com/fatedier/frp) - Fast reverse proxy
- [bore](https://github.com/ekzhang/bore) - Simple tunnel

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-01 | Initial draft |
