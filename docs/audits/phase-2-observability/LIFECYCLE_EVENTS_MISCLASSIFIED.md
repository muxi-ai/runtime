# Lifecycle Events Misclassified as SystemEvents

## Summary

Found **3 instances** where request lifecycle events are being emitted as `SystemEvents` instead of `ConversationEvents`. These events are part of the request processing flow, not system infrastructure operations.

## Findings

### 1. Async Mode Override (chat_orchestrator.py:384)

**Current Classification:** `SystemEvents.SYSTEM_ACTION`

**Location:** `src/muxi/formation/overlord/chat_orchestrator.py:384`

**Context:**
```python
# FAIL-SAFE: Force sync mode if no webhook URL is available
if use_async is not False and webhook_url is None:
    observability.observe(
        event_type=observability.SystemEvents.SYSTEM_ACTION,  # ❌ WRONG
        level=observability.EventLevel.WARNING,
        data={
            "forced_sync": True,
            "reason": "no_webhook_url",
            "use_async_requested": use_async,
        },
        description="Forcing sync mode: No webhook URL configured or provided",
    )
```

**Issue:** This is a request processing decision, not a system infrastructure event. It's determining how to process a specific user request.

**Recommendation:** Should be a ConversationEvent. Possible options:
- Use existing `ASYNC_PROCESSING_FAILED` (closest match)
- Create new `ASYNC_MODE_FORCED_SYNC` event
- Use `REQUEST_PROCESSING` with explicit data indicating mode override

---

### 2. Credential Storage After Clarification (overlord.py:9335)

**Current Classification:** `SystemEvents.CREDENTIAL_UPDATE`

**Location:** `src/muxi/formation/overlord/overlord.py:9335`

**Context:**
```python
# Clean up pending clarification
self._delete_pending_clarification(session_id)

observability.observe(
    event_type=observability.SystemEvents.CREDENTIAL_UPDATE,  # ❌ WRONG
    level=observability.EventLevel.INFO,
    data={
        "service": service,
        "user_id": user_id,
        "credential_type": (
            list(credential_data.keys())[0]
            if credential_data
            else "unknown"
        ),
    },
    description=f"Successfully stored {service} credentials for user",
)
```

**Issue:** This occurs during clarification response processing - part of the conversation flow. User provided credentials via clarification, and we're storing them. This is a conversation lifecycle event, not system configuration.

**Recommendation:** Should be a ConversationEvent. Options:
- Use existing `CLARIFICATION_COMPLETED` (since it's the result of clarification)
- Create new `CREDENTIAL_PROVIDED` or `CREDENTIAL_STORED` ConversationEvent
- Keep `CREDENTIAL_UPDATE` but move it to ConversationEvents enum

---

### 3. Clarification Bypass Decision (overlord.py:5996)

**Current Classification:** `SystemEvents.SERVICE_STARTED`

**Location:** `src/muxi/formation/overlord/overlord.py:5996`

**Context:**
```python
# Log clarification bypass decision
if skip_clarification:
    observability.observe(
        event_type=observability.SystemEvents.SERVICE_STARTED,  # ❌ WRONG (reused)
        level=observability.EventLevel.DEBUG,
        data={
            "clarification_bypassed": True,
            "is_workflow_task": message and message.startswith("## Task:"),
            "reason": (
                "workflow_task"
                if message and message.startswith("## Task:")
                else "analyzer_clear"
            ),
        },
        description="Clarification bypassed",
    )
```

**Issue:** This is misusing a generic system event (`SERVICE_STARTED`) to log a request processing decision. The clarification bypass is part of the conversation lifecycle analysis.

**Recommendation:** Use existing `CLARIFICATION_SKIPPED` ConversationEvent (already exists!)

---

## Impact Assessment

### Current State
- **3 lifecycle events** incorrectly routed to stdout (SystemEvents)
- **Observability data loss**: These events aren't tracked with proper request/session context
- **Confusing event semantics**: `SERVICE_STARTED` is being reused for unrelated purposes

### After Fix
- All conversation lifecycle events will use ConversationEvents
- Better event filtering and routing
- Clearer event semantics

---

## Recommended Actions

### Quick Wins (No New Events Needed)

1. **Fix #3** - Change `SystemEvents.SERVICE_STARTED` → `ConversationEvents.CLARIFICATION_SKIPPED`
   - Event already exists
   - Perfect semantic match
   - **5-minute fix**

### Requires Decision

2. **Fix #1** - Async mode override
   - **Option A**: Use `ConversationEvents.ASYNC_PROCESSING_FAILED` (closest match)
   - **Option B**: Create new `ConversationEvents.ASYNC_MODE_FORCED_SYNC`
   - **Option C**: Use `REQUEST_PROCESSING` with data fields

3. **Fix #2** - Credential storage
   - **Option A**: Use existing `ConversationEvents.CLARIFICATION_COMPLETED`
   - **Option B**: Move `CREDENTIAL_UPDATE` from SystemEvents → ConversationEvents
   - **Option C**: Create new `ConversationEvents.CREDENTIAL_PROVIDED`

---

## Additional Context

### Not Issues (False Positives)

These were checked but are correctly classified:

- **SERVICE_USE / CREDENTIAL_REQUEST**: Not actual events - these are detection type strings used in credential handler logic
- **SERVICE_STARTED in overlord.py**: Multiple uses for actual service initialization (MCP, A2A, etc.) - correctly SystemEvents
- **MCP_* events**: Correctly SystemEvents - these are infrastructure/service lifecycle

### Related Documentation

- Request lifecycle: `docs/request-lifecycle-updated.md`
- Credential detection flow: Section 3.4 (lines 456-600)
- Clarification system: Section 3.3 (lines 300-455)

---

## Testing Considerations

After fixing these classifications:
1. Verify events appear in correct observability stream
2. Check event data structure is preserved
3. Confirm no breaking changes to event consumers
4. Run e2e test 1 (basic conversation) to verify events still emit

---

## Questions for User

1. **Fix #3 (CLARIFICATION_SKIPPED)**: Should we proceed with this obvious fix?
2. **Fix #1 (Async override)**: Which approach do you prefer?
3. **Fix #2 (Credential storage)**: Should we move `CREDENTIAL_UPDATE` to ConversationEvents or create a new event?
4. **Scope**: Should we do a broader audit of all SystemEvents usage in overlord/ and chat_orchestrator/?
