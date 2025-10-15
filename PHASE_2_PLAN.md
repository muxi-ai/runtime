# Phase 2: Runtime Event Cleanup - Implementation Plan

**Issue:** [#84 - EPIC: Observability Events Cleanup & Linux-Style Initialization](https://github.com/muxi-ai/runtime/issues/84)  
**Phase:** 2 of 4 (Event Consolidation & Cleanup)  
**Status:** 📋 **PLANNING**  
**Dependencies:** Phase 1 complete ✅  
**Estimated Duration:** 2-3 weeks

---

## Goals

1. **Reduce event count by 50%**: 216 events → ~100 events
2. **Remove unused events**: Delete 161 events (74.5%) that are never/rarely used
3. **Consolidate redundant events**: Merge duplicate event types
4. **Standardize naming**: Apply consistent `service.object.action` pattern
5. **Add missing events**: Fill gaps for new features (topics, synopsis, preferences)

---

## Current State Analysis

### Event Statistics (from audit)
- **Total Events**: 216
- **Never Used**: 63 (29.2%) → **DELETE**
- **Rarely Used (<5)**: 98 (45.4%) → **REVIEW**
- **Frequently Used (≥5)**: 55 (25.5%) → **KEEP**

### Event Categories

| Category | Total | Never Used | Rarely Used | Frequently Used | Target |
|----------|-------|------------|-------------|----------------|--------|
| **ConversationEvents** | 59 | 37 | 8 | 14 | 25 (-58%) |
| **SystemEvents** | 61 | 18 | 30 | 13 | 30 (-51%) |
| **ErrorEvents** | 30 | 8 | 17 | 5 | 15 (-50%) |
| **APIEvents** | 32 | 1 | 20 | 11 | 20 (-38%) |
| **ServerEvents** | 35 | 0 | 23 | 12 | 20 (-43%) |
| **TOTAL** | **216** | **63** | **98** | **55** | **~110** |

---

## Implementation Strategy

### Step 1: Delete Never-Used Events (63 events)
**Priority**: High  
**Effort**: Low  
**Risk**: Low (zero production impact)

**Approach:**
1. Review audit list of 63 never-used events
2. Verify with code search (grep for event usage)
3. Delete from event enums
4. Run tests to ensure no breaking changes
5. Document deleted events in migration guide

**Expected Outcome**: 216 → 153 events (-29%)

---

### Step 2: Consolidate MCP Events (46 → 10 events)
**Priority**: High  
**Effort**: Medium  
**Risk**: Medium (MCP is heavily used)

**Problem**: MCP has 80+ events, many redundant

**Current MCP Events to Consolidate:**
```python
# Registration (3 events → 1 event)
MCP_SERVER_REGISTRATION_STARTED    # DELETE
MCP_SERVER_REGISTRATION_COMPLETED  # DELETE
MCP_SERVER_REGISTRATION_FAILED     # KEEP (rename to MCP_SERVER_REGISTERED with status)

# Transport Detection (4 events → 1 event)
MCP_TRANSPORT_DETECTED             # DELETE
MCP_TRANSPORT_ATTEMPT              # DELETE  
MCP_TRANSPORT_FAILED               # DELETE
MCP_TRANSPORT_DETECTION_FAILED     # KEEP (rename to MCP_TRANSPORT_DETECTED with status)

# Tool Discovery (2 events → 1 event)
MCP_TOOL_DISCOVERY_STARTED         # DELETE
MCP_TOOL_DISCOVERY_COMPLETED       # KEEP (rename to MCP_TOOLS_DISCOVERED)

# Connection (3 events → 1 event)
MCP_SERVER_CONNECTING              # DELETE
MCP_SERVER_CONNECTED               # KEEP
MCP_SERVER_CONNECTION_FAILED       # DELETE (merge into MCP_SERVER_CONNECTED with status)
```

**New Consolidated Events:**
```python
class SystemEvents:
    # Registration lifecycle (1 event)
    MCP_SERVER_REGISTERED = "mcp.server.registered"  # status: success/failed
    
    # Transport lifecycle (1 event)
    MCP_TRANSPORT_DETECTED = "mcp.transport.detected"  # status: success/failed
    
    # Tool discovery (1 event)
    MCP_TOOLS_DISCOVERED = "mcp.tools.discovered"  # count, status
    
    # Runtime operations (keep existing)
    MCP_SERVER_DISCONNECTED = "mcp.server.disconnected"
    MCP_SERVER_CONNECTION_LOST = "mcp.server.connection_lost"
    
    # Errors (keep existing)
    MCP_SERVER_ERROR = "mcp.server.error"
    MCP_TOOL_CALL_FAILED = "mcp.tool.call_failed"
```

**Migration:**
```python
# Before: 3 events for registration
observe(SystemEvents.MCP_SERVER_REGISTRATION_STARTED, ...)
observe(SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED, ...)

# After: 1 event with status
observe(
    SystemEvents.MCP_SERVER_REGISTERED,
    data={"server": "filesystem", "tools": 14, "status": "success"}
)
```

**Expected Outcome**: 153 → 117 events (-36 events)

---

### Step 3: Consolidate Scheduler Events (27 → 8 events)
**Priority**: High  
**Effort**: Low  
**Risk**: Low

**Problem**: `SCHEDULER_SERVICE_INITIALIZED` emitted from 11+ locations

**Current Scheduler Events to Consolidate:**
```python
# Initialization (multiple locations → 1 event)
SCHEDULER_SERVICE_INITIALIZED      # Used 11+ times!

# Job lifecycle (keep separate)
SCHEDULER_JOB_SCHEDULED
SCHEDULER_JOB_STARTED
SCHEDULER_JOB_COMPLETED
SCHEDULER_JOB_FAILED
SCHEDULER_JOB_CANCELED
```

**Solution:**
1. Remove duplicate `SCHEDULER_SERVICE_INITIALIZED` emissions
2. Keep only ONE emission at end of scheduler init
3. Consolidate job events with status field

**New Consolidated Events:**
```python
class SystemEvents:
    SCHEDULER_INITIALIZED = "scheduler.initialized"
    
    SCHEDULER_JOB_SCHEDULED = "scheduler.job.scheduled"
    SCHEDULER_JOB_STATUS_CHANGED = "scheduler.job.status_changed"  # Replaces started/completed/failed/canceled
    SCHEDULER_JOB_DELETED = "scheduler.job.deleted"
```

**Expected Outcome**: 117 → 109 events (-8 events)

---

### Step 4: Clean Up Conversation Events (59 → 25 events)
**Priority**: Medium  
**Effort**: Medium  
**Risk**: Medium (affects observability)

**Problem**: 37 never-used conversation events, overly granular

**Events to DELETE (never used):**
```python
# Over-granular agent thinking (8 events)
AGENT_THINKING_STARTED
AGENT_THINKING_STOPPED
AGENT_REASONING_STEP
AGENT_DECISION_MADE
AGENT_CONFIDENCE_LOW
AGENT_CONFIDENCE_HIGH
AGENT_REFLECTION
AGENT_SELF_CORRECTION

# Never-used lifecycle events (15+ events)
REQUEST_PREPROCESSING
REQUEST_POSTPROCESSING
RESPONSE_PREPROCESSING
RESPONSE_POSTPROCESSING
... (more)
```

**Events to KEEP (frequently used):**
```python
REQUEST_RECEIVED           # Used 50+ times
REQUEST_COMPLETED          # Used 40+ times
AGENT_SELECTED             # Used 30+ times
TOOL_CALL_INITIATED        # Used 25+ times
CLARIFICATION_REQUESTED    # Used 20+ times
```

**Events to ADD (missing):**
```python
REQUEST_TOPICS_EXTRACTED   # ✅ Already added!
MEMORY_SYNOPSIS_GENERATED  # New feature
USER_PREFERENCE_DETECTED   # New feature
WORKFLOW_REPLANNED         # Existing feature, missing event
SECURITY_VIOLATION         # Existing feature, missing event
```

**Expected Outcome**: 109 → 75 events (-34 events)

---

### Step 5: Standardize Event Naming
**Priority**: Medium  
**Effort**: Medium  
**Risk**: High (breaking change)

**Current Problems:**
- Inconsistent patterns: `MCP_SERVER_CONNECTED` vs `mcp.server.connected`
- Mix of SCREAMING_CASE and dot.notation
- Unclear hierarchy

**New Standard**: `service.object.action` (all lowercase with dots)

**Examples:**
```python
# Before (inconsistent)
MCP_SERVER_CONNECTED
SCHEDULER_SERVICE_INITIALIZED
A2A_AGENT_DISCOVERED

# After (consistent)
mcp.server.connected
scheduler.initialized
a2a.agent.discovered
```

**Migration Strategy:**
1. Add new names as aliases (keep old names for backward compatibility)
2. Update all emitters to use new names
3. Deprecation warnings for old names
4. Remove old names in next major version

**OR** (simpler, since no external consumers yet):
1. Just rename everything
2. Update all emitters
3. Document in migration guide

**Recommendation**: Simple rename (no external API consumers yet)

---

### Step 6: Add Missing Critical Events
**Priority**: Medium  
**Effort**: Low  
**Risk**: Low

**Missing Events to Add:**
```python
class ConversationEvents:
    # Topic tagging (already exists!)
    REQUEST_TOPICS_EXTRACTED = "conversation.topics.extracted"
    
    # Memory features
    MEMORY_SYNOPSIS_GENERATED = "memory.synopsis.generated"
    USER_PREFERENCE_DETECTED = "user.preference.detected"
    USER_PREFERENCE_UPDATED = "user.preference.updated"
    
    # Workflow features
    WORKFLOW_COMPLEXITY_ANALYZED = "workflow.complexity.analyzed"
    WORKFLOW_REPLANNED = "workflow.replanned"
    WORKFLOW_APPROVED = "workflow.approved"
    WORKFLOW_REJECTED = "workflow.rejected"
    
    # Security
    SECURITY_VIOLATION_DETECTED = "security.violation.detected"
    SECURITY_ACTION_BLOCKED = "security.action.blocked"
```

**Expected Outcome**: 75 → 85 events (+10 events)

---

## Implementation Tasks

### Task Breakdown

#### Phase 2.1: Delete Unused Events (Week 1)
- [ ] Review audit list of 63 never-used events
- [ ] Verify each event with code search
- [ ] Delete events from `src/muxi/datatypes/observability.py`
- [ ] Run full test suite
- [ ] Update documentation

**Deliverable**: 216 → 153 events (-29%)

#### Phase 2.2: Consolidate MCP & Scheduler (Week 1-2)
- [ ] Consolidate MCP events (46 → 10)
- [ ] Update MCP service emitters
- [ ] Consolidate scheduler events (27 → 8)
- [ ] Update scheduler service emitters
- [ ] Test MCP and scheduler functionality
- [ ] Update documentation

**Deliverable**: 153 → 109 events (-28%)

#### Phase 2.3: Clean Conversation Events (Week 2)
- [ ] Delete 37 never-used conversation events
- [ ] Review rarely-used events
- [ ] Add 10 missing events
- [ ] Update emitters
- [ ] Test conversation lifecycle
- [ ] Update documentation

**Deliverable**: 109 → 85 events (-22%)

#### Phase 2.4: Standardize Naming (Week 2-3)
- [ ] Define new naming convention
- [ ] Create mapping of old → new names
- [ ] Update all event definitions
- [ ] Update all emitters (grep + replace)
- [ ] Run full test suite
- [ ] Create migration guide

**Deliverable**: Clean, consistent event names

#### Phase 2.5: Documentation & Testing (Week 3)
- [ ] Create comprehensive event reference guide
- [ ] Document all events with examples
- [ ] Update observability.yaml examples
- [ ] Add E2E tests for new events
- [ ] Update CHANGELOG

**Deliverable**: Complete documentation

---

## Breaking Changes & Migration

### Breaking Changes
1. **63 events deleted** - Any code using these will break
2. **Event names changed** - All consumers must update
3. **Event structure changed** - Some data fields consolidated

### Backward Compatibility Strategy

**Option 1: Hard Break (Recommended)**
- Just delete/rename everything
- Document in migration guide
- No external consumers yet, so low risk

**Option 2: Gradual Migration**
- Keep old events as deprecated aliases
- Emit both old and new events for 1 release
- Remove old events in next major version

**Recommendation**: Option 1 (hard break) since:
- No external consumers of events yet
- Cleaner codebase
- Faster implementation
- Pre-1.0 so breaking changes expected

### Migration Guide
Create `OBSERVABILITY_MIGRATION.md` with:
- Complete list of deleted events
- Mapping of renamed events
- Examples of data structure changes
- Code snippets for common patterns

---

## Success Criteria

### Quantitative
- ✅ Event count reduced by 50%: 216 → ~110 events
- ✅ All never-used events deleted: 63 → 0
- ✅ Rarely-used events reviewed and consolidated: 98 → ~40
- ✅ 100% consistent naming pattern
- ✅ All tests passing

### Qualitative
- ✅ Logs are cleaner and more meaningful
- ✅ Events provide actionable intelligence
- ✅ Easy to find events in codebase
- ✅ Clear separation of concerns
- ✅ Well-documented event catalog

---

## Risk Mitigation

### High Risk: Breaking Changes
**Mitigation:**
- Comprehensive testing before merge
- Create detailed migration guide
- Update all internal usages first
- Gradual rollout if external consumers exist

### Medium Risk: Missing Important Events
**Mitigation:**
- Review audit carefully
- Check with stakeholders before deleting
- Keep events if any doubt
- Easy to re-add if needed

### Low Risk: Performance Impact
**Mitigation:**
- Event emission is already async
- Fewer events = better performance
- Test with high load

---

## Timeline

**Week 1: Cleanup**
- Mon-Tue: Delete 63 unused events
- Wed-Fri: Consolidate MCP events

**Week 2: Consolidation**
- Mon-Tue: Consolidate scheduler events
- Wed-Thu: Clean conversation events
- Fri: Testing

**Week 3: Standardization**
- Mon-Wed: Rename all events
- Thu-Fri: Documentation & testing

**Total: 3 weeks**

---

## Next Phase Preview: Phase 3

### Phase 3: Standardize Event Structure
**Goals:**
- Consistent data fields across all events
- Standard metadata (formation_id, user_id, session_id)
- Improved event descriptions
- Better error context

**Timeline:** 1-2 weeks after Phase 2

---

## Appendix A: Event Deletion Checklist

### Never-Used Events to Delete (63 total)

#### ConversationEvents (37 events)
```
- AGENT_THINKING_STARTED
- AGENT_THINKING_STOPPED
- AGENT_REASONING_STEP
- AGENT_DECISION_MADE
- AGENT_CONFIDENCE_LOW
- AGENT_CONFIDENCE_HIGH
- AGENT_REFLECTION
- AGENT_SELF_CORRECTION
- REQUEST_PREPROCESSING
- REQUEST_POSTPROCESSING
- RESPONSE_PREPROCESSING
- RESPONSE_POSTPROCESSING
... (complete list in audit)
```

#### SystemEvents (18 events)
```
- MCP_SERVER_PROCESS_STARTED
- MCP_SERVER_REGISTRATION_STARTED
- MCP_TRANSPORT_ATTEMPT
... (complete list in audit)
```

#### ErrorEvents (8 events)
```
- CONFIGURATION_VALIDATION_ERROR
- DEPENDENCY_RESOLUTION_ERROR
... (complete list in audit)
```

---

## Appendix B: Event Consolidation Examples

### Before: MCP Server Registration (3 events)
```python
# Event 1
observe(SystemEvents.MCP_SERVER_REGISTRATION_STARTED, {
    "server": "filesystem"
})

# Event 2 (2 seconds later)
observe(SystemEvents.MCP_TOOL_DISCOVERY_COMPLETED, {
    "server": "filesystem",
    "tools": 14
})

# Event 3 (immediately after)
observe(SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED, {
    "server": "filesystem",
    "tools": 14
})
```

### After: MCP Server Registration (1 event)
```python
observe(SystemEvents.MCP_SERVER_REGISTERED, {
    "server": "filesystem",
    "tools": 14,
    "transport": "command",
    "duration_ms": 234,
    "status": "success"
})
```

---

## Appendix C: Resources

### Key Files
- `src/muxi/datatypes/observability.py` - Event definitions
- `src/muxi/services/observability/` - Observability infrastructure
- `observability_audit.csv` - Complete event usage audit
- `INIT_EVENTS_ANALYSIS.md` - Init event analysis
- `OBSERVABILITY_AUDIT_ANALYSIS.md` - Full audit report

### Tools
- `scripts/audit_observability.py` - Event usage auditor
- `grep` - Find event usages in codebase
- `pytest` - Test suite

---

**Status**: Ready to start Phase 2  
**Next Action**: Review this plan, get approval, start with Task 2.1 (Delete unused events)
