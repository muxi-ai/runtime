# Phase 2: BLITZ Implementation Plan 🚀

**Goal**: Implement 205 System/Error observability TODOs TODAY  
**Strategy**: Batch by component, quick wins first, parallelize when possible

---

## 🎯 Implementation Batches (Priority Order)

### BATCH 1: A2A Authentication (12 HIGH priority) - 30 min
**Files**: `services/a2a/auth/inbound.py` (probably all in one file)  
**Events**: AUTHENTICATION_FAILED, AUTHORIZATION_FAILED, TOKEN_INVALID, CREDENTIAL_ERROR

**Pattern**:
```python
# Replace: #  A2A inbound auth error - TODO: add observability
# With:
observe(
    ErrorEvents.AUTHENTICATION_FAILED,
    level=EventLevel.ERROR,
    data={"auth_type": self.auth_mode, "client_id": client_id, "error": str(e)},
    description=f"A2A authentication failed for {client_id}"
)
```

**Quick Win**: All similar, can batch replace

---

### BATCH 2: MCP Failures (20 TODOs) - 45 min
**Files**: 5 MCP files  
**Events**: MCP_TOOL_CALL_FAILED, MCP_CONNECTION_LOST, MCP_SERVER_PROCESS_FAILED

**Sub-batches**:
- 2 HIGH priority (connection failures)
- 18 System/Error (disconnections, tool failures, timeouts)

**Pattern**: Similar to A2A, mostly error handling blocks

---

### BATCH 3: A2A Failures (11 TODOs) - 30 min
**Files**: `services/a2a/discovery.py`, communication files  
**Events**: A2A_DISCOVERY_FAILED, A2A_MESSAGE_FAILED, A2A_COMMUNICATION_ERROR

---

### BATCH 4: Resilience System (35 TODOs) - 1 hour
**Files**: 4 resilience files (circuit_breaker, fallback_manager, recovery_strategist, error_classifier)  
**Events**: CIRCUIT_BREAKER_OPENED, FALLBACK_ACTIVATED, RECOVERY_STRATEGY_APPLIED

**Approach**: File by file, these are well-structured

---

### BATCH 5: Workflow Errors (28 TODOs) - 1 hour
**Files**: 6 workflow files (decomposer, executor, analyzer, synthesis)  
**Events**: WORKFLOW_DECOMPOSITION_FAILED, WORKFLOW_EXECUTION_ERROR, TASK_ASSIGNMENT_FAILED

---

### BATCH 6: Overlord Orchestration (23 TODOs) - 45 min
**Files**: 2 overlord files  
**Events**: OVERLORD_ERROR, AGENT_ROUTING_FAILED, MCP_COORDINATOR_ERROR

---

### BATCH 7: Memory Operations (12 TODOs) - 30 min
**Files**: 4 memory files  
**Events**: MEMORY_OPERATION_FAILED, MEMORY_ERROR, STORAGE_ERROR

---

### BATCH 8: Webhook/Scheduler (10 TODOs) - 30 min
**Files**: `webhook_manager.py` (9), `scheduler/batch_processor.py` (1)  
**Events**: WEBHOOK_DELIVERY_FAILED, WEBHOOK_RETRY, SCHEDULER_JOB_FAILED

---

### BATCH 9: Document Processing (9 TODOs) - 30 min
**Files**: 5 document files  
**Events**: DOCUMENT_PROCESSING_FAILED, CONTENT_EXTRACTION_FAILED

---

### BATCH 10: Cleanup Unknown (45 TODOs) - 1 hour
**Files**: 5 miscellaneous files  
**Approach**: Review and categorize on-the-fly

---

## ⚡ Fast Implementation Strategy

### 1. Pattern-Based Replacement (60% of TODOs)

Most TODOs follow this pattern:
```python
# Before:
#  Error - TODO: add observability
_ = e  # Remove after implementing observability

# After:
observe(
    ErrorEvents.APPROPRIATE_EVENT,
    level=EventLevel.ERROR,
    data={"component": "...", "error": str(e)},
    description=f"..."
)
```

### 2. Batch Edit Tool Usage

Use MultiEdit for similar patterns in same file:
```python
# Find all: #.*TODO.*observability
# In context of: except.*Exception
# Replace with: observe(...) calls
```

### 3. Component-Specific Events

Create component-specific event patterns:
- **A2A**: Authentication, Discovery, Communication
- **MCP**: Connection, Tool Call, Process
- **Memory**: Operation, Storage, Extraction
- **Workflow**: Decomposition, Execution, Task
- **Resilience**: Circuit Breaker, Fallback, Recovery

---

## 📊 Time Estimates

| Batch | TODOs | Time | Running Total |
|-------|-------|------|---------------|
| 1. A2A Auth | 12 | 30m | 30m |
| 2. MCP Failures | 20 | 45m | 1h 15m |
| 3. A2A Failures | 11 | 30m | 1h 45m |
| 4. Resilience | 35 | 1h | 2h 45m |
| 5. Workflow | 28 | 1h | 3h 45m |
| 6. Overlord | 23 | 45m | 4h 30m |
| 7. Memory | 12 | 30m | 5h |
| 8. Webhook/Scheduler | 10 | 30m | 5h 30m |
| 9. Doc Processing | 9 | 30m | 6h |
| 10. Unknown | 45 | 1h | **7h total** |

**Realistic**: 7-8 hours with breaks  
**Optimistic**: 5-6 hours if patterns repeat  
**Conservative**: 8-10 hours with testing

---

## 🎯 Success Metrics

### Per Batch
- [ ] All TODOs in batch files have observability
- [ ] Events emit correctly (spot check)
- [ ] No syntax errors (quick test import)

### Overall
- [ ] 205 System/Error TODOs implemented
- [ ] Events follow consistent patterns
- [ ] Code compiles and imports successfully
- [ ] Sample test shows events emitting

---

## 🚀 LET'S GO!

**Start with BATCH 1**: A2A Authentication (highest impact, quick win)

**Command to start**:
```bash
grep -n "TODO.*observability" src/muxi/services/a2a/auth/inbound.py
```

**Ready?** 🔥
