# Initialization Events - Current State Analysis

**Date**: October 15, 2025
**Purpose**: Map actual init events emitted to inform Linux-style startup redesign

---

## Event Emission Summary

Based on codebase grep analysis:

| Event Category | Count | Used During Init | Notes |
|---------------|-------|------------------|-------|
| `INITIALIZING` | 40 uses | ✅ Yes | Formation, Overlord, Artifacts |
| `SERVICE_STARTED` | 29 uses | ✅ Yes | Various services |
| `MCP_SERVER_*` | 46 uses | ✅ Yes | Registration, connection, discovery |
| `SCHEDULER_*` | 27 uses | ✅ Yes | Heavy usage (11 different locations!) |
| `DATABASE_*` | 5 uses | ✅ Yes | Manager init, table creation |
| `AGENT_INITIALIZED` | 10 uses | ✅ Yes | Agent loading |
| `A2A_*` | 155 uses | ✅ Yes | Massive A2A subsystem |
| `MEMORY_*` | 7 uses | ⚠️ Mostly runtime | Buffer updates, operation failures |

---

## Detailed Analysis by Subsystem

### 1. Core Formation/Overlord Init

**Current Events**:
- `SystemEvents.INITIALIZING` (artifacts/extractor.py, overlord.py)
- `SystemEvents.SERVICE_STARTED` (overlord.py - 5+ locations)

**Files**:
- `src/muxi/formation/artifacts/extractor.py` - line ~156
- `src/muxi/formation/overlord/overlord.py` - multiple locations

**Assessment**:
- ✅ These are the "main" startup events
- ⚠️ `SERVICE_STARTED` is overloaded (used 29 times!)
- **Recommendation**: Replace with Linux-style banner
  ```
  [  OK  ] Started MUXI Runtime Server v{version}
  [  OK  ] Loaded formation: {formation_name}
  ```

---

### 2. MCP Service Init (46 uses!)

**Current Events**:
- `MCP_SERVER_REGISTRATION_STARTED` (overlord.py:323)
- `MCP_SERVER_REGISTRATION_COMPLETED` (mcp/service.py:250, overlord.py:1025)
- `MCP_SERVER_REGISTRATION_FAILED` (mcp/service.py:1041)
- `MCP_TOOL_DISCOVERY_COMPLETED` (mcp/service.py:908, 944, 975)
- `MCP_TRANSPORT_DETECTED` (mcp/service.py:367)
- `MCP_TRANSPORT_ATTEMPT` (mcp/service.py:766)
- `MCP_TRANSPORT_FAILED` (mcp/service.py:796)
- `MCP_TRANSPORT_DETECTION_FAILED` (mcp/service.py:402)

**Runtime Events (keep these)**:
- `MCP_SERVER_DISCONNECTED` (mcp/service.py:1160, 1170, 1626)
- `MCP_SERVER_CONNECTION_LOST` (mcp/service.py:1394)
- `MCP_SERVER_DISCONNECTION_FAILED` (mcp/service.py:1637)

**Assessment**:
- 🚨 **This is the verbosity culprit!** MCP emits 8+ events per server during init
- For 3 MCP servers = 24+ log lines just for MCP
- **Recommendation**: Consolidate to single formatted line
  ```
  [  OK  ] Registered MCP server: filesystem (3 tools, stdio transport)
  [  OK  ] Registered MCP server: web-search (2 tools, http-sse transport)
  [ WARN ] MCP server registration failed: broken-server (timeout)
  ```

**Events to Delete (init only)**:
- `MCP_SERVER_REGISTRATION_STARTED` → Not needed with single-line output
- `MCP_TOOL_DISCOVERY_COMPLETED` → Merge into registration success
- `MCP_TRANSPORT_DETECTED` → Merge into registration
- `MCP_TRANSPORT_ATTEMPT` → Too granular
- `MCP_TRANSPORT_DETECTION_FAILED` → Move to DEBUG

**Events to Keep (runtime)**:
- `MCP_SERVER_DISCONNECTED` → Runtime event
- `MCP_SERVER_CONNECTION_LOST` → Runtime event
- `MCP_SERVER_REGISTRATION_FAILED` → Convert to formatted [ FAIL ]

---

### 3. Scheduler Init (27 uses!)

**Current Events**:
- `SCHEDULER_SERVICE_INITIALIZED` (scheduler/service.py - 11 locations!)

**Files**:
- `src/muxi/services/scheduler/service.py` - lines 146, 162, 191, 205, 241, 285, 324, 365, 416, 706, 763, 1169, 1186

**Assessment**:
- 🚨 **Way too many!** Same event emitted from 11+ different code paths
- This creates duplicate log lines
- **Recommendation**: Single consolidated init
  ```
  [  OK  ] Initialized scheduler service
  ```

**Action Required**:
- Review scheduler/service.py to understand why 11 different locations
- Likely: Different initialization paths (parser, manager, jobs, etc.)
- **Solution**: Emit once at the end of successful init, not at every sub-component

---

### 4. Database Init (5 uses)

**Current Events**:
- `DATABASE_MANAGER_INITIALIZED` (services/db.py)
- `DATABASE_TABLES_CREATED` (formation/initialization.py)
- `DATABASE_TYPE_FALLBACK` (services/db.py)

**Assessment**:
- ✅ Reasonable number
- **Recommendation**: Format as single line
  ```
  [  OK  ] Connected to PostgreSQL database
  [  OK  ] Database tables ready
  [ INFO ] Using SQLite (PostgreSQL unavailable)
  ```

**Events to Keep**:
- `DATABASE_MANAGER_INITIALIZED` → Convert to formatted
- `DATABASE_TABLES_CREATED` → Convert to formatted
- `DATABASE_TYPE_FALLBACK` → Convert to formatted [ INFO ]

---

### 5. Agent Init (10 uses)

**Current Events**:
- `AGENT_INITIALIZED` (overlord.py - 3 different locations)

**Assessment**:
- ✅ Reasonable usage
- **Recommendation**: Format as summary line
  ```
  [  OK  ] Loaded 3 agents: analyst, writer, debugger
  ```

**Events to Keep**:
- `AGENT_INITIALIZED` → Convert to formatted (with agent name)

---

### 6. A2A System Init (155 uses!)

**Current Events**:
- `A2A_SERVER_STARTED` (overlord/a2a_coordinator.py)
- `A2A_SERVER_FAILED` (overlord/a2a_coordinator.py)
- `A2A_CONFIG_LOAD_STARTED` (audit: used)
- `A2A_CONFIG_LOAD_COMPLETED` (audit: used)
- Many more A2A events...

**Assessment**:
- 🚨 **155 uses is MASSIVE!** A2A has its own event ecosystem
- Need to review what's init vs runtime
- **Recommendation**: Consolidate init events
  ```
  [  OK  ] A2A service initialized (5 connections)
  [ INFO ] A2A registry connected
  ```

**Action Required**:
- Deep dive into A2A events to separate init from runtime
- Many A2A events are likely runtime (registry updates, health checks)

---

### 7. Memory Systems Init (7 uses - mostly runtime)

**Current Events**:
- `MEMORY_BUFFER_UPDATE_FAILED` (buffer_manager.py) - runtime
- `MEMORY_OPERATION_FAILED` (clarification.py) - runtime

**Assessment**:
- ✅ Most memory events are runtime, not init
- No dedicated memory init events currently
- **Recommendation**: Add init events
  ```
  [ INFO ] Buffer memory: FIFO mode (100 messages)
  [ INFO ] Persistent memory: PostgreSQL
  [ WARN ] Vector memory: disabled
  ```

**Events to Add**:
- `MEMORY_BUFFER_INITIALIZED` (or format directly)
- `MEMORY_PERSISTENT_INITIALIZED` (or format directly)
- `MEMORY_VECTOR_INITIALIZED` (or format directly)

---

## Proposed Linux-Style Init Mapping

### Current Startup Log (Verbose)
```
INFO | SystemEvents.INITIALIZING
INFO | MCP_SERVER_REGISTRATION_STARTED server=filesystem
INFO | MCP_TRANSPORT_ATTEMPT transport=stdio
INFO | MCP_TRANSPORT_DETECTED transport=stdio
INFO | MCP_SERVER_REGISTRATION_COMPLETED server=filesystem
INFO | MCP_TOOL_DISCOVERY_COMPLETED server=filesystem tools=3
INFO | MCP_SERVER_REGISTRATION_STARTED server=web-search
INFO | MCP_TRANSPORT_ATTEMPT transport=http-sse
INFO | MCP_TRANSPORT_DETECTED transport=http-sse
INFO | MCP_SERVER_REGISTRATION_COMPLETED server=web-search
INFO | MCP_TOOL_DISCOVERY_COMPLETED server=web-search tools=2
INFO | SCHEDULER_SERVICE_INITIALIZED
INFO | SCHEDULER_SERVICE_INITIALIZED (duplicate from different path)
INFO | DATABASE_MANAGER_INITIALIZED
INFO | DATABASE_TABLES_CREATED
INFO | AGENT_INITIALIZED agent=analyst
INFO | AGENT_INITIALIZED agent=writer
INFO | AGENT_INITIALIZED agent=debugger
INFO | A2A_SERVER_STARTED
INFO | A2A_CONFIG_LOAD_COMPLETED
INFO | SystemEvents.SERVICE_STARTED
```
**Estimated lines**: 20+ lines for typical formation

### Proposed Linux-Style Log (Clean)
```
[  OK  ] Started MUXI Runtime Server v1.0.0
[  OK  ] Loaded formation: my-formation
[  OK  ] Connected to PostgreSQL database (tables ready)
[  OK  ] Registered MCP server: filesystem (3 tools)
[  OK  ] Registered MCP server: web-search (2 tools)
[  OK  ] Initialized scheduler service
[  OK  ] Loaded 3 agents: analyst, writer, debugger
[  OK  ] A2A service initialized
[ INFO ] Buffer memory: FIFO mode (100 messages)
[ INFO ] Persistent memory: PostgreSQL
[ WARN ] Vector memory: disabled
[  OK  ] Ready to accept requests

Startup completed in 2.3s (8 services, 1 warning, 0 errors)
```
**Estimated lines**: 13 lines (35% reduction)

---

## Design Decisions (Finalized)

### Service Identification
**Use formation IDs/names, not full URLs/connection strings:**
- ✅ `[  OK  ] MCP server: filesystem (3 tools)`
- ✅ `[  OK  ] Database: sqlite (./data/muxi.db)`
- ✅ `[  OK  ] A2A registry: local (5 agents)`
- ❌ `[  OK  ] MCP server: http://localhost:3000/mcp/filesystem`
- ❌ `[  OK  ] Database: postgresql://user:****@localhost:5432/muxi`

**Rationale**: Formation already has friendly names. URLs expose sensitive info and add clutter.

### Error Display Format
**Show structured error information by default (not behind debug flag):**
```
[ FAIL ] MCP server: filesystem

  Connection timeout after 5 seconds
  
  The server didn't respond during startup. Common causes:
    • Server executable not installed or not in PATH
    • Incorrect command in formation config
    • Server crashed on launch
    
  To fix:
    1. Test manually: npx @modelcontextprotocol/server-filesystem
    2. Install if needed: npm install -g @modelcontextprotocol/server-filesystem
    3. Check formation.yaml → mcp.servers.filesystem.command
  
  Config: formation.yaml:45 (mcp.servers.filesystem)
  
  Traceback (most recent call last):
    File "src/muxi/services/mcp/registry.py", line 156, in register_server
      response = await client.connect(timeout=5.0)
  TimeoutError: Server did not respond within 5 seconds
```

**Rationale**: Init failures happen at deployment/development time. Fast feedback with full context accelerates debugging. No need to hide details behind flags.

### Structured Error Information
Create `InitFailureInfo` dataclass for consistent error formatting:
```python
@dataclass
class InitFailureInfo:
    component: str       # "MCP server: filesystem"
    problem: str         # Plain English summary
    context: str         # Where in formation config
    causes: list[str]    # Likely reasons
    fixes: list[str]     # Actionable steps
    technical: str       # Original exception with traceback
```

**Benefits**:
- Operational guidance instead of raw stack traces
- Consistent error format across all subsystems
- Clear action items for users
- Technical details included for debugging

---

## Events to Convert to Linux-Style Format

### Delete (replace with formatted output):
1. `INITIALIZING` → Banner line
2. `SERVICE_STARTED` (29 uses!) → Ready line
3. `MCP_SERVER_REGISTRATION_STARTED` → Removed
4. `MCP_SERVER_REGISTRATION_COMPLETED` → `[  OK  ] Registered MCP server`
5. `MCP_TOOL_DISCOVERY_COMPLETED` → Merged into registration
6. `MCP_TRANSPORT_DETECTED` → Merged into registration
7. `MCP_TRANSPORT_ATTEMPT` → Removed (too granular)
8. `SCHEDULER_SERVICE_INITIALIZED` → `[  OK  ] Initialized scheduler`
9. `DATABASE_MANAGER_INITIALIZED` → `[  OK  ] Connected to database`
10. `DATABASE_TABLES_CREATED` → Merged into database line
11. `AGENT_INITIALIZED` → `[  OK  ] Loaded agents`
12. `A2A_CONFIG_LOAD_STARTED` → Removed
13. `A2A_CONFIG_LOAD_COMPLETED` → `[  OK  ] A2A service initialized`
14. `A2A_SERVER_STARTED` → Merged into A2A init

**Total to convert**: ~14 init-specific events

### Keep (runtime events):
1. `MCP_SERVER_DISCONNECTED` → Runtime
2. `MCP_SERVER_CONNECTION_LOST` → Runtime
3. `MCP_SERVER_RECONNECTING` → Runtime
4. `CLEANUP` → Shutdown
5. `OVERLORD_SHUTDOWN` → Shutdown
6. A2A runtime events (registry, health checks)
7. Memory operation events (buffer updates, failures)

---

## Missing Init Events to Add

**Memory Systems** (currently no dedicated init events):
```python
# Should emit during memory initialization
[ INFO ] Buffer memory: FIFO mode (100 messages)
[ INFO ] Persistent memory: PostgreSQL
[ WARN ] Vector memory: disabled
```

**Services Summary** (no consolidated summary):
```python
# Final line showing overall status
[  OK  ] Ready to accept requests

Startup completed in 2.3s (8 services, 1 warning, 0 errors)
```

---

## Implementation Priority

### Phase 1: Quick Wins (Kill the noise)
1. **Scheduler**: Fix 11 duplicate `SCHEDULER_SERVICE_INITIALIZED` emissions
2. **MCP Transport**: Delete `MCP_TRANSPORT_ATTEMPT`, `MCP_TRANSPORT_DETECTED` (too granular)
3. **MCP Registration**: Delete `MCP_SERVER_REGISTRATION_STARTED` (use completion only)

### Phase 2: Linux Formatting
1. Create `InitEventFormatter` class
2. Replace formation init events with banner
3. Replace service init events with formatted lines
4. Add startup summary line

### Phase 3: Deep Cleanup
1. Review A2A's 155 event uses - separate init from runtime
2. Consolidate remaining init events
3. Move verbose events to DEBUG level

---

## Action Items

1. ✅ **Analyze** - Document current state (this file)
2. 🚧 **Create Formatter** - Build InitEventFormatter with structured error support
3. 🚧 **Create Error Dataclass** - Build InitFailureInfo for structured errors
4. ⏭️ **Fix Duplicates** - Reduce scheduler's 11 duplicate events to 1
5. ⏭️ **Delete Noise** - Remove 8+ granular MCP init events
6. ⏭️ **Implement** - Replace init events with formatted output
7. ⏭️ **Test** - Verify startup logs are clean
8. ⏭️ **Document** - Update observability docs

---

## Success Criteria

- ✅ Startup log < 15 lines for typical formation (currently 20+)
- ✅ No duplicate service initialization messages
- ✅ Each service init = 1 line maximum
- ✅ Clear status indicators ([OK]/[WARN]/[FAIL])
- ✅ Startup time and summary visible
- ✅ Runtime events preserved for monitoring

---

## Files to Modify

**High Priority** (duplicates/noise):
- `src/muxi/services/scheduler/service.py` - Fix 11 duplicate inits
- `src/muxi/services/mcp/service.py` - Remove granular transport events

**Medium Priority** (formatting):
- `src/muxi/datatypes/observability.py` - Add InitEventFormatter
- `src/muxi/formation/overlord/overlord.py` - Replace init events
- `src/muxi/formation/initialization.py` - Replace database events
- `src/muxi/services/db.py` - Replace database manager events

**Low Priority** (deep cleanup):
- `src/muxi/formation/overlord/a2a_coordinator.py` - Review 155 A2A events
- Various A2A files - Separate init from runtime
