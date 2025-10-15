# Phase 2 Implementation Status

**Date**: Current session
**Goal**: Clean up Phase 1-covered events and implement runtime System/Error events

---

## ✅ Phase 1 Coverage Verification

### Confirmed: Init Events Already Handled by Linux-Style Output

| Category | Format Location | Output Example |
|----------|----------------|----------------|
| **MCP Registration & Discovery** | `mcp/service.py:955` | `[  OK  ] Connected to MCP 'filesystem' (3 tools available via stdio)` |
| **MCP Transport** | Same as above | Transport type included in MCP message |
| **Scheduler Init** | `scheduler/service.py:162` | `[  OK  ] Background scheduler initialized (checks every 1m, up to 5 concurrent jobs, UTC)` |
| **A2A Server** | `a2a_coordinator.py:249` | `[  OK  ] A2A server (localhost:8080, auth=api_key)` |
| **A2A Registry** | `overlord.py:1135` | `[  OK  ] Connected to A2A registry at registry.example.com` |
| **Database Init** | `initialization.py:469,524` | `[  OK  ] Initializing persistent memory (PostgreSQL / multi-user mode)`<br/>`[  OK  ] Database schema ready (6 tables initialized)` |
| **Service Init** | `formation.py:359,2602` | Banner + `[  OK  ] Formation initialized successfully (in 2.3s)` |
| **Agent Loading** | `initialization.py:918` | `[  OK  ] Loaded agent 'analyst' (role: research)` |

**Key Pattern**: Observability is disabled during init (`formation.py:349`), only formatted output shows. Observability enabled after init completes (`formation.py:2607`).

---

## 🗑️ Phase 1 Cleanup: Remove Obsolete Init Events

### Events to DELETE from `src/muxi/datatypes/observability.py`

These events are **obsolete** - replaced by InitEventFormatter output:

```python
# DELETE - General init events (replaced by banner + formatted output)
INITIALIZING = "service.initializing"  # Line 26
SERVICE_STARTED = "service.started"  # Line 29

# DELETE - MCP init events (replaced by formatted output)
MCP_SERVER_REGISTRATION_STARTED = "mcp.server.registration.started"  # Line 53
MCP_SERVER_REGISTRATION_COMPLETED = "mcp.server.registration.completed"  # Line 56
MCP_TOOL_DISCOVERY_COMPLETED = "mcp.tool.discovery.completed"  # Line 59
MCP_TRANSPORT_DETECTED = "mcp.transport.detected"  # Line 104

# DELETE - A2A init events (replaced by formatted output)
A2A_SERVER_STARTED = "a2a.server.started"  # Line 188

# DELETE - Overlord init events (replaced by formatted output)
OVERLORD_INITIALIZING = "overlord.initializing"  # Line 242

# DELETE - Scheduler init events (replaced by formatted output)
SCHEDULER_SERVICE_INITIALIZED = "scheduler.service.initialized"  # Line 345

# DELETE - Database init events (replaced by formatted output)
DATABASE_MANAGER_INITIALIZED = "database.manager.initialized"  # Line 357
```

**Total to delete**: ~11 init event definitions

### Events to KEEP (Runtime Events)

These are runtime events still needed for observability:

```python
# KEEP - MCP runtime events
MCP_SERVER_DISCONNECTED = "mcp.server.disconnected"
MCP_SERVER_CONNECTION_LOST = "mcp.server.connection_lost"
MCP_SERVER_PROCESS_FAILED = "mcp.server.process.failed"
MCP_TOOL_CALL_FAILED = "mcp.tool.call.failed"

# KEEP - Database runtime events
DATABASE_ERROR = "database.error"
DATABASE_QUERY_FAILED = "database.query.failed"

# KEEP - Scheduler runtime events  
SCHEDULER_JOB_FAILED = "scheduler.job.failed"
SCHEDULER_ERROR = "scheduler.error"

# KEEP - Cleanup/shutdown events
CLEANUP = "cleanup"
OVERLORD_SHUTDOWN = "overlord.shutdown"
```

---

## 📋 Phase 2 Scope: 368 TODO Comments

### Distribution Analysis

Found **368 TODO observability comments** across the codebase:

**Sample Categories** (from grep):
- Webhook events (~15 TODOs) - retry failures, delivery status
- Time estimation (~5 TODOs) - estimation errors, adjustments
- Document processing (~40 TODOs) - extraction failures, workflow errors
- Memory operations (~30 TODOs) - buffer failures, storage errors
- MCP runtime (~30 TODOs) - disconnections, tool call failures
- A2A runtime (~40 TODOs) - discovery failures, auth errors
- Resilience (~20 TODOs) - circuit breaker, fallback, recovery
- Workflow (~25 TODOs) - decomposition, execution, synthesis
- Many more...

### Categorization Strategy

**System/Error Events** (~150-200 TODOs) - **FOCUS NOW**:
- Infrastructure failures (MCP disconnects, database errors)
- Authentication/authorization failures
- Network errors and timeouts
- Resource exhaustion
- Service health monitoring

**Conversation Events** (~168-218 TODOs) - **DEFER TO PHASE 3**:
- Request lifecycle events
- Clarification system
- Agent processing
- Workflow orchestration
- Response generation
- Memory updates

**How to Separate**:
- ✅ **System/Error**: If event happens regardless of user request (service failures, health checks, resource limits)
- ❌ **Conversation**: If event is part of processing a user request (clarification, agent routing, memory extraction)

---

## 🎯 Phase 2 Action Plan

### Step 1: Remove Obsolete Init Events (30 minutes)

1. ✅ Verify Phase 1 coverage (DONE)
2. ⏭️ Delete 11 init event definitions from `observability.py`
3. ⏭️ Verify no code still references deleted events
4. ⏭️ Run test to confirm no breakage

### Step 2: Audit TODOs into System/Error vs Conversation (1 hour)

1. ⏭️ Create script to extract and categorize all 368 TODOs
2. ⏭️ Identify System/Error TODOs (~150-200)
3. ⏭️ Identify Conversation TODOs (~168-218)
4. ⏭️ Create prioritized list for System/Error implementation

### Step 3: Implement High-Priority System/Error Events (2-3 hours)

**Week 1: Security & Infrastructure** (~50 TODOs)
- Authentication failures (A2A, MCP)
- Authorization denials
- Database connection failures
- MCP process crashes
- Network errors

**Week 2: Error Handling** (~50 TODOs)
- Document processing errors
- Memory operation failures
- Scheduler job failures
- Webhook delivery failures

**Week 3: Resource & Health** (~50 TODOs)
- Resource exhaustion
- Circuit breaker events
- Health check failures
- Performance degradation

### Step 4: Defer Conversation Events to Phase 3 (Planning)

Use `docs/request-lifecycle.md` to map out Conversation events:
- Request initialization
- Clarification flow
- Agent processing
- Workflow execution
- Response generation
- Memory updates

---

## 📊 Success Criteria

**Phase 2 Complete When**:
- ✅ All 11 init events removed from observability.py
- ✅ No code references deleted init events
- ✅ 368 TODOs categorized (System/Error vs Conversation)
- ✅ High-priority System/Error TODOs implemented (~50-100)
- ✅ Clean startup output with Linux-style formatting
- ✅ Runtime observability working for critical failures

**Phase 3 Starts When**:
- Phase 2 System/Error events complete
- Ready to focus on Conversation events
- `docs/request-lifecycle.md` reviewed and updated

---

## 🚀 Next Immediate Actions

1. **Now**: Delete obsolete init events from observability.py
2. **Next**: Run grep analysis to categorize all 368 TODOs
3. **Then**: Create prioritized implementation list for System/Error events
4. **Finally**: Start Week 1 implementation (Security & Infrastructure)

**Ready to proceed with Step 1 (delete init events)?**
