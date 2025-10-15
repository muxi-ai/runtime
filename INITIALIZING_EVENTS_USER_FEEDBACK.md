# User Feedback on INITIALIZING Events

**Source**: User comments in observability_events_audit.csv  
**Date**: Current session

---

## Summary of User Decisions

| Action | Count | Files |
|--------|-------|-------|
| **REMOVE** | 17 | 8 files |
| **Convert to InitEventFormatter** | 4 | 3 files |
| **Replace with ServerEvents** | 5 | 2 files |
| **Decision needed** | 6 | 5 files |
| **Explain NO DESCRIPTION** | 2 | 2 files |

---

## 1. REMOVE (17 events) ✅ Clear Directive

**User comment: "remove"**

| File | Line | Description |
|------|------|-------------|
| `artifacts/extractor.py` | 41 | No tool results provided |
| `overlord.py` | 2738, 2751 | Collection registration (2x) |
| `overlord.py` | 4188 | Fallback chunking |
| `overlord.py` | 2786 | A2A ClientFactory initialized |
| `overlord.py` | 4148 | File extraction success |
| `long_term.py` | 207 | Lazy embedding model |
| `long_term.py` | 258 | pgvector extension created |
| `formation.py` | 1268 | All Formation services initialized |
| `initialization.py` | 339 | Buffer memory initialized |
| `initialization.py` | 456 | Persistent memory initialized |
| `initialization.py` | 604 | Found MCP servers |
| `initialization.py` | 708 | Background services initialized |
| `initialization.py` | 1077 | PostgreSQL backend (NO DESCRIPTION) |
| `initialization.py` | 1120 | SQLite backend (NO DESCRIPTION) |
| `run_formation.py` | 64 | Loading formation from |
| `run_formation.py` | 271 | Starting formation runner |

**Total: 17 removals across 8 files**

---

## 2. Convert to InitEventFormatter (4 events) ✅ Clear Directive

**User comment: "Convert to init print"**

These should become InitEventFormatter print statements, not observability events:

| File | Line | Current Description | Proposed Init Message |
|------|------|---------------------|----------------------|
| `initialization.py` | 97 | Observability initialized with file output | `[ INFO ] Observability logging to: {path}` |
| `initialization.py` | 277 | Working memory configured in {mode} mode | `[  OK  ] Working memory ({mode} mode)` |
| `llm.py` | 151 | OneLLM cache is disabled | `[ INFO ] OneLLM cache: disabled` |
| `server.py` | 185 | Auto-generated API keys - NOT recommended | `[ WARN ] API keys auto-generated (NOT for production)` |

**Total: 4 conversions across 3 files**

---

## 3. Replace with ServerEvents (5 events) ✅ Clear Directive

**User comment: "should be replaced with appropriate ServerEvents"**

These are runtime server lifecycle events, not initialization:

| File | Line | Current | New Event Type | Description |
|------|------|---------|----------------|-------------|
| `formation.py` | 3146 | INITIALIZING | ServerEvents.SERVER_RESTARTING | Replacing existing stopped server instance |
| `formation.py` | 3177 | INITIALIZING | ServerEvents.SERVER_STARTING | Starting Formation API server on {host}:{port} |
| `formation.py` | 3192 | INITIALIZING | ServerEvents.OVERLORD_STARTING | Auto-starting overlord for Formation API server |
| `server.py` | 130 | INITIALIZING | ServerEvents.SERVER_INITIALIZING | Initializing Formation server on {host}:{port} |
| `server.py` | 226 | INITIALIZING | ServerEvents.API_KEYS_LOADED | API keys loaded from formation configuration |

**Action**: Add these 5 new ServerEvents to observability.py enum

**Total: 5 conversions to ServerEvents across 2 files**

---

## 4. Decision Needed (6 events) ⚠️ User Says "Feels pointless"

**User comment: "Feels pointless. Either convert to init print or remove"**

User wants these evaluated - are they worth keeping at all?

| File | Line | Description | My Recommendation |
|------|------|-------------|-------------------|
| `initialization.py` | 765 | Clarification config initialized | **REMOVE** - Internal config, not user-visible |
| `initialization.py` | 553 | Document processing initialized | **Convert to Init** - `[  OK  ] Document processing ready` |
| `initialization.py` | 651 | Initializing artifact generation service | **REMOVE** - Internal service, covered by agent capabilities |
| `initialization.py` | 813 | Document processing configuration initialized | **REMOVE** - Redundant with line 553 above |
| `overlord.py` | 482 | Initialized encrypted credential resolver | **REMOVE** - Internal security component |
| `workflow_manager.py` | 51 | WorkflowManager initialized | **REMOVE** - Internal component, not user-visible |

**User: Should I remove all 6? Or convert document processing (553) to init print?**

**My vote: Remove 5, convert document processing (553) to init print only if it's an optional feature users explicitly enable.**

---

## 5. Questions from User ❓

### 5a. MCP Initialization Error (initialization.py:636)

**User comment: "aren't we 'failing fast' during init? Why do we need this?"**

**Code context:**
```python
try:
    # Initialize MCP service
    await initialize_mcp_service(formation)
except Exception as e:
    observability.observe(
        event_type=SystemEvents.INITIALIZING,
        level=EventLevel.ERROR,
        description="Failed to initialize MCP service: {str(e)}"
    )
    # NO re-raise - continues with formation loading!
```

**Answer**: We're **NOT failing fast here** - the exception is caught and logged, but **formation continues loading without MCP**. This is graceful degradation, not fail-fast.

**Options:**
1. **Keep as ErrorEvent** (ErrorEvents.MCP_INITIALIZATION_FAILED) - User needs to know MCP failed
2. **Remove if we want fail-fast** - Re-raise exception to prevent formation from starting without MCP
3. **Convert to InitEventFormatter warning** - `[ WARN ] MCP initialization failed - continuing without MCP servers`

**My recommendation**: Option 1 (keep as ErrorEvent) - graceful degradation is intentional, user should know MCP failed.

**User: Which option do you prefer?**

---

### 5b. NO DESCRIPTION Events - Need Explanation

**User comment: "explain"**

#### Event 1: initialization.py:234
```python
observability.observe(
    event_type=SystemEvents.INITIALIZING,
    level=EventLevel.INFO,
    data=log_data,
    description=description,  # ← Actually HAS description: "LLM configuration initialized with {len(capabilities)} capabilities"
)
```

**Explanation**: CSV shows "NO DESCRIPTION" but code has description. **This is a CSV extraction bug** - the description variable contains the actual message. Not actually missing.

**Real description**: "LLM configuration initialized with X capabilities"

**Action**: Fix CSV extraction script, then re-evaluate if this should be init print or removed.

---

#### Event 2: llm.py:173
```python
observability.observe(
    event_type=SystemEvents.INITIALIZING,
    level=EventLevel.INFO,
    data={
        "service": "onellm_cache",
        "enabled": True,
        **cache_params,
    },
    description=(
        f"OneLLM cache initialized with {cache_params['max_entries']} max entries, "
        f"{cache_params['p']} similarity threshold, {cache_params['ttl']}s TTL"
    ),
)
```

**Explanation**: CSV shows "NO DESCRIPTION" but code has detailed description. **CSV extraction bug again**.

**Real description**: "OneLLM cache initialized with 10000 max entries, 0.95 similarity threshold, 86400s TTL"

**Action**: Fix CSV extraction script, then re-evaluate if this should be init print or removed.

---

## Proposed Action Plan

### Phase 1: Simple Removals (17 events) - 5 minutes
Remove observability.observe() calls for the 17 "remove" events.

### Phase 2: Convert to InitEventFormatter (4 events) - 10 minutes
Replace observability.observe() with InitEventFormatter print statements.

### Phase 3: Add ServerEvents (5 new types) - 15 minutes
1. Add 5 new ServerEvents to observability.py
2. Convert 5 INITIALIZING events to use new ServerEvents

### Phase 4: Resolve "Feels pointless" (6 events) - Awaiting user decision
**User: Which of these 6 should I keep/convert/remove?**
- My recommendation: Remove 5, convert document processing (553) to init print

### Phase 5: Resolve Questions (2 events) - Awaiting user decision
1. **MCP error**: Keep as ErrorEvent, remove, or init print warning?
2. **NO DESCRIPTION bugs**: Fix CSV script, then re-evaluate

---

## Questions for User

1. **"Feels pointless" events (6)**: Remove all 6? Or keep document processing (553) as init print?

2. **MCP initialization error (636)**: 
   - Option A: Keep as ErrorEvent.MCP_INITIALIZATION_FAILED (graceful degradation)
   - Option B: Remove and fail fast (re-raise exception)
   - Option C: Convert to InitEventFormatter warning

3. **NO DESCRIPTION events (2)**: After I fix the CSV extraction bug, should these be init prints or removed?

---

**Ready to proceed once you answer these 3 questions!**
