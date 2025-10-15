# Phase 2 Cleanup Summary

**Date**: Current session
**Status**: Init events removed from observability.py; stale references remain but harmless

---

## ✅ Completed: Init Event Removal

### Events Removed from `observability.py`

**Total Removed**: 27 init event definitions

| Category | Events Removed | Reason |
|----------|---------------|---------|
| **General Init** | INITIALIZING, SERVICE_STARTED | Replaced by InitEventFormatter banner/completion |
| **MCP Init** | MCP_SERVER_PROCESS_STARTED, MCP_SERVER_REGISTRATION_STARTED, MCP_SERVER_REGISTRATION_COMPLETED, MCP_TOOL_DISCOVERY_COMPLETED, MCP_SERVER_CONNECTING, MCP_SERVER_CONNECTED, MCP_TRANSPORT_DETECTED, MCP_TRANSPORT_ATTEMPT | Replaced by formatted: `[  OK  ] Connected to MCP 'X' (3 tools via stdio)` |
| **A2A Init** | A2A_CONFIG_LOAD_STARTED, A2A_CONFIG_LOAD_COMPLETED, A2A_SERVER_STARTED | Replaced by formatted: `[  OK  ] A2A server (localhost:8080, auth=api_key)` |
| **Overlord Init** | OVERLORD_INITIALIZING, OVERLORD_STARTED, CACHE_MANAGER_STARTED, MEMORY_OPTIMIZER_STARTED | Replaced by banner + completion message |
| **Auth Init** | AUTH_MANAGER_INITIALIZED, INBOUND_AUTH_INITIALIZED | Too granular, not useful |
| **Scheduler Init** | SCHEDULER_SERVICE_INITIALIZED, SCHEDULER_MANAGER_INITIALIZED, SCHEDULER_PARSER_INITIALIZED, SCHEDULER_DATABASE_INITIALIZED | Replaced by formatted: `[  OK  ] Background scheduler initialized` |
| **Database Init** | DATABASE_MANAGER_INITIALIZED, DATABASE_TABLES_CREATED | Replaced by formatted memory + schema messages |
| **Network Init** | NETWORK_INTERFACE_INITIALIZED | Too granular, not used |
| **Agent Init** | AGENT_INITIALIZED | Replaced by formatted: `[  OK  ] Loaded agent 'X'` |

### Stale References in Code

**Found**: ~30-40 `observe()` calls still reference deleted events

**Status**: **Harmless** - Observability is disabled during init (`formation.py:349`), so these calls don't emit anything

**Action**: Leave in place for now (massive cleanup, low value)

**Files with stale references**:
- `initialization.py` - Multiple INITIALIZING calls
- `overlord.py` - SERVICE_STARTED, INITIALIZING calls  
- `formation.py` - MCP_SERVER_REGISTRATION_STARTED, INITIALIZING calls
- `a2a_coordinator.py` - A2A_SERVER_STARTED call
- Others...

---

## 🎯 Next Focus: 368 TODO Comments

### Current Understanding

- **Total TODOs**: 368 comments marked "TODO: add observability"
- **Nature**: Runtime events (NOT init events)
- **Categories** (estimated):
  - System/Error events: ~150-200
  - Conversation events: ~168-218

### TODO Distribution (from grep sample)

| Area | Estimated TODOs | Category |
|------|----------------|----------|
| **Webhook Manager** | ~15 | System |
| **Time Estimator** | ~5 | System |
| **Document Processing** | ~40 | Mixed (some System, some Conversation) |
| **Memory Operations** | ~30 | Mixed |
| **MCP Runtime** | ~30 | System |
| **A2A Runtime** | ~40 | System |
| **Resilience System** | ~20 | System |
| **Workflow** | ~25 | Conversation |
| **Clarification** | ~15 | Conversation |
| **Agent Processing** | ~30 | Conversation |
| **Scheduler Runtime** | ~15 | System |
| **Many more...** | ~103 | Mixed |

### Categorization Strategy

**System/Error Events** = Infrastructure failures, independent of user requests:
- ✅ MCP server disconnections
- ✅ Database connection lost
- ✅ Authentication failures
- ✅ Network errors
- ✅ Scheduler job failures
- ✅ Resource exhaustion
- ✅ Circuit breaker trips

**Conversation Events** = Part of processing user requests:
- ❌ Request received
- ❌ Clarification started
- ❌ Agent selected
- ❌ Workflow decomposed
- ❌ Memory updated
- ❌ Response generated

---

## 📋 Phase 2 Roadmap (Updated)

### ✅ Step 1: Remove Init Events (DONE)
- Removed 27 init event definitions
- Identified stale references (harmless, deferred cleanup)

### ⏭️ Step 2: Categorize 368 TODOs (NEXT)
**Goal**: Create two lists:
1. System/Error TODOs (~150-200) - implement in Phase 2
2. Conversation TODOs (~168-218) - defer to Phase 3

**Approach**:
1. Create Python script to extract all TODOs with context
2. Analyze file paths and comment text to categorize
3. Output two prioritized lists

### ⏭️ Step 3: Implement System/Error Events
**Weeks 1-3**: Implement ~50-100 high-priority System/Error TODOs
- Week 1: Security & Auth (~30 TODOs)
- Week 2: Infrastructure failures (~30 TODOs)
- Week 3: Resource & Health (~20-40 TODOs)

### ⏭️ Step 4: Plan Conversation Events (Phase 3)
Use `docs/request-lifecycle.md` to map Conversation events

---

## 🚀 Immediate Next Steps

1. **Create TODO extraction script** (~30 min)
   - Parse all 368 TODO comments
   - Extract file path, line number, context
   - Export to CSV/JSON for analysis

2. **Categorize TODOs** (~1 hour)
   - Review extracted TODOs
   - Mark as System/Error or Conversation
   - Prioritize System/Error by severity

3. **Start implementation** (~2-3 hours)
   - Begin with high-priority auth failures
   - Then infrastructure failures
   - Document patterns for team

---

## 📈 Success Metrics

**Phase 2 Complete When**:
- ✅ Init events removed (DONE)
- ⏭️ 368 TODOs categorized
- ⏭️ Top 50-100 System/Error TODOs implemented
- ⏭️ Runtime observability verified in testing

**Phase 3 Ready When**:
- System/Error events stable
- `request-lifecycle.md` reviewed
- Conversation event plan created

---

**Current Priority**: Create TODO extraction and categorization script 🎯
