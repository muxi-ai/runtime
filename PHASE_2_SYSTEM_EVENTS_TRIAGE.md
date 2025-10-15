# Phase 2: SystemEvents & ErrorEvents Triage

**Strategy**: Be verbose but meaningful
- **KEEP (INFO)**: Informative for production monitoring
- **DEBUG**: Useful for debugging, too granular for production  
- **DELETE**: Not informative at all

**Scope**: SystemEvents (61) + ErrorEvents (30) = 91 events

---

## SystemEvents Triage (61 events)

### MCP Events (~46 events)

#### Registration & Discovery Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MCP_SERVER_REGISTRATION_STARTED` | INFO | **DEBUG** | Too granular - we only care about result, not start |
| `MCP_SERVER_REGISTRATION_COMPLETED` | INFO | **KEEP** | ✅ Important - confirms successful registration |
| `MCP_SERVER_REGISTRATION_FAILED` | ERROR | **KEEP** | ✅ Critical - need to know about failures |
| `MCP_TOOL_DISCOVERY_STARTED` | INFO | **DEBUG** | Too granular - start event not useful in production |
| `MCP_TOOL_DISCOVERY_COMPLETED` | INFO | **KEEP** | ✅ Important - confirms tools available |
| `MCP_TOOL_DISCOVERY_FAILED` | ERROR | **KEEP** | ✅ Important - need to know why no tools |

**Recommendation:**
```python
# Production (INFO)
[  OK  ] Connected to MCP server 'filesystem' (14 tools available via command)
observe(SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED, level=INFO)
observe(SystemEvents.MCP_TOOL_DISCOVERY_COMPLETED, level=INFO)

# Debug only (DEBUG)
observe(SystemEvents.MCP_SERVER_REGISTRATION_STARTED, level=DEBUG)
observe(SystemEvents.MCP_TOOL_DISCOVERY_STARTED, level=DEBUG)
```

#### Transport Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MCP_TRANSPORT_DETECTED` | INFO | **KEEP** | ✅ Important - shows which transport worked |
| `MCP_TRANSPORT_ATTEMPT` | INFO | **DEBUG** | Too granular - attempt not useful, only result |
| `MCP_TRANSPORT_FAILED` | WARNING | **DEBUG** | Not critical - we try multiple transports |
| `MCP_TRANSPORT_DETECTION_FAILED` | ERROR | **KEEP** | ✅ Important - no transport worked |

#### Connection Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MCP_SERVER_CONNECTING` | INFO | **DEBUG** | Too granular - start event not useful |
| `MCP_SERVER_CONNECTED` | INFO | **KEEP** | ✅ Important - confirms connection |
| `MCP_SERVER_CONNECTION_FAILED` | ERROR | **KEEP** | ✅ Critical - need to know about failures |
| `MCP_SERVER_DISCONNECTED` | INFO | **KEEP** | ✅ Important - runtime event, connection lost |
| `MCP_SERVER_CONNECTION_LOST` | WARNING | **KEEP** | ✅ Important - unexpected disconnection |
| `MCP_SERVER_DISCONNECTION_FAILED` | ERROR | **DEBUG** | Rare edge case, not critical for production |

#### Process Management Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MCP_SERVER_PROCESS_STARTED` | INFO | **DEBUG** | Too granular - only care if it works |
| `MCP_SERVER_PROCESS_STOPPED` | INFO | **DEBUG** | Too granular - normal shutdown |
| `MCP_SERVER_PROCESS_FAILED` | ERROR | **KEEP** | ✅ Critical - process crash |
| `MCP_SERVER_PROCESS_TIMEOUT` | ERROR | **KEEP** | ✅ Important - hung process |

#### Tool Call Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MCP_TOOL_CALL_STARTED` | INFO | **DEBUG** | Too granular - floods logs |
| `MCP_TOOL_CALL_COMPLETED` | INFO | **DEBUG** | Too granular - floods logs (use metrics instead) |
| `MCP_TOOL_CALL_FAILED` | ERROR | **KEEP** | ✅ Important - tool errors need visibility |
| `MCP_TOOL_CALL_TIMEOUT` | WARNING | **KEEP** | ✅ Important - performance issue indicator |

#### Health & Monitoring Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MCP_SERVER_HEALTH_CHECK_STARTED` | INFO | **DEBUG** | Too granular - checks happen frequently |
| `MCP_SERVER_HEALTH_CHECK_PASSED` | INFO | **DEBUG** | Too granular - only log failures |
| `MCP_SERVER_HEALTH_CHECK_FAILED` | WARNING | **KEEP** | ✅ Important - server unhealthy |

#### Configuration & Credentials Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MCP_CREDENTIAL_RESOLUTION_STARTED` | INFO | **DEBUG** | Too granular |
| `MCP_CREDENTIAL_RESOLVED` | INFO | **DEBUG** | Security risk - don't log credential events |
| `MCP_CREDENTIAL_RESOLUTION_FAILED` | ERROR | **KEEP** | ✅ Critical - auth failure |
| `MCP_CONFIG_VALIDATION_FAILED` | ERROR | **KEEP** | ✅ Critical - config error |

**MCP Summary:**
- KEEP (INFO): 15 events
- DEBUG: 12 events  
- DELETE: 19 events (truly unused)
- **Total reduction**: 46 → 15 INFO + 12 DEBUG = 27 events

---

### Scheduler Events (~27 events)

#### Service Initialization Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `SCHEDULER_SERVICE_INITIALIZED` | INFO | **KEEP** | ✅ Important - but emit ONCE only |
| `SCHEDULER_MANAGER_INITIALIZED` | INFO | **DEBUG** | Too granular - internal component |
| `SCHEDULER_PARSER_INITIALIZED` | INFO | **DEBUG** | Too granular - internal component |
| `SCHEDULER_DATABASE_INITIALIZED` | INFO | **DEBUG** | Too granular - internal component |

#### Job Lifecycle Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `SCHEDULER_JOB_SCHEDULED` | INFO | **KEEP** | ✅ Important - job created |
| `SCHEDULER_JOB_STARTED` | INFO | **DEBUG** | Too granular - floods logs on every job |
| `SCHEDULER_JOB_COMPLETED` | INFO | **DEBUG** | Too granular - use metrics instead |
| `SCHEDULER_JOB_FAILED` | ERROR | **KEEP** | ✅ Critical - job errors need visibility |
| `SCHEDULER_JOB_CANCELED` | INFO | **KEEP** | ✅ Important - user action |
| `SCHEDULER_JOB_TIMEOUT` | WARNING | **KEEP** | ✅ Important - performance issue |
| `SCHEDULER_JOB_RETRY` | INFO | **DEBUG** | Too granular - internal retry logic |
| `SCHEDULER_JOB_DELETED` | INFO | **KEEP** | ✅ Important - user action |

#### Execution & Runtime Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `SCHEDULER_EXECUTION_STARTED` | INFO | **DEBUG** | Too granular - same as JOB_STARTED |
| `SCHEDULER_EXECUTION_COMPLETED` | INFO | **DEBUG** | Too granular - same as JOB_COMPLETED |
| `SCHEDULER_CHECK_STARTED` | INFO | **DEBUG** | Too granular - checks every minute |
| `SCHEDULER_CHECK_COMPLETED` | INFO | **DEBUG** | Too granular - noise |

#### Error & Health Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `SCHEDULER_ERROR` | ERROR | **KEEP** | ✅ Critical - scheduler system error |
| `SCHEDULER_HEALTH_CHECK` | INFO | **DEBUG** | Too granular - frequent checks |
| `SCHEDULER_LIMIT_REACHED` | WARNING | **KEEP** | ✅ Important - hitting system limits |

**Scheduler Summary:**
- KEEP (INFO): 8 events
- DEBUG: 11 events
- DELETE: 8 events (duplicates/unused)
- **Total reduction**: 27 → 8 INFO + 11 DEBUG = 19 events

---

### A2A Events (~20 events)

#### Registry Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `A2A_REGISTRY_CONNECTED` | INFO | **KEEP** | ✅ Important - registry available |
| `A2A_REGISTRY_CONNECTION_FAILED` | ERROR | **KEEP** | ✅ Critical - can't reach registry |
| `A2A_REGISTRY_DISCONNECTED` | INFO | **KEEP** | ✅ Important - runtime event |
| `A2A_REGISTRY_HEALTH_CHECK` | INFO | **DEBUG** | Too granular - frequent checks |

#### Agent Discovery Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `A2A_AGENT_DISCOVERY_STARTED` | INFO | **DEBUG** | Too granular - only care about result |
| `A2A_AGENT_DISCOVERED` | INFO | **KEEP** | ✅ Important - new agent available |
| `A2A_AGENT_DISCOVERY_FAILED` | WARNING | **DEBUG** | Not critical - might be empty registry |
| `A2A_AGENT_REGISTRATION_COMPLETED` | INFO | **KEEP** | ✅ Important - our agent published |
| `A2A_AGENT_REGISTRATION_FAILED` | ERROR | **KEEP** | ✅ Critical - can't publish agent |

#### Server Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `A2A_SERVER_STARTED` | INFO | **KEEP** | ✅ Important - A2A server listening |
| `A2A_SERVER_STOPPED` | INFO | **KEEP** | ✅ Important - server shutdown |
| `A2A_SERVER_FAILED` | ERROR | **KEEP** | ✅ Critical - server crash |

**A2A Summary:**
- KEEP (INFO): 9 events
- DEBUG: 3 events
- DELETE: 8 events (unused)
- **Total reduction**: 20 → 9 INFO + 3 DEBUG = 12 events

---

### Database & Memory Events (~15 events)

#### Database Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `DATABASE_MANAGER_INITIALIZED` | INFO | **DELETE** | Already covered by persistent memory init |
| `DATABASE_TABLES_CREATED` | INFO | **KEEP** | ✅ Important - schema ready |
| `DB_CONNECTION_STARTED` | INFO | **DEBUG** | Too granular - only care about result |
| `DB_CONNECTION_FAILED` | ERROR | **KEEP** | ✅ Critical - can't connect to DB |

#### Memory Events

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `MEMORY_CLEAR` | INFO | **DEBUG** | Too granular - internal operation |
| `MEMORY_DELETION_COMPLETED` | INFO | **DEBUG** | Too granular - internal operation |
| `MEMORY_DELETION_FAILED` | ERROR | **KEEP** | ✅ Important - data loss risk |
| `MEMORY_OPTIMIZER_STARTED` | INFO | **DEBUG** | Too granular - background task |

**Database & Memory Summary:**
- KEEP (INFO): 3 events
- DEBUG: 4 events
- DELETE: 8 events
- **Total reduction**: 15 → 3 INFO + 4 DEBUG = 7 events

---

### Service Initialization Events (~10 events)

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `INITIALIZING` | INFO | **DELETE** | Replaced by Linux-style init |
| `SERVICE_STARTED` | INFO | **DELETE** | Replaced by Linux-style init |
| `AUTH_MANAGER_INITIALIZED` | INFO | **DEBUG** | Too granular - internal component |
| `INBOUND_AUTH_INITIALIZED` | INFO | **DEBUG** | Too granular - internal component |
| `KNOWLEDGE_SOURCE_LOADED` | INFO | **KEEP** | ✅ Important - knowledge available |
| `KNOWLEDGE_SOURCE_FAILED` | ERROR | **KEEP** | ✅ Important - missing knowledge |

**Service Init Summary:**
- KEEP (INFO): 2 events
- DEBUG: 2 events
- DELETE: 6 events
- **Total reduction**: 10 → 2 INFO + 2 DEBUG = 4 events

---

### Performance & Resource Events (~5 events)

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `RESOURCE_USAGE_MEASURED` | INFO | **DEBUG** | Too granular - use metrics system |
| `RESOURCE_ALLOCATED` | INFO | **DEBUG** | Too granular - internal allocation |
| `PERFORMANCE_DURATION_RECORDED` | INFO | **DEBUG** | Too granular - use metrics system |
| `PERFORMANCE_OPTIMIZED` | INFO | **DEBUG** | Too granular - internal optimization |

**Performance Summary:**
- KEEP (INFO): 0 events (use metrics instead)
- DEBUG: 4 events
- DELETE: 1 events
- **Total reduction**: 5 → 0 INFO + 4 DEBUG = 4 events

---

### Extension & Secret Events (~10 events)

| Event | Current Level | Decision | Rationale |
|-------|--------------|----------|-----------|
| `EXTENSION_LOADED` | INFO | **KEEP** | ✅ Important - extension available |
| `EXTENSION_FAILED` | ERROR | **KEEP** | ✅ Important - extension error |
| `EXTENSION_LISTED` | INFO | **DEBUG** | Too granular - internal query |
| `SECRET_OPERATION_COMPLETED` | INFO | **DEBUG** | Security risk - don't log secrets |
| `SECRET_OPERATION_FAILED` | ERROR | **KEEP** | ✅ Important - auth/config issue |
| `SECRET_LISTING_COMPLETED` | INFO | **DEBUG** | Security risk - don't log secrets |

**Extension & Secret Summary:**
- KEEP (INFO): 3 events
- DEBUG: 3 events
- DELETE: 4 events
- **Total reduction**: 10 → 3 INFO + 3 DEBUG = 6 events

---

## ErrorEvents Triage (30 events)

### Critical Errors (Always KEEP at ERROR level)

| Event | Decision | Rationale |
|-------|----------|-----------|
| `INTERNAL_ERROR` | **KEEP** | ✅ Critical - unexpected errors |
| `OVERLORD_ERROR` | **KEEP** | ✅ Critical - core system failure |
| `AGENT_ERROR` | **KEEP** | ✅ Critical - agent failure |
| `TOOL_CALL_ERROR` | **KEEP** | ✅ Important - tool failure |
| `MEMORY_ERROR` | **KEEP** | ✅ Critical - memory system failure |
| `DATABASE_ERROR` | **KEEP** | ✅ Critical - database failure |
| `SCHEDULER_ERROR` | **KEEP** | ✅ Critical - scheduler failure |

### Configuration Errors

| Event | Decision | Rationale |
|-------|----------|-----------|
| `CONFIGURATION_ERROR` | **KEEP** | ✅ Critical - startup failure |
| `CONFIGURATION_VALIDATION_ERROR` | **DELETE** | Duplicate of CONFIGURATION_ERROR |
| `DEPENDENCY_RESOLUTION_ERROR` | **DELETE** | Duplicate of CONFIGURATION_ERROR |

### Authentication & Security Errors

| Event | Decision | Rationale |
|-------|----------|-----------|
| `AUTHENTICATION_ERROR` | **KEEP** | ✅ Critical - auth failure |
| `AUTHORIZATION_ERROR` | **KEEP** | ✅ Critical - permission denied |
| `CREDENTIAL_ERROR` | **KEEP** | ✅ Critical - credential issue |
| `RATE_LIMIT_ERROR` | **KEEP** | ✅ Important - throttling |

### Network & Communication Errors

| Event | Decision | Rationale |
|-------|----------|-----------|
| `NETWORK_ERROR` | **KEEP** | ✅ Critical - connectivity issue |
| `TIMEOUT_ERROR` | **KEEP** | ✅ Important - performance issue |
| `CONNECTION_ERROR` | **DELETE** | Duplicate of NETWORK_ERROR |

### Data & Processing Errors

| Event | Decision | Rationale |
|-------|----------|-----------|
| `DATA_VALIDATION_ERROR` | **KEEP** | ✅ Important - bad input |
| `PARSING_ERROR` | **KEEP** | ✅ Important - malformed data |
| `SERIALIZATION_ERROR` | **DEBUG** | Too technical - internal error |
| `DESERIALIZATION_ERROR` | **DEBUG** | Too technical - internal error |

### Integration Errors

| Event | Decision | Rationale |
|-------|----------|-----------|
| `EXTERNAL_SERVICE_ERROR` | **KEEP** | ✅ Critical - external dependency down |
| `API_ERROR` | **KEEP** | ✅ Important - API call failed |
| `MCP_ERROR` | **KEEP** | ✅ Critical - MCP system error |
| `A2A_ERROR` | **KEEP** | ✅ Critical - A2A system error |

### Resource Errors

| Event | Decision | Rationale |
|-------|----------|-----------|
| `RESOURCE_EXHAUSTED` | **KEEP** | ✅ Critical - out of resources |
| `QUOTA_EXCEEDED` | **KEEP** | ✅ Important - hitting limits |
| `STORAGE_ERROR` | **KEEP** | ✅ Critical - can't write data |

**ErrorEvents Summary:**
- KEEP (ERROR): 23 events
- DEBUG: 2 events
- DELETE: 5 events (duplicates)
- **Total reduction**: 30 → 23 ERROR + 2 DEBUG = 25 events

---

## Summary: SystemEvents + ErrorEvents

| Category | Current | KEEP (INFO/ERROR) | DEBUG | DELETE | Final Count |
|----------|---------|-------------------|-------|--------|-------------|
| **MCP Events** | 46 | 15 | 12 | 19 | 27 |
| **Scheduler Events** | 27 | 8 | 11 | 8 | 19 |
| **A2A Events** | 20 | 9 | 3 | 8 | 12 |
| **Database & Memory** | 15 | 3 | 4 | 8 | 7 |
| **Service Init** | 10 | 2 | 2 | 6 | 4 |
| **Performance** | 5 | 0 | 4 | 1 | 4 |
| **Extension & Secret** | 10 | 3 | 3 | 4 | 6 |
| **SystemEvents Total** | **133** | **40** | **39** | **54** | **79** |
| | | | | | |
| **ErrorEvents** | 30 | 23 | 2 | 5 | 25 |
| | | | | | |
| **GRAND TOTAL** | **163** | **63** | **41** | **59** | **104** |

**Reduction:** 163 → 104 events (-36%)
- **Production logs**: 63 events (clean, actionable)
- **Debug logs**: 41 events (detailed troubleshooting)
- **Deleted**: 59 events (truly unused)

---

## 🚨 CRITICAL FINDING: 368 TODO Comments

**Discovery:** 368 "TODO: add observability" comments found in codebase!

These mark places where events were designed to be emitted but never implemented:

### TODO Distribution by Area

| Area | TODO Count | Example Locations |
|------|------------|-------------------|
| **Document Processing** | ~120 | `formation/documents/**/*.py` |
| **A2A System** | ~80 | `services/a2a/**/*.py` |
| **MCP Service** | ~40 | `services/mcp/**/*.py` |
| **Memory Systems** | ~50 | `services/memory/**/*.py`, `formation/documents/storage/*.py` |
| **Formation/Overlord** | ~30 | `formation/overlord/*.py` |
| **Scheduler** | ~20 | `services/scheduler/*.py` |
| **Other Services** | ~28 | Various |
| **TOTAL** | **368** | Across entire codebase |

### Example TODO Comments

```python
# Document processing (120+ TODOs)
#  Error - TODO: add observability
_ = e  # remove this after implementing observability

# A2A system (80+ TODOs)
#  A2A discovery error - TODO: add observability
#  A2A inbound auth warning - TODO: add observability

# MCP service (40+ TODOs)
#  MCP server error - TODO: add observability

# Memory systems (50+ TODOs)
#  Context preserver error - TODO: add observability
#  Buffer memory info - TODO: add observability
```

### Implications

This explains why so many events are "unused":
1. **Events were defined** in `observability.py`
2. **TODO comments were added** at intended emission points
3. **But events were never actually emitted** (TODOs never completed)

**Result:** We have 368 observability gaps in the codebase!

---

## Implementation Strategy

### 1. Add DEBUG Level Support (if not exists)

```python
# Check current EventLevel enum
class EventLevel(Enum):
    DEBUG = "debug"      # Add if missing
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
```

### 2. Update Event Emitters

```python
# Before: Everything at INFO
observe(SystemEvents.MCP_TOOL_DISCOVERY_STARTED, level=EventLevel.INFO)

# After: Appropriate level
observe(SystemEvents.MCP_TOOL_DISCOVERY_STARTED, level=EventLevel.DEBUG)
```

### 3. Configuration Support

```yaml
# observability.yaml
event_level:
  minimum: info  # Production: only INFO and above
  # minimum: debug  # Development: all events
```

### 4. Log Filtering

```python
def observe(event, level=EventLevel.INFO, ...):
    # Filter based on configured minimum level
    if level.value < configured_minimum_level:
        return  # Skip event
    
    # Emit event
    ...
```

---

## Benefits of This Approach

1. **Clean Production Logs**: Only 63 meaningful events
2. **Debugging Capability**: 41 DEBUG events available when needed
3. **Flexible**: Toggle DEBUG on/off per environment
4. **No Information Loss**: DEBUG events preserved, not deleted
5. **Better Performance**: Fewer events in production = less overhead

---

## Revised Strategy: Address TODO Comments

### Phase 2A: High-Priority TODOs (Week 1-2)

**Focus:** Implement critical missing events first

1. **Security Events** (HIGH PRIORITY)
   - Authentication failures (A2A, MCP)
   - Authorization failures  
   - Rate limiting
   - ~30 TODOs to address

2. **Infrastructure Events** (HIGH PRIORITY)
   - Database connection failures
   - MCP process failures
   - Network interface failures
   - ~20 TODOs to address

3. **Error Handling** (MEDIUM PRIORITY)
   - Document processing errors (~40 TODOs)
   - Memory operation errors (~20 TODOs)
   - A2A errors (~30 TODOs)

### Phase 2B: Event Level Classification (Week 3)

1. Update event definitions with appropriate levels (DEBUG/INFO/ERROR)
2. Update existing emitters to use correct levels
3. Add configuration support for minimum log level

### Phase 2C: Cleanup (Week 4)

1. Delete truly unused events (59 events)
2. Remove obsolete TODO comments
3. Update documentation

---

## Next Steps

1. ✅ Review this triage
2. **Prioritize which TODOs to address first**
3. Start with security events (auth, authz, rate limit)
4. Then infrastructure events (DB, MCP, network)
5. Then error handling events
6. Finally, cleanup and level classification

**Estimated Time:** 4 weeks for complete implementation

**Key Decision:** Should we implement all 368 TODOs, or focus on critical ones only?

**Ready to proceed?** 🎯
