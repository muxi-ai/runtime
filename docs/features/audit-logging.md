# Audit Logging Implementation

**Status:** Planned (endpoints return 501 until implemented)  
**Date:** 2025-12-12  
**Author:** Engineering  

## Overview

Wire up the existing `AuditLogger` to track formation events. Currently the audit infrastructure exists but is not connected to any actual operations.

## Scope

### Phase 1: Initialization Events (Priority)

Log what's deployed when formation starts - highest value for debugging and compliance.

| Event | Action | Resource Type | Metadata |
|-------|--------|---------------|----------|
| Agent loaded | `agent.registered` | `agent` | model, capabilities |
| MCP server connected | `mcp.server.registered` | `mcp_server` | transport type |
| Logging destination configured | `logging.destination.registered` | `logging` | destination type |
| Scheduler initialized | `scheduler.registered` | `scheduler` | job count |
| Memory system initialized | `memory.registered` | `memory` | memory type |

### Phase 2: Runtime Operations (Follow-up)

| Endpoint | Action | Resource Type |
|----------|--------|---------------|
| `POST /secrets` | `secret.created` | `secret` |
| `DELETE /secrets/{key}` | `secret.deleted` | `secret` |
| `DELETE /memory/buffers` (admin) | `memory.buffers.cleared` | `memory` |
| `DELETE /memories/{memory_id}` (client) | `memory.deleted` | `memory` |
| `DELETE /memory/buffer` (client) | `memory.buffer.cleared` | `memory` |
| `DELETE /memory/buffer/{session_id}` (client) | `memory.buffer.session.cleared` | `memory` |

## Architecture Decisions

### AuditLogger Instance Management

**Problem:** Creating a new `AuditLogger` for every request is wasteful.

**Solution:** Attach a single `AuditLogger` instance to the formation during initialization:

```python
# In Formation class or server startup
formation.audit_logger = AuditLogger(formation.formation_id)

# In route handlers
audit_logger = formation.audit_logger
```

### Error Handling

- Audit logging failures must NOT block the actual operation
- Current implementation uses `asyncio.create_task()` (good)
- Add exception logging in task callback for debugging
- Failed operations SHOULD be logged with `result: "error"`

### Storage Limitations

**Current:** `~/.muxi/formations/{formation_id}/audit.log`

**Limitations:**
- Local to runtime container
- Lost on restart unless volume mounted
- Not centralized for multi-formation deployments

**For MVP:** Document this limitation. Future work may add remote log shipping.

**Log Rotation:** Not for MVP. Document that large formations may need manual cleanup.

## Implementation Details

### 1. Initialization Logging

```python
# In formation/server/server.py after formation loads

def _log_initialization_events(self, formation: Formation):
    """Log all resources registered during formation initialization."""
    audit = formation.audit_logger
    
    # Log agents with metadata
    for name, agent in formation.agents.items():
        audit.log(
            action="agent.registered",
            resource_type="agent",
            resource_id=name,
            message=f"Agent '{name}' registered",
            user="system",
            additional_data={"model": agent.model_name}
        )
    
    # Log MCP servers
    if formation.mcp_manager:
        for name, server in formation.mcp_manager.servers.items():
            audit.log(
                action="mcp.server.registered",
                resource_type="mcp_server",
                resource_id=name,
                message=f"MCP server '{name}' registered",
                user="system",
                additional_data={"transport": server.transport_type}
            )
    
    # Log logging destinations, scheduler, memory...
```

### 2. Route Handler Logging (Phase 2)

```python
# In routes/admin/secrets.py

@router.post("/secrets", response_model=APIResponse)
async def create_secret(...):
    # ... existing logic ...
    
    # After successful creation:
    formation.audit_logger.log_from_request(
        request=request,
        action="secret.created",
        resource_type="secret",
        resource_id=key,
        message=f"Secret '{key}' created",
    )
    
    return response
```

### 3. Files to Modify

| File | Changes |
|------|---------|
| `formation/formation.py` | Initialize `audit_logger` attribute |
| `formation/server/server.py` | Call `_log_initialization_events()` on startup |
| `routes/admin/secrets.py` | Add audit logging (Phase 2) |
| `routes/admin/memory.py` | Add audit logging (Phase 2) |
| `routes/client/memory.py` | Add audit logging (Phase 2) |

### 4. Audit Log Format

Each entry is a JSON line in `~/.muxi/formations/{formation_id}/audit.log`:

```json
{
  "timestamp": "2025-12-12T10:30:00.000Z",
  "request_id": null,
  "action": "agent.registered",
  "resource_type": "agent",
  "resource_id": "assistant",
  "user": "system",
  "ip": null,
  "result": "success",
  "status_code": 200,
  "message": "Agent 'assistant' registered",
  "data": {"model": "openai/gpt-4o-mini"}
}
```

## API Spec Updates Needed

Document audited events in OpenAPI spec under `GET /audit` response examples.

## Testing

1. Create a formation with agents, MCP servers, logging destinations
2. Start the formation server
3. Call `GET /audit` - verify initialization events appear
4. (Phase 2) Create/delete secret, verify in audit log
5. (Phase 2) Clear memory buffer, verify in audit log

## Estimate

- Phase 1 (initialization logging): ~30 minutes
- Phase 2 (runtime operations): ~30 minutes
- Testing: ~15 minutes
- **Total: ~1.25 hours**
