# Phase 2: Implement 368 Observability TODOs - Implementation Plan

**Finding**: 368 "TODO: add observability" comments found in codebase  
**Status**: Planning  
**Priority**: High - These are observability gaps, not just cleanup

---

## Executive Summary

The codebase has 368 locations marked with "TODO: add observability" comments. These are places where:
1. Events were designed to be emitted
2. Code was written with placeholder comments
3. But actual event emission was never implemented

This creates **368 blind spots** in our observability system.

---

## TODO Distribution & Priority

### High Priority: Security & Infrastructure (50 TODOs)

#### Security Events (~30 TODOs)
**Why Critical**: Security monitoring, compliance, audit trail

| Area | TODOs | Event Types | Example Locations |
|------|-------|-------------|-------------------|
| **A2A Authentication** | ~15 | AUTH_FAILED, AUTH_SUCCESS | `services/a2a/auth/inbound.py` |
| **MCP Authentication** | ~8 | CREDENTIAL_ERROR, AUTH_FAILED | `services/mcp/auth/*.py` |
| **Authorization** | ~7 | AUTHORIZATION_FAILED | `formation/overlord/*.py` |

**Impact**: Can't detect:
- Brute force attacks
- Unauthorized access attempts
- Credential theft/misuse
- Permission escalation

#### Infrastructure Events (~20 TODOs)
**Why Critical**: Reliability monitoring, incident response

| Area | TODOs | Event Types | Example Locations |
|------|-------|-------------|-------------------|
| **Database Failures** | ~5 | DB_CONNECTION_FAILED | `services/db.py` |
| **MCP Process Crashes** | ~8 | MCP_PROCESS_FAILED | `services/mcp/service.py` |
| **Network Failures** | ~7 | NETWORK_ERROR | `services/a2a/*.py` |

**Impact**: Can't detect:
- Database outages
- MCP server crashes
- Network connectivity issues
- Service unavailability

---

### Medium Priority: Error Handling (140 TODOs)

#### Document Processing Errors (~40 TODOs)
**Why Important**: User experience, data quality

| Area | TODOs | Event Types | Example Locations |
|------|-------|-------------|-------------------|
| **Error Handler** | ~15 | DOCUMENT_PROCESSING_FAILED | `formation/documents/experience/error_handler.py` |
| **Chunk Manager** | ~10 | CONTENT_EXTRACTION_FAILED | `formation/documents/storage/chunk_manager.py` |
| **Workflow** | ~15 | WORKFLOW_ERROR | `formation/documents/workflow/*.py` |

#### A2A System Errors (~40 TODOs)
**Why Important**: Distributed system reliability

| Area | TODOs | Event Types | Example Locations |
|------|-------|-------------|-------------------|
| **Discovery** | ~20 | A2A_DISCOVERY_FAILED | `services/a2a/discovery.py` |
| **Communication** | ~10 | A2A_MESSAGE_FAILED | `services/a2a/*.py` |
| **Auth** | ~10 | A2A_AUTH_FAILED | `services/a2a/auth/*.py` |

#### Memory System Errors (~30 TODOs)
**Why Important**: Data integrity, performance

| Area | TODOs | Event Types | Example Locations |
|------|-------|-------------|-------------------|
| **Context Preserver** | ~15 | MEMORY_ERROR | `formation/documents/workflow/context_preserver.py` |
| **Buffer Memory** | ~10 | MEMORY_OPERATION_FAILED | `formation/documents/storage/buffer_memory.py` |
| **Metadata Store** | ~5 | STORAGE_ERROR | `formation/documents/storage/metadata_store.py` |

#### MCP Service Errors (~30 TODOs)
**Why Important**: Tool integration reliability

| Area | TODOs | Event Types | Example Locations |
|------|-------|-------------|-------------------|
| **Connection** | ~15 | MCP_CONNECTION_FAILED | `services/mcp/service.py` |
| **Tool Calls** | ~10 | MCP_TOOL_CALL_FAILED | `services/mcp/*.py` |
| **Auth** | ~5 | MCP_AUTH_FAILED | `services/mcp/auth/*.py` |

---

### Low Priority: Informational Events (178 TODOs)

#### Document Processing Info (~80 TODOs)
**Why Lower Priority**: Useful for debugging but not critical

| Area | TODOs | Example Locations |
|------|-------|-------------------|
| **Acknowledgment Generator** | ~15 | `formation/documents/experience/acknowledgment_generator.py` |
| **Workflow Integrator** | ~20 | `formation/documents/workflow/workflow_integrator.py` |
| **Buffer Memory** | ~15 | `formation/documents/storage/buffer_memory.py` |
| **Metadata Store** | ~10 | `formation/documents/storage/metadata_store.py` |
| **Cross-Reference** | ~10 | `formation/documents/workflow/cross_reference_manager.py` |
| **Context Preserver** | ~10 | `formation/documents/workflow/context_preserver.py` |

#### A2A System Info (~40 TODOs)
| Area | TODOs | Example Locations |
|------|-------|-------------------|
| **Discovery** | ~20 | `services/a2a/discovery.py` |
| **Auth** | ~15 | `services/a2a/auth/inbound.py` |
| **Communication** | ~5 | `services/a2a/*.py` |

#### Other Services (~58 TODOs)
| Area | TODOs | Example Locations |
|------|-------|-------------------|
| **Scheduler** | ~20 | `services/scheduler/*.py` |
| **Overlord** | ~15 | `formation/overlord/*.py` |
| **Memory** | ~10 | `services/memory/*.py` |
| **Various** | ~13 | Multiple files |

---

## Implementation Strategy

### Phase 2A: Security & Infrastructure TODOs (Weeks 1-2)

**Goal**: Close critical observability gaps for security and reliability

#### Week 1: Security Events (30 TODOs)

**Day 1-2: A2A Authentication**
- File: `services/a2a/auth/inbound.py`
- TODOs: ~15 locations
- Events to add:
  - `AUTHENTICATION_FAILED` - Failed auth attempts
  - `AUTHORIZATION_FAILED` - Permission denials
  - `TOKEN_INVALID` - Bad tokens
  
**Implementation:**
```python
# Before (TODO comment)
#  A2A inbound auth error - TODO: add observability
return False, None, f"Authentication error: {str(e)}"

# After (emit event)
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
return False, None, f"Authentication error: {str(e)}"
```

**Day 3-4: MCP Authentication**
- File: `services/mcp/auth/*.py`
- TODOs: ~8 locations
- Events: Same as A2A (AUTHENTICATION_FAILED, etc.)

**Day 5: Authorization**
- Files: `formation/overlord/*.py`, `services/*/permissions.py`
- TODOs: ~7 locations
- Events: `AUTHORIZATION_FAILED`

#### Week 2: Infrastructure Events (20 TODOs)

**Day 1: Database Failures**
- File: `services/db.py`
- TODOs: ~5 locations
- Events: `DB_CONNECTION_FAILED`, `DATABASE_ERROR`

**Day 2-3: MCP Process Crashes**
- File: `services/mcp/service.py`
- TODOs: ~8 locations
- Events: `MCP_SERVER_PROCESS_FAILED`, `MCP_SERVER_TIMEOUT`

**Day 4-5: Network Failures**
- Files: `services/a2a/*.py`, `services/mcp/*.py`
- TODOs: ~7 locations
- Events: `NETWORK_ERROR`, `CONNECTION_TIMEOUT`

---

### Phase 2B: Error Handling TODOs (Weeks 3-4)

**Goal**: Improve error visibility across all subsystems

#### Week 3: Document Processing & A2A Errors (80 TODOs)

**Day 1-2: Document Processing**
- Files: `formation/documents/experience/error_handler.py` + others
- TODOs: ~40 locations
- Events:
  - `DOCUMENT_PROCESSING_FAILED`
  - `CONTENT_EXTRACTION_FAILED`
  - `WORKFLOW_ERROR`

**Day 3-5: A2A System**
- Files: `services/a2a/discovery.py` + others
- TODOs: ~40 locations
- Events:
  - `A2A_DISCOVERY_FAILED`
  - `A2A_MESSAGE_FAILED`
  - `A2A_COMMUNICATION_ERROR`

#### Week 4: Memory & MCP Errors (60 TODOs)

**Day 1-2: Memory Systems**
- Files: `formation/documents/workflow/*.py`, `storage/*.py`
- TODOs: ~30 locations
- Events:
  - `MEMORY_ERROR`
  - `MEMORY_OPERATION_FAILED`
  - `STORAGE_ERROR`

**Day 3-5: MCP Service**
- Files: `services/mcp/service.py` + others
- TODOs: ~30 locations
- Events:
  - `MCP_CONNECTION_FAILED`
  - `MCP_TOOL_CALL_FAILED`
  - `MCP_ERROR`

---

### Phase 2C: Informational TODOs (Weeks 5-6) - OPTIONAL

**Goal**: Add comprehensive debugging visibility

This phase is **optional** - only do if we want complete observability coverage.

#### Week 5: Document Processing Info (80 TODOs)
- Files: All document processing subsystem
- Events: Various INFO level events
- Focus: Workflow tracking, context management

#### Week 6: Service Info (98 TODOs)
- Files: A2A, Scheduler, Overlord, Memory
- Events: Various INFO level events
- Focus: Operation tracking, state changes

---

## Event Emission Pattern

### Standard Pattern

```python
# 1. Find the TODO comment
#  Error - TODO: add observability
_ = e  # remove this after implementing observability

# 2. Replace with proper event emission
observe(
    event_type=ErrorEvents.APPROPRIATE_ERROR,
    level=EventLevel.ERROR,  # or WARNING, INFO
    data={
        "component": "component_name",
        "error": str(e),
        "context": relevant_context
    },
    description="Human-readable description of what happened"
)
# Remove the '_ = e' line
```

### Error Handling Pattern

```python
# Before
except Exception as e:
    #  Error - TODO: add observability
    _ = e
    return None

# After
except Exception as e:
    observe(
        ErrorEvents.OPERATION_FAILED,
        level=EventLevel.ERROR,
        data={
            "operation": "operation_name",
            "error_type": type(e).__name__,
            "error": str(e),
            "traceback": traceback.format_exc()
        },
        description=f"Operation failed: {operation_name}"
    )
    return None  # or raise, depending on error handling strategy
```

### Info Event Pattern

```python
# Before
#  Info - TODO: add observability

# After
observe(
    SystemEvents.OPERATION_COMPLETED,
    level=EventLevel.INFO,
    data={
        "operation": "operation_name",
        "duration_ms": duration,
        "result": result_summary
    },
    description=f"Operation completed: {operation_name}"
)
```

---

## Testing Strategy

### Per TODO Implementation

1. **Unit Test**: Verify event is emitted
   ```python
   def test_auth_failure_emits_event():
       with capture_events() as events:
           with pytest.raises(AuthenticationError):
               authenticate(bad_credentials)
       
       assert any(e.type == ErrorEvents.AUTHENTICATION_FAILED for e in events)
   ```

2. **Integration Test**: Verify event data is correct
3. **Manual Test**: Check logs contain useful information

### Batch Testing

After implementing each category (security, infrastructure, etc.):
1. Run full test suite
2. Check for new events in test logs
3. Verify no regressions
4. Update documentation

---

## Success Criteria

### Phase 2A (Critical TODOs)
- ✅ All 30 security TODOs implemented
- ✅ All 20 infrastructure TODOs implemented
- ✅ Security events visible in logs
- ✅ Infrastructure failures visible in logs
- ✅ No regressions in test suite

### Phase 2B (Error Handling TODOs)
- ✅ All 140 error handling TODOs implemented
- ✅ Errors visible in logs with useful context
- ✅ Can debug issues from logs alone
- ✅ No regressions

### Phase 2C (Optional - Info TODOs)
- ✅ All 178 info TODOs implemented
- ✅ Complete operation visibility
- ✅ Can trace full request flow through logs

---

## Deliverables

### Documentation
1. **Event Emission Guide**: How to emit events properly
2. **Event Catalog Update**: New events documented
3. **Migration Guide**: Changes for log consumers
4. **Debugging Guide**: How to use new events

### Code Changes
1. **~368 files modified**: Add event emissions
2. **~368 TODO comments removed**: Clean up after implementation
3. **Test files**: Add/update tests for new events

### Metrics
- Event emission coverage: 0% → 100%
- Observability gaps: 368 → 0
- Security visibility: Minimal → Complete
- Error visibility: Partial → Complete

---

## Risk Assessment

### Low Risk
- Adding events is additive (no breaking changes)
- Events already defined (just need emission)
- Clear patterns from existing code

### Medium Risk
- Performance impact (368 new event emissions)
  - **Mitigation**: Events are async, minimal overhead
  - **Mitigation**: Can disable via log level
- Test suite changes needed
  - **Mitigation**: Add tests incrementally

### High Risk
- None identified

---

## Timeline & Effort

### Minimal Scope (Recommended)
**Phase 2A only** - Security & Infrastructure
- **Duration**: 2 weeks
- **TODOs**: 50 (critical)
- **Impact**: Close major observability gaps

### Standard Scope
**Phase 2A + 2B** - Add all error handling
- **Duration**: 4 weeks
- **TODOs**: 190 (critical + errors)
- **Impact**: Complete error visibility

### Complete Scope
**Phase 2A + 2B + 2C** - Everything
- **Duration**: 6 weeks
- **TODOs**: 368 (all)
- **Impact**: Complete observability coverage

---

## Recommendation

**Start with Phase 2A (2 weeks)** focusing on security and infrastructure TODOs:

1. **Week 1**: Security events (auth, authz, rate limit)
2. **Week 2**: Infrastructure events (DB, MCP, network)

Then **reassess**:
- If security/infrastructure events prove valuable → Continue with Phase 2B
- If overhead is too high → Stop and evaluate
- If we need complete coverage → Continue with Phase 2C

**Rationale**: 
- Phase 2A gives us the most important 14% of TODOs (50/368)
- Closes critical security and reliability gaps
- Fast win (2 weeks) with high impact
- Can evaluate value before committing to remaining 86%

---

## Next Steps

1. ✅ Review this plan
2. Decide on scope (2A only, 2A+2B, or full)
3. Create detailed task list for chosen scope
4. Start implementation with Week 1, Day 1 (A2A Auth)
5. Track progress against TODOs remaining

**Ready to start?** 🎯
