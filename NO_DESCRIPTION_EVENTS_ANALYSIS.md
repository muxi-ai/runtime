# NO DESCRIPTION Events Analysis

**Total**: 45 events with "NO DESCRIPTION"

---

## Categorization

### ✅ Already Fixed (8 events - Skip)

**INITIALIZING events (4) - Already removed/converted**:
- initialization.py:234 - Marked "done"
- initialization.py:1077 - Marked "done"  
- initialization.py:1120 - Marked "done"
- llm.py:173 - Marked "done"

**Recently fixed in commit 5f7411db (4)**:
- handler.py:547 - MCP_OVERLORD_REQUEST_CANCELLED (now DEBUG, still needs description)
- handler.py:1038 - MCP_SERVER_OPERATIONS_CANCELLED (now DEBUG, still needs description)
- user_resolution.py:132 - Now USER_RESOLVED (still needs description)
- user_resolution.py:163 - Now USER_CREATED (still needs description)
- user_resolution.py:353 - Now USER_IDENTIFIERS_ASSOCIATED (still needs description)

**Subtotal**: 8 events (but 5 still need descriptions after fixes)

---

### 🔧 Need Event Type Changes First (17 events)

**RETRY_ATTEMPTED Misnomers (9 events)**:
- cache_manager.py:70, 165, 207, 264, 324, 365 (6 events)
- response_converter.py:72, 181, 345 (3 events)
- *Fix*: Replace with specific error types (not retries!)

**INTERNAL_ERROR Too Generic (5 events)**:
- overlord.py:1665 (ERROR)
- overlord.py:1231 (WARNING)
- llm.py:648 (ERROR)
- llm.py:674 (WARNING)
- llm.py:1268 (ERROR)
- *Fix*: Replace with specific ErrorEvent types

**Anti-Pattern (1 event)**:
- sops.py:818 - ErrorEvents.WARNING (using level as event type!)
- *Fix*: Create specific ErrorEvent

**Too Generic (2 events)**:
- agent.py:1191 - VALIDATION_ERROR
- extractor.py:513, 529 - OPERATION_COMPLETED (2 events)
- user_resolution.py:81, 106 - OPERATION_COMPLETED (2 events)
- *Fix*: Consider more specific event types

**Subtotal**: 17 events (need event type changes, then add descriptions)

---

### 📝 Need Descriptions Only (20 events)

**Priority 1: ErrorEvents (5 events)**:

1. **overlord.py:1178** - CONFIGURATION_ERROR (ERROR)
2. **executor.py:99** - CONNECTION_TIMEOUT (WARNING)
3. **executor.py:1541** - CONNECTION_TIMEOUT (WARNING)
4. **user_resolution.py:94** - VALIDATION_FAILED (WARNING)
5. **user_resolution.py:304** - VALIDATION_FAILED (WARNING)

**Priority 2: SystemEvents - Extensions (5 events)**:

6. **base.py:103** - EXTENSION_LOADED (ERROR)
7. **base.py:140** - EXTENSION_LOADED (ERROR)
8. **base.py:209** - EXTENSION_LISTED (DEBUG)
9. **base.py:256** - EXTENSION_LOADED (ERROR)
10. **base.py:276** - EXTENSION_LOADED (ERROR)

**Priority 3: SystemEvents - MCP (3 events)**:

11. **service.py:890** - MCP_TOOL_DISCOVERY_COMPLETED (WARNING)
12. **service.py:1090** - MCP_SERVER_DISCONNECTED (ERROR)
13. **handler.py:922** - MCP_SERVER_MAPPING_FAILED (WARNING)

**Priority 4: SystemEvents - A2A (2 events)**:

14. **inbound.py:586** - A2A_AUTH_VALIDATION_FAILED (ERROR)
15. **overlord.py:1116** - A2A_REGISTRY_CONNECTED (INFO)

**Priority 5: SystemEvents - Other (5 events)**:

16. **overlord.py:860** - SERVICE_STARTED (DEBUG)
17. **handler.py:547** - MCP_OVERLORD_REQUEST_CANCELLED (DEBUG) - *Recently changed*
18. **handler.py:1038** - MCP_SERVER_OPERATIONS_CANCELLED (DEBUG) - *Recently changed*
19. **user_resolution.py:132** - USER_RESOLVED (DEBUG) - *Recently changed*
20. **user_resolution.py:163** - USER_CREATED (DEBUG) - *Recently changed*
21. **user_resolution.py:353** - USER_IDENTIFIERS_ASSOCIATED (DEBUG) - *Recently changed*

Actually 21 events total when including the 5 recently changed ones.

**Subtotal**: 20 unique locations, 21 total events

---

## Implementation Strategy

### Phase 1: Add Descriptions to Simple Events (20 locations)

Start with events that have correct types but just need descriptions:

1. **ErrorEvents (5)**: Read code context, add meaningful descriptions
2. **Extensions (5)**: Read code context, add meaningful descriptions
3. **MCP (3)**: Read code context, add meaningful descriptions
4. **A2A (2)**: Read code context, add meaningful descriptions
5. **Other (6)**: Read code context, add meaningful descriptions

### Phase 2: Fix Event Types Then Add Descriptions (17 events)

Fix the underlying event type issues first, then add descriptions:

1. **RETRY_ATTEMPTED (9)**: Change to specific error types
2. **INTERNAL_ERROR (5)**: Change to specific error types
3. **Anti-Pattern (1)**: Create specific ErrorEvent
4. **Generic types (2)**: Consider more specific events

---

## Summary

| Category | Count | Action |
|----------|-------|--------|
| Already Fixed (skip) | 8 | Skip (4 removed, 4 recently changed but need descriptions) |
| Need Event Type Changes | 17 | Fix event types first, then descriptions |
| Need Descriptions Only | 20 | Add descriptions directly |
| **Total** | **45** | **37 to fix** (8 already done) |

**Recommended Approach**:
1. Start with "Need Descriptions Only" (20 events) - quick wins
2. Then tackle "Need Event Type Changes" (17 events) - more complex

---

## Next Step

Create implementation plan for adding descriptions to the 20 straightforward events.
