# Phase 2 Focused Plan: System & Error Events Only

**Goal**: Implement runtime System/Error event TODOs, excluding init events (already done) and conversation events (planned later based on request-lifecycle.md)

---

## Step 1: Remove Phase 1-Covered Init Events

### Events to DELETE from Code

These events were replaced by Phase 1 Linux-style init messages and should be **removed from the codebase**:

#### MCP Init Events (DELETE from observability.py)
```python
# Registration & Discovery - REMOVE
MCP_SERVER_REGISTRATION_STARTED = "mcp.server.registration.started"  # → DELETE
MCP_SERVER_REGISTRATION_COMPLETED = "mcp.server.registration.completed"  # → DELETE (covered by init message)
MCP_TOOL_DISCOVERY_STARTED = "mcp.tool.discovery_started"  # → DELETE
MCP_TOOL_DISCOVERY_COMPLETED = "mcp.tool.discovery_completed"  # → DELETE (covered by init message)

# Transport - REMOVE
MCP_TRANSPORT_DETECTED = "mcp.transport.detected"  # → DELETE (shown in init message)
MCP_TRANSPORT_ATTEMPT = "mcp.transport.attempt"  # → DELETE

# Process - REMOVE
MCP_SERVER_PROCESS_STARTED = "mcp.server.process.started"  # → DELETE
```

#### Scheduler Init Events (DELETE from observability.py)
```python
# Scheduler initialization - REMOVE (covered by init message)
SCHEDULER_SERVICE_INITIALIZED = "scheduler.service.initialized"  # → DELETE (covered)
SCHEDULER_MANAGER_INITIALIZED = "scheduler.manager.initialized"  # → DELETE
SCHEDULER_PARSER_INITIALIZED = "scheduler.parser.initialized"  # → DELETE
SCHEDULER_DATABASE_INITIALIZED = "scheduler.database.initialized"  # → DELETE
```

#### A2A Init Events (DELETE from observability.py)
```python
# A2A server startup - REMOVE (covered by init message)
A2A_SERVER_STARTED = "a2a.server.started"  # → DELETE (covered)
A2A_REGISTRY_CONNECTED = "a2a.registry.connected"  # → DELETE (covered)
```

#### Database Init Events (DELETE from observability.py)
```python
# Database initialization - REMOVE (covered by init messages)
DATABASE_MANAGER_INITIALIZED = "database.manager.initialized"  # → DELETE (redundant with persistent memory)
DATABASE_TABLES_CREATED = "database.tables.created"  # → DELETE (covered by schema ready)
DB_CONNECTION_STARTED = "db.connection.started"  # → DELETE
```

#### General Service Init Events (DELETE from observability.py)
```python
# General initialization - REMOVE (replaced by Linux-style init)
INITIALIZING = "initializing"  # → DELETE (replaced by banner)
SERVICE_STARTED = "service.started"  # → DELETE (replaced by specific init messages)
AUTH_MANAGER_INITIALIZED = "auth.manager.initialized"  # → DELETE (too granular)
INBOUND_AUTH_INITIALIZED = "inbound.auth.initialized"  # → DELETE (too granular)
MEMORY_OPTIMIZER_STARTED = "memory.optimizer.started"  # → DELETE (too granular)
CACHE_MANAGER_STARTED = "cache.manager.started"  # → DELETE (too granular)
```

**Action Items**:
1. Delete these event definitions from `src/muxi/datatypes/observability.py`
2. Remove any imports/usages of these events
3. Update any TODOs that reference these events → mark as "Covered by Phase 1 init"

---

## Step 2: Categorize Remaining TODOs

### A. System & Error Events (Focus Now - ~150 TODOs)

**Infrastructure & Runtime Events** - NOT related to request lifecycle:

#### 1. MCP Runtime Events (~30 TODOs)
**Category**: SystemEvents / ErrorEvents
**Focus**: Runtime failures, NOT init

| TODO Location | Event Needed | Type |
|---------------|--------------|------|
| `services/mcp/service.py` | MCP_SERVER_PROCESS_FAILED | SystemEvents |
| `services/mcp/service.py` | MCP_SERVER_PROCESS_TIMEOUT | SystemEvents |
| `services/mcp/service.py` | MCP_SERVER_DISCONNECTED | SystemEvents |
| `services/mcp/service.py` | MCP_SERVER_CONNECTION_LOST | SystemEvents |
| `services/mcp/service.py` | MCP_TOOL_CALL_FAILED | ErrorEvents |
| `services/mcp/service.py` | MCP_TOOL_CALL_TIMEOUT | ErrorEvents |
| `services/mcp/service.py` | MCP_CONNECTION_ERROR | ErrorEvents |
| `services/mcp/auth/*.py` | AUTHENTICATION_FAILED | ErrorEvents |
| `services/mcp/auth/*.py` | CREDENTIAL_ERROR | ErrorEvents |

**Exclude**: Init-related TODOs (already covered)

#### 2. A2A Runtime Events (~40 TODOs)
**Category**: SystemEvents / ErrorEvents
**Focus**: Discovery, communication, auth failures

| TODO Location | Event Needed | Type |
|---------------|--------------|------|
| `services/a2a/discovery.py` | A2A_DISCOVERY_FAILED | ErrorEvents |
| `services/a2a/discovery.py` | A2A_AGENT_UNREACHABLE | SystemEvents |
| `services/a2a/discovery.py` | A2A_REGISTRY_SYNC_FAILED | ErrorEvents |
| `services/a2a/auth/inbound.py` | AUTHENTICATION_FAILED | ErrorEvents |
| `services/a2a/auth/inbound.py` | AUTHORIZATION_FAILED | ErrorEvents |
| `services/a2a/auth/inbound.py` | TOKEN_INVALID | ErrorEvents |
| `services/a2a/auth/inbound.py` | CREDENTIAL_ERROR | ErrorEvents |
| `services/a2a/*.py` | A2A_MESSAGE_FAILED | ErrorEvents |
| `services/a2a/*.py` | A2A_COMMUNICATION_ERROR | ErrorEvents |
| `services/a2a/*.py` | NETWORK_ERROR | ErrorEvents |

**Exclude**: A2A_SERVER_STARTED, A2A_REGISTRY_CONNECTED (covered by init)

#### 3. Database Runtime Events (~10 TODOs)
**Category**: ErrorEvents
**Focus**: Runtime failures, NOT init

| TODO Location | Event Needed | Type |
|---------------|--------------|------|
| `services/db.py` | DB_CONNECTION_FAILED | ErrorEvents |
| `services/db.py` | DB_CONNECTION_LOST | ErrorEvents |
| `services/db.py` | DATABASE_ERROR | ErrorEvents |
| `services/db.py` | DATABASE_QUERY_FAILED | ErrorEvents |
| `services/db.py` | DATABASE_TIMEOUT | ErrorEvents |

**Exclude**: DATABASE_MANAGER_INITIALIZED, DB_CONNECTION_STARTED (covered by init)

#### 4. Scheduler Runtime Events (~15 TODOs)
**Category**: SystemEvents / ErrorEvents
**Focus**: Job execution, NOT init

| TODO Location | Event Needed | Type |
|---------------|--------------|------|
| `services/scheduler/*.py` | SCHEDULER_JOB_FAILED | ErrorEvents |
| `services/scheduler/*.py` | SCHEDULER_JOB_TIMEOUT | ErrorEvents |
| `services/scheduler/*.py` | SCHEDULER_JOB_RETRY | SystemEvents (DEBUG) |
| `services/scheduler/*.py` | SCHEDULER_ERROR | ErrorEvents |
| `services/scheduler/*.py` | SCHEDULER_LIMIT_REACHED | SystemEvents |

**Exclude**: SCHEDULER_SERVICE_INITIALIZED, SCHEDULER_MANAGER_INITIALIZED (covered by init)

#### 5. Memory System Errors (~25 TODOs)
**Category**: ErrorEvents
**Focus**: Operation failures

| TODO Location | Event Needed | Type |
|---------------|--------------|------|
| `formation/documents/storage/*.py` | MEMORY_ERROR | ErrorEvents |
| `formation/documents/storage/*.py` | MEMORY_OPERATION_FAILED | ErrorEvents |
| `formation/documents/storage/*.py` | STORAGE_ERROR | ErrorEvents |
| `formation/documents/workflow/*.py` | MEMORY_DELETION_FAILED | ErrorEvents |
| `services/memory/*.py` | MEMORY_CORRUPTION | ErrorEvents |
| `services/memory/*.py` | SERIALIZATION_ERROR | ErrorEvents |

#### 6. Network & Infrastructure (~10 TODOs)
**Category**: ErrorEvents
**Focus**: Network failures

| TODO Location | Event Needed | Type |
|---------------|--------------|------|
| `services/a2a/*.py` | NETWORK_ERROR | ErrorEvents |
| `services/a2a/*.py` | CONNECTION_TIMEOUT | ErrorEvents |
| `services/mcp/*.py` | CONNECTION_REFUSED | ErrorEvents |
| Various | NETWORK_INTERFACE_FAILED | ErrorEvents |

#### 7. Document Processing Errors (~20 TODOs)
**Category**: ErrorEvents
**Focus**: Processing failures (NOT request lifecycle)

| TODO Location | Event Needed | Type |
|---------------|--------------|------|
| `formation/documents/experience/error_handler.py` | DOCUMENT_PROCESSING_FAILED | ErrorEvents |
| `formation/documents/storage/chunk_manager.py` | CONTENT_EXTRACTION_FAILED | ErrorEvents |
| `formation/documents/workflow/*.py` | WORKFLOW_ERROR | ErrorEvents |
| `formation/documents/experience/error_handler.py` | CIRCUIT_BREAKER_OPENED | SystemEvents |

**Note**: Some document processing TODOs may be ConversationEvents (request lifecycle). Separate later.

---

### B. Conversation Events (Plan Later - ~218 TODOs)

**Request Lifecycle Events** - Based on request-lifecycle.md:

These are related to user request flow and should be planned based on the request lifecycle doc:

- Request initialization (~30 TODOs)
- Clarification system (~20 TODOs)
- Agent processing (~40 TODOs)
- Overlord orchestration (~30 TODOs)
- Workflow execution (~25 TODOs)
- Response generation (~20 TODOs)
- Memory updates (~15 TODOs)
- Persona application (~10 TODOs)
- Document workflow info (~28 TODOs)

**Action**: Defer to separate planning session with request-lifecycle.md

---

## Step 3: Focused Implementation Plan (System & Error Events)

### Phase 2A: High-Priority Runtime Events (Week 1-2)

#### Week 1: Security & Auth Failures

**Focus**: Authentication, authorization, credential errors

**Day 1-2: A2A Authentication (~15 TODOs)**
- File: `services/a2a/auth/inbound.py`
- Events: AUTHENTICATION_FAILED, AUTHORIZATION_FAILED, TOKEN_INVALID, CREDENTIAL_ERROR
- Pattern:
  ```python
  # Replace TODO
  #  A2A inbound auth error - TODO: add observability
  
  # With event emission
  observe(
      ErrorEvents.AUTHENTICATION_FAILED,
      level=EventLevel.ERROR,
      data={
          "auth_type": self.auth_mode.value,
          "client_id": client_id,
          "error": str(e)
      },
      description=f"A2A authentication failed for {client_id}"
  )
  ```

**Day 3-4: MCP Authentication (~8 TODOs)**
- File: `services/mcp/auth/*.py`
- Events: Same as A2A
- Similar pattern

**Day 5: Authorization Failures (~7 TODOs)**
- Files: Various permission checks
- Events: AUTHORIZATION_FAILED
- Focus: Access control denials

#### Week 2: Infrastructure Failures

**Day 1: Database Runtime Errors (~10 TODOs)**
- File: `services/db.py`
- Events: DB_CONNECTION_FAILED, DB_CONNECTION_LOST, DATABASE_ERROR, DATABASE_QUERY_FAILED
- Pattern:
  ```python
  # On connection failure
  except Exception as e:
      observe(
          ErrorEvents.DB_CONNECTION_FAILED,
          level=EventLevel.ERROR,
          data={
              "database_type": self.database_type,
              "error": str(e)
          },
          description="Database connection failed"
      )
      raise
  ```

**Day 2-3: MCP Runtime Errors (~20 TODOs)**
- File: `services/mcp/service.py`
- Events:
  - MCP_SERVER_PROCESS_FAILED
  - MCP_SERVER_PROCESS_TIMEOUT
  - MCP_SERVER_DISCONNECTED
  - MCP_SERVER_CONNECTION_LOST
  - MCP_TOOL_CALL_FAILED
  - MCP_TOOL_CALL_TIMEOUT
  
**Day 4-5: A2A Runtime Errors (~20 TODOs)**
- Files: `services/a2a/discovery.py`, `services/a2a/*.py`
- Events:
  - A2A_DISCOVERY_FAILED
  - A2A_AGENT_UNREACHABLE
  - A2A_MESSAGE_FAILED
  - A2A_COMMUNICATION_ERROR
  - NETWORK_ERROR

### Phase 2B: Medium-Priority Runtime Events (Week 3)

**Day 1-2: Scheduler Runtime (~15 TODOs)**
- Files: `services/scheduler/*.py`
- Events: SCHEDULER_JOB_FAILED, SCHEDULER_JOB_TIMEOUT, SCHEDULER_ERROR

**Day 3-4: Memory System Errors (~25 TODOs)**
- Files: `formation/documents/storage/*.py`, `services/memory/*.py`
- Events: MEMORY_ERROR, MEMORY_OPERATION_FAILED, STORAGE_ERROR

**Day 5: Network Errors (~10 TODOs)**
- Files: Various
- Events: NETWORK_ERROR, CONNECTION_TIMEOUT, CONNECTION_REFUSED

### Phase 2C: Document Processing Errors (Week 4)

**Day 1-3: Document Processing (~20 TODOs)**
- Files: `formation/documents/experience/error_handler.py`, `formation/documents/storage/chunk_manager.py`
- Events: DOCUMENT_PROCESSING_FAILED, CONTENT_EXTRACTION_FAILED, WORKFLOW_ERROR

**Day 4-5: Testing & Cleanup**
- Run full test suite
- Verify events emitted correctly
- Update documentation
- Remove TODO comments

---

## Step 4: Event Cleanup Actions

### Action 1: Delete Init Events from observability.py

```python
# File: src/muxi/datatypes/observability.py

# DELETE these lines (init events covered by Phase 1):
class SystemEvents(Enum):
    # DELETE: MCP init events
    # MCP_SERVER_REGISTRATION_STARTED = "..."
    # MCP_SERVER_REGISTRATION_COMPLETED = "..."
    # MCP_TOOL_DISCOVERY_STARTED = "..."
    # MCP_TOOL_DISCOVERY_COMPLETED = "..."
    # MCP_TRANSPORT_DETECTED = "..."
    # MCP_TRANSPORT_ATTEMPT = "..."
    # MCP_SERVER_PROCESS_STARTED = "..."
    
    # DELETE: Scheduler init events
    # SCHEDULER_SERVICE_INITIALIZED = "..."
    # SCHEDULER_MANAGER_INITIALIZED = "..."
    # SCHEDULER_PARSER_INITIALIZED = "..."
    # SCHEDULER_DATABASE_INITIALIZED = "..."
    
    # DELETE: A2A init events
    # A2A_SERVER_STARTED = "..."
    # A2A_REGISTRY_CONNECTED = "..."
    
    # DELETE: Database init events
    # DATABASE_MANAGER_INITIALIZED = "..."
    # DATABASE_TABLES_CREATED = "..."
    # DB_CONNECTION_STARTED = "..."
    
    # DELETE: General init events
    # INITIALIZING = "..."
    # SERVICE_STARTED = "..."
    # AUTH_MANAGER_INITIALIZED = "..."
    # INBOUND_AUTH_INITIALIZED = "..."
    # MEMORY_OPTIMIZER_STARTED = "..."
    # CACHE_MANAGER_STARTED = "..."
```

### Action 2: Update TODOs

For init-related TODOs, change:
```python
# Before
#  Info - TODO: add observability

# After
# Covered by Phase 1 Linux-style init message
```

### Action 3: Grep for Usages

```bash
# Find any code still referencing deleted events
grep -r "MCP_SERVER_REGISTRATION_STARTED" src/
grep -r "SCHEDULER_SERVICE_INITIALIZED" src/
grep -r "A2A_SERVER_STARTED" src/
grep -r "DATABASE_MANAGER_INITIALIZED" src/
grep -r "SERVICE_STARTED" src/

# Remove those usages
```

---

## Summary

### Phase 2 Scope (Revised)

**Original**: 368 TODOs total

**After Removing Init Events**:
- ~50-80 TODOs are init-related → **DELETE or mark as covered**
- ~150 TODOs are System/Error runtime → **Implement in Phase 2**
- ~218 TODOs are Conversation lifecycle → **Defer to Phase 3** (planned with request-lifecycle.md)

### Phase 2 Focus: System & Error Runtime Events Only

**Week 1-2**: Security & Infrastructure (~50 TODOs)
- Authentication failures (A2A, MCP)
- Authorization denials
- Database runtime errors
- MCP runtime failures
- A2A communication errors

**Week 3**: Scheduler & Memory (~40 TODOs)
- Scheduler job failures
- Memory operation errors
- Network failures

**Week 4**: Document Processing & Testing (~20 TODOs)
- Document processing errors
- Testing & cleanup

**Total: ~110 System/Error runtime TODOs**

---

## Next Steps

1. **Delete init events** from observability.py (Action 1)
2. **Update init TODOs** to mark as covered (Action 2)
3. **Verify no usages** of deleted events (Action 3)
4. **Start Week 1** implementation (A2A auth failures)
5. **Defer Conversation events** to Phase 3 with request-lifecycle.md mapping

**Ready to start?** 🎯
