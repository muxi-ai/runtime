# Request Lifecycle Events - Comprehensive Audit

## Executive Summary

**Goal**: Enable timeline reconstruction, analytics on request patterns, performance tracking, and type classification.

**Findings**: Out of 49+ documented events:
- **3 CRITICAL**: Using SystemEvents instead of ConversationEvents
- **12 HIGH**: Reusing generic events (REQUEST_VALIDATED, CLARIFICATION_REQUEST_SENT, etc.)
- **8 MEDIUM**: Wrong event type or missing event
- **6 LOW**: Description/metadata improvements needed

**Total Issues**: 29 events need fixes (59% of lifecycle events)

---

## CRITICAL Issues (Must Fix)

### C1. Forced Sync Mode (Phase 1.8)
**Current**: `SystemEvents.SYSTEM_ACTION`  
**Fix**: Create `ConversationEvents.REQUEST_MODE_CHANGED`  
**Location**: chat_orchestrator.py:384  
**Data Needed**: `requested_mode`, `forced_mode`, `reason`, `timestamp`  
**Why**: Timeline needs to show when/why requests were forced sync

### C2. Credential Storage (Phase 2.2)
**Current**: `SystemEvents.CREDENTIAL_UPDATE`  
**Fix**: Create `ConversationEvents.CREDENTIAL_PROVIDED`  
**Location**: overlord.py:9335  
**Data Needed**: `service`, `credential_type`, `via_clarification=true`, `timestamp`  
**Why**: Timeline needs to track credential collection as part of conversation flow

### C3. Clarification Bypassed (Phase 3.6)
**Current**: `SystemEvents.SERVICE_STARTED` (wrong reuse)  
**Fix**: Use existing `ConversationEvents.CLARIFICATION_SKIPPED`  
**Location**: overlord.py:5996  
**Data Needed**: `reason`, `is_workflow_task`, `timestamp`  
**Why**: Event already exists! Just wrong enum being used

---

## HIGH Priority (Generic Event Reuse)

### H1. Async/Streaming Conflict (Phase 1.2)
**Current**: `ConversationEvents.REQUEST_VALIDATED` (generic reuse)  
**Fix**: Create `ConversationEvents.REQUEST_MODE_RESOLVED`  
**Location**: overlord.py:4749  
**Data Needed**: `requested_async`, `requested_stream`, `resolution`, `final_mode`  
**Why**: Important for understanding request processing modes

### H2. Request ID Reuse (Phase 1.3)
**Current**: `ConversationEvents.REQUEST_VALIDATED` (generic reuse)  
**Fix**: Create `ConversationEvents.REQUEST_ID_REUSED`  
**Location**: chat_orchestrator.py:222  
**Data Needed**: `original_request_id`, `clarification_turn`, `session_id`  
**Why**: Critical for multi-turn clarification tracking

### H3. User Info Extraction Task (Phase 1.6)
**Current**: `ConversationEvents.REQUEST_VALIDATED` (generic reuse)  
**Fix**: Use existing `ConversationEvents.MEMORY_AUTO_EXTRACTED` or create `USER_INFO_EXTRACTION_STARTED`  
**Location**: chat_orchestrator.py:364  
**Data Needed**: `extraction_enabled`, `user_id`, `background_task=true`  
**Why**: Track when/why extraction happens

### H4. Pending Clarification Check (Phase 2.1)
**Current**: `ConversationEvents.CLARIFICATION_REQUEST_SENT` (wrong context)  
**Fix**: Remove event OR use `ConversationEvents.CLARIFICATION_RESPONSE_RECEIVED`  
**Location**: overlord.py:6085  
**Reason**: This is checking state, not sending a request. Debug noise, not timeline value.

### H5. Workflow Approval Processing (Phase 3.3)
**Current**: `ConversationEvents.CLARIFICATION_REQUEST_SENT` (wrong context)  
**Fix**: Create `ConversationEvents.WORKFLOW_APPROVAL_RECEIVED`  
**Location**: overlord.py:5754  
**Data Needed**: `workflow_id`, `approval_status`, `user_response`  
**Why**: Workflow approvals are key decision points in timeline

### H6. Workflow Lookup Debug (Phase 3.4)
**Current**: `ConversationEvents.CLARIFICATION_REQUEST_SENT` (wrong context)  
**Fix**: Remove this debug event  
**Location**: overlord.py:5767  
**Reason**: Pure debug logging, no timeline value

### H7. Workflow Analysis Conditions (Phase 4.1)
**Current**: `ConversationEvents.CLARIFICATION_REQUEST_SENT` (wrong context)  
**Fix**: Remove OR use `ConversationEvents.WORKFLOW_ANALYSIS_STARTED` (if it exists, otherwise create)  
**Location**: overlord.py:6241  
**Data Needed**: `auto_decomposition_enabled`, `agent_specified`, `complexity_threshold`  
**Why**: Shows decision point for workflow routing

### H8. Request Analyzer Result (Phase 4.4)
**Current**: `ServerEvents.REQUEST_RECEIVED` (completely wrong enum!)  
**Fix**: Create `ConversationEvents.REQUEST_ANALYZED`  
**Location**: overlord.py:6347  
**Data Needed**: `complexity_score`, `requires_decomposition`, `is_scheduling`, `topics`, `analysis_duration_ms`  
**Why**: Critical for understanding routing decisions

### H9. Explicit SOP Request (Phase 4.5)
**Current**: `ConversationEvents.REQUEST_VALIDATED` (generic reuse)  
**Fix**: Use existing `ConversationEvents.SOP_MATCHED`  
**Location**: overlord.py:6359  
**Data Needed**: `sop_id`, `sop_name`, `explicit_request=true`  
**Why**: SOP invocations are important routing events

### H10. Scheduler Check (Phase 5.1)
**Current**: `ServerEvents.REQUEST_RECEIVED` (completely wrong enum!)  
**Fix**: Remove OR create `ConversationEvents.SCHEDULER_ROUTING_EVALUATED`  
**Location**: overlord.py:6500  
**Reason**: Debug noise, but if kept needs proper event

### H11. Scheduler Routing (Phase 5.2)
**Current**: `ServerEvents.REQUEST_RECEIVED` (completely wrong enum!)  
**Fix**: Create `ConversationEvents.SCHEDULER_JOB_REQUESTED`  
**Location**: overlord.py:6519  
**Data Needed**: `user_id`, `schedule_expression`, `job_type`  
**Why**: Track when jobs are scheduled vs immediately processed

### H12. Agent Selection Debug (Phase 6.1)
**Current**: `ConversationEvents.CLARIFICATION_REQUEST_SENT` (wrong context)  
**Fix**: Remove this debug event  
**Location**: overlord.py:6571  
**Reason**: Pure debug logging, no timeline value

---

## MEDIUM Priority (Missing Events or Wrong Events)

### M1. SOP Not Found (Phase 4.6)
**Current**: `ConversationEvents.SOP_MATCHED` (wrong - should be error/warning)  
**Fix**: Create `ConversationEvents.SOP_NOT_FOUND` or use ErrorEvents  
**Location**: overlord.py:6384  
**Data Needed**: `requested_sop_id`, `available_sops`, `sop_system_enabled`  
**Why**: Track SOP configuration issues

### M2. Non-Actionable Fast Path (Phase 4.8)
**Current**: `ConversationEvents.REQUEST_PROCESSING` (too generic)  
**Fix**: Create `ConversationEvents.REQUEST_NON_ACTIONABLE`  
**Location**: overlord.py:6201  
**Data Needed**: `message_type`, `fast_path=true`, `processing_time_ms`  
**Why**: Track simple vs complex request patterns

### M3. Message Context Enhancement (MISSING)
**Current**: No event emitted  
**Fix**: Create `ConversationEvents.REQUEST_CONTEXT_LOADED`  
**Location**: After `_enhance_message_with_context` completes  
**Data Needed**: `buffer_messages_count`, `long_term_memories_count`, `context_loading_ms`  
**Why**: Track memory system performance

### M4. Credential Detection Started (MISSING)
**Current**: No event emitted  
**Fix**: Create `ConversationEvents.CREDENTIAL_DETECTION_STARTED`  
**Location**: Before credential detection analysis  
**Data Needed**: `user_id`, `message_preview`, `has_existing_credentials`  
**Why**: Track credential detection flow initiation

### M5. Credential Selection (MISSING)
**Current**: Only has CREDENTIAL_UPDATE event  
**Fix**: Create `ConversationEvents.CREDENTIAL_SELECTED`  
**Location**: When user selects between multiple credentials  
**Data Needed**: `service`, `available_credentials_count`, `selected_credential_id`  
**Why**: Track credential selection in ambiguous cases

### M6. Async Request Queued (MISSING)
**Current**: Has ASYNC_PROCESSING_STARTED but not queuing  
**Fix**: Create `ConversationEvents.REQUEST_QUEUED_ASYNC`  
**Location**: In `_execute_async_request` before background task  
**Data Needed**: `request_id`, `webhook_url`, `estimated_duration_ms`  
**Why**: Distinguish between queueing and actual processing start

### M7. Webhook Delivery (MISSING)
**Current**: Has WEBHOOK_SENT/FAILED but not started  
**Fix**: Ensure `WEBHOOK_DELIVERY_STARTED` is emitted  
**Location**: Before webhook delivery attempt  
**Data Needed**: `webhook_url`, `attempt_number`, `payload_size_bytes`  
**Why**: Track webhook delivery performance

### M8. SOP Execution Started (MISSING)
**Current**: Has SOP_MATCHED but not execution start  
**Fix**: Ensure `ConversationEvents.SOP_EXECUTED` is emitted at start  
**Location**: When SOP workflow generation begins  
**Data Needed**: `sop_id`, `sop_name`, `matched_score`, `user_message`  
**Why**: Separate matching from execution

---

## LOW Priority (Metadata/Description Improvements)

### L1. Basic Request Validation (Phase 1.4)
**Current**: Generic metadata  
**Improve**: Add `validation_checks_passed`, `validation_duration_ms`, `file_processing_required`  
**Why**: Better understanding of validation performance

### L2. Security Violation (Phases 4.2, 6.3)
**Current**: Good event, needs consistent data  
**Improve**: Ensure all security events include `threat_level`, `blocked=true`, `detection_confidence`  
**Why**: Security analytics and threat assessment

### L3. Agent Message Processing (Phase 6.5)
**Current**: Good event, could add performance data  
**Improve**: Add `has_tools`, `tool_count`, `model_used`  
**Why**: Track agent capabilities usage

### L4. MCP Tool Call (Phase 6.8)
**Current**: Has completion, missing start  
**Improve**: Add `MCP_TOOL_CALL_STARTED` event  
**Why**: Track tool execution duration accurately

### L5. Workflow Task Events (Phases 7.7, 7.8)
**Current**: Good events, could standardize metadata  
**Improve**: Ensure consistent `task_complexity`, `agent_affinity_score`, `dependencies_completed`  
**Why**: Better workflow performance analytics

### L6. Memory Events (Phase 8)
**Current**: Good coverage, could add performance metrics  
**Improve**: Add `vector_search_duration_ms`, `similarity_threshold`, `results_quality_score`  
**Why**: Memory system performance tracking

---

## Proposed New Event Types

These events should be added to `ConversationEvents` enum:

```python
# Request Lifecycle
REQUEST_MODE_CHANGED = "request.mode.changed"
REQUEST_MODE_RESOLVED = "request.mode.resolved"  
REQUEST_ID_REUSED = "request.id.reused"
REQUEST_CONTEXT_LOADED = "request.context.loaded"
REQUEST_ANALYZED = "request.analyzed"
REQUEST_NON_ACTIONABLE = "request.non_actionable"
REQUEST_QUEUED_ASYNC = "request.queued.async"

# Credential Flow
CREDENTIAL_DETECTION_STARTED = "credential.detection.started"
CREDENTIAL_PROVIDED = "credential.provided"
CREDENTIAL_SELECTED = "credential.selected"

# Workflow
WORKFLOW_ANALYSIS_STARTED = "workflow.analysis.started"
WORKFLOW_APPROVAL_RECEIVED = "workflow.approval.received"

# Scheduler
SCHEDULER_ROUTING_EVALUATED = "scheduler.routing.evaluated"
SCHEDULER_JOB_REQUESTED = "scheduler.job.requested"

# SOP
SOP_NOT_FOUND = "sop.not_found"
SOP_EXECUTION_STARTED = "sop.execution.started"

# User Info
USER_INFO_EXTRACTION_STARTED = "user.info.extraction.started"
USER_IDENTITY_RESOLVED = "user.identity.resolved"

# Tools
MCP_TOOL_CALL_STARTED = "mcp.tool.call.started"

# Webhook
WEBHOOK_DELIVERY_STARTED = "webhook.delivery.started"
```

---

## Event Metadata Standards

For timeline reconstruction and analytics, every event should include:

### Core Metadata (Always Required)
- `request_id`: Links event to request timeline
- `session_id`: Links event to conversation
- `user_id`: Links event to user
- `timestamp`: Precise event timing (auto-added by observability system)

### Performance Metadata (When Applicable)
- `duration_ms`: How long operation took
- `start_timestamp`: When operation started (for async operations)
- `end_timestamp`: When operation ended

### Context Metadata (When Applicable)
- `phase`: Which lifecycle phase (entry, routing, execution, delivery)
- `path`: Which processing path (fast, workflow, direct_agent, scheduler)
- `complexity_score`: Request complexity (0.0-10.0)

### Decision Metadata (When Applicable)
- `reason`: Why this path was chosen
- `alternatives_considered`: What other options were available
- `confidence_score`: How confident the system is (0.0-1.0)

### Resource Metadata (When Applicable)
- `agent_id`: Which agent processed this
- `model_used`: Which LLM model
- `tools_used`: List of tools invoked
- `tokens_used`: Token consumption

---

## Implementation Strategy

### Phase 1: Quick Wins (1-2 hours)
1. Fix C3 (CLARIFICATION_SKIPPED - just change enum)
2. Fix H4, H6, H12 (Remove debug noise events)
3. Fix H8, H10, H11 (Wrong ServerEvents usage)

### Phase 2: Event Refactoring (3-4 hours)
1. Add new event types to ConversationEvents enum
2. Fix all CRITICAL events (C1, C2)
3. Fix all HIGH priority generic reuse events (H1-H3, H5, H7, H9)

### Phase 3: Missing Events (2-3 hours)
1. Add MEDIUM priority missing events (M3-M8)
2. Fix M1, M2 (wrong events)

### Phase 4: Metadata Enhancement (1-2 hours)
1. Add standard metadata to all events
2. Add performance tracking metadata
3. Update documentation

### Phase 5: Testing & Verification (2 hours)
1. Run e2e tests to verify events emit correctly
2. Check timeline reconstruction works
3. Verify no regressions

**Total Estimated Time**: 9-13 hours

---

## Questions for Decision

1. **Remove vs Fix**: Should we remove pure debug events (H4, H6, H12) or keep them but fix classification?
   - Recommendation: **Remove** - they add noise without timeline value

2. **Event Granularity**: Should we track every state check or only meaningful transitions?
   - Recommendation: **Only meaningful transitions** - focus on events that change request state

3. **Performance Events**: Should we add `_STARTED` events for all operations to track duration?
   - Recommendation: **Yes for key operations** - context loading, analysis, tool calls, webhooks

4. **Backwards Compatibility**: Should we keep old event names and add new ones, or rename?
   - Recommendation: **Add new events** - don't break existing consumers

5. **Testing Coverage**: Should we add e2e tests specifically for event emission?
   - Recommendation: **Yes** - add observability e2e test that verifies complete event timeline

---

## Success Criteria

After implementation, we should be able to:

1. ✅ Reconstruct complete request timeline from events alone
2. ✅ Identify request type (simple, workflow, scheduler, SOP) from events
3. ✅ Measure performance at each phase (context loading, routing, execution, delivery)
4. ✅ Track resource usage (agents, tools, models, tokens)
5. ✅ Analyze request patterns (fast-path %, workflow %, SOP usage, credential needs)
6. ✅ Debug issues by following event sequence
7. ✅ No SystemEvents in conversation flow (except true infrastructure events)
8. ✅ No generic event reuse (REQUEST_VALIDATED used only for actual validation)

---

## Next Steps

1. Review this audit with user
2. Get decisions on open questions
3. Proceed with Phase 1 implementation
4. Iterate through remaining phases
