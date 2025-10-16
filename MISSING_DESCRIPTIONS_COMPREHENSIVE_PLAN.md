# Missing Descriptions - Comprehensive Fix Plan

**Scope**: 595 events across 73 files  
**Approach**: Systematic, priority-based implementation  
**Estimated Effort**: 20-30 hours total

---

## Phase 1: High-Priority ErrorEvents (Est: 4-6 hours)

Fix all ErrorEvents first - these are critical for debugging production issues.

### Batch 1.1: Core System Errors (~50 events)
- **overlord.py**: ~30 ErrorEvents
- **agent.py**: ~15 ErrorEvents  
- **formation.py**: ~5 ErrorEvents

### Batch 1.2: Service Errors (~40 events)
- **scheduler/manager.py**: ~10 ErrorEvents
- **mcp/service.py**: ~8 ErrorEvents
- **llm.py**: ~5 ErrorEvents
- **a2a/**: Various files ~15 ErrorEvents

### Batch 1.3: Workflow & Memory Errors (~20 events)
- **workflow/executor.py**: ~5 ErrorEvents
- **memory/**: Various files ~10 ErrorEvents
- **documents/**: Various files ~5 ErrorEvents

**Subtotal Phase 1**: ~110 ErrorEvents

---

## Phase 2: High-Traffic SystemEvents (Est: 6-8 hours)

Fix SystemEvents in hot paths that appear frequently in logs.

### Batch 2.1: Overlord & Orchestration (~60 events)
- **overlord.py**: ~50 SystemEvents (chat flow, agent routing, etc.)
- **chat_orchestrator.py**: ~9 SystemEvents
- **agent_router.py**: ~2 SystemEvents

### Batch 2.2: Agent Operations (~40 events)
- **agent.py**: ~34 SystemEvents (task execution, tool calls, etc.)
- **formation.py**: ~6 SystemEvents

### Batch 2.3: MCP & A2A (~50 events)
- **mcp/service.py**: ~4 SystemEvents
- **a2a/discovery.py**: ~24 SystemEvents
- **a2a/card_generator.py**: ~21 SystemEvents
- **mcp/reconnection.py**: ~4 SystemEvents

**Subtotal Phase 2**: ~150 SystemEvents

---

## Phase 3: Initialization & Background (~8-10 hours)

Fix events in initialization, background tasks, and scheduled operations.

### Batch 3.1: Initialization (~30 events)
- **initialization.py**: 20 events
- **formation.py**: ~10 events (startup-related)

### Batch 3.2: Scheduler (~60 events)
- **scheduler/manager.py**: 29 events
- **scheduler/parser.py**: 12 events
- **scheduler/service.py**: 10 events
- **scheduler/rewriter.py**: 7 events
- **scheduler/batch_processor.py**: 1 event
- **scheduler/cache.py**: 1 event

### Batch 3.3: Background Tasks (~20 events)
- **run_formation.py**: 11 events
- **time_estimator.py**: 4 events
- **webhook_manager.py**: 1 event
- **background/**: Various ~4 events

**Subtotal Phase 3**: ~110 events

---

## Phase 4: Workflow & Documents (~6-8 hours)

Fix workflow decomposition, document processing, and SOP execution.

### Batch 4.1: Workflow (~30 events)
- **workflow/decomposer.py**: 14 events
- **workflow/executor.py**: ~6 events
- **workflow/sops.py**: 12 events
- **workflow/analyzer.py**: 3 events
- **workflow/synthesis.py**: 1 event
- **workflow_manager.py**: 1 event

### Batch 4.2: Document Processing (~25 events)
- **multimodal/fusion_engine.py**: 21 events
- **documents/**: Various ~15 events
  - cross_reference_manager.py: 4
  - workflow_integrator.py: 4
  - context_preserver.py: 4
  - experience/summarizer.py: 4
  - storage/: 5 events

**Subtotal Phase 4**: ~55 events

---

## Phase 5: Memory & Storage (~4-6 hours)

Fix memory management and data persistence events.

### Batch 5.1: Memory Systems (~30 events)
- **memory/working.py**: 10 events
- **memory/long_term.py**: 6 events
- **memory/extractor.py**: 5 events
- **memory/buffer_manager.py**: 4 events
- **memory/persistent_manager.py**: 8 events
- **memory/sqlite.py**: 1 event
- **memory/extraction_coordinator.py**: 1 event

### Batch 5.2: Artifacts (~15 events)
- **artifacts/extractor.py**: 8 events
- **artifacts/processor.py**: 4 events

**Subtotal Phase 5**: ~45 events

---

## Phase 6: Server & API (~3-4 hours)

Fix server routes, middleware, and admin endpoints.

### Batch 6.1: Server Core (~15 events)
- **server/server.py**: 9 events
- **server/middleware.py**: 2 events
- **server/routes/health.py**: 1 event

### Batch 6.2: Admin Routes (~10 events)
- **routes/admin/mcp.py**: 4 events
- **routes/admin/agents.py**: 2 events

### Batch 6.3: Client Routes (~5 events)
- **routes/client/triggers.py**: 3 events
- **routes/client/chat.py**: 2 events

**Subtotal Phase 6**: ~30 events

---

## Phase 7: Utilities & Resilience (~3-4 hours)

Fix utility functions, credentials, and resilience patterns.

### Batch 7.1: User & Auth (~15 events)
- **user_resolution.py**: 7 events
- **credentials/resolver.py**: 2 events
- **credentials/handler.py**: 1 event
- **a2a/cache_manager.py**: 6 events (auth cache)

### Batch 7.2: Resilience (~10 events)
- **resilience/fallback_manager.py**: 2 events
- **resilience/error_classifier.py**: 2 events
- **resilience/circuit_breaker.py**: 2 events
- **resilience/recovery_strategist.py**: 1 event
- **retry_manager.py**: 2 events

### Batch 7.3: Other Utilities (~10 events)
- **response_converter.py**: 3 events
- **db.py**: 5 events
- **a2a/client.py**: 6 events (non-auth)
- **a2a/server.py**: 5 events
- **intent/service.py**: 2 events
- **mcp/**: Various ~10 events

**Subtotal Phase 7**: ~35 events

---

## Implementation Strategy

### Approach for Each Event

1. **Read surrounding code context** (10-15 lines before/after)
2. **Identify the operation** (what is being done?)
3. **Determine the outcome** (success/failure/warning?)
4. **Add concise description** following patterns:
   - ErrorEvents: "Failed to X: {reason}" or "X error: {context}"
   - SystemEvents: "X completed/started/finished" or "X operation: {details}"
   - Include key context variables in description (IDs, names, counts)

### Automation Helper

Create a script to:
1. Extract event context (file, line, event type, data fields)
2. Suggest description based on patterns
3. Human review and adjust
4. Apply changes in batches

### Quality Checks

After each phase:
1. Verify all descriptions added
2. Check for consistency in language/style
3. Ensure descriptions are actionable (help with debugging)
4. Update CSV audit file

---

## Timeline (Conservative Estimate)

| Phase | Scope | Events | Est. Hours |
|-------|-------|--------|------------|
| Phase 1 | ErrorEvents | ~110 | 4-6 hours |
| Phase 2 | High-Traffic SystemEvents | ~150 | 6-8 hours |
| Phase 3 | Init & Background | ~110 | 8-10 hours |
| Phase 4 | Workflow & Docs | ~55 | 6-8 hours |
| Phase 5 | Memory & Storage | ~45 | 4-6 hours |
| Phase 6 | Server & API | ~30 | 3-4 hours |
| Phase 7 | Utils & Resilience | ~35 | 3-4 hours |
| **TOTAL** | **All Files** | **595** | **34-46 hours** |

With automation and batching: **~20-30 hours realistic**

---

## Proposed Execution Plan

### Day 1: Setup + Phase 1
- Create automation helper script
- Complete Phase 1 (ErrorEvents)
- **Output**: ~110 descriptions added

### Day 2: Phase 2
- High-traffic SystemEvents
- **Output**: ~150 descriptions added

### Day 3: Phase 3
- Init & Background
- **Output**: ~110 descriptions added

### Day 4: Phases 4-5
- Workflow, Docs, Memory
- **Output**: ~100 descriptions added

### Day 5: Phases 6-7 + Verification
- Server, Utils, Resilience
- Verify all 595 events
- Update CSV
- **Output**: ~65 descriptions + verification complete

---

## Success Criteria

- ✅ All 595 events have meaningful `description` parameter
- ✅ Descriptions follow consistent patterns
- ✅ Descriptions include actionable context
- ✅ CSV audit updated and verified
- ✅ No "NO DESCRIPTION" entries remaining

---

## Next Step

Start with **Phase 1, Batch 1.1** (overlord.py ErrorEvents) - highest priority for production debugging.

Create automation script first to speed up the process.
