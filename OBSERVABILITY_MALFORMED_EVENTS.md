# Malformed Observability Events - Status Report

## Summary
**Original**: 35 malformed observability.observe() calls  
**Fixed**: 15 events (43% complete)  
**Remaining**: 20 events (57%)

### Breakdown:
- ✅ **Fixed**: 14 STRING events in `src/muxi/services/a2a/client.py` (commit d71b1557)
- ✅ **Fixed**: 1 event fixed automatically
- ❌ **Remaining**: 14 STRING events (raw strings instead of enums)
- ❌ **Remaining**: 6 MALFORMED events (missing level keywords or using conditionals)

## Fixed Files

### ✅ 1. src/muxi/services/a2a/client.py (14 STRING events) - COMPLETED
**All raw strings converted to proper enums (commit d71b1557):**
**Raw strings → Proper enums needed:**
- `"a2a.sdk.initialized"` → `SystemEvents.A2A_REGISTRY_CLIENT_INITIALIZED`
- `"a2a.sdk.skipped"` → `SystemEvents.OPERATION_COMPLETED` (with skip context)
- `"a2a.sdk.error"` → `ErrorEvents.INTERNAL_ERROR`
- `"a2a.service.initialized"` → `SystemEvents.SERVICE_STARTED`
- `"a2a.routing.internal"` → `ConversationEvents.A2A_MESSAGE_SENT` (DEBUG level)
- `"a2a.routing.external"` → `ConversationEvents.A2A_MESSAGE_SENT` (DEBUG level)
- `"a2a_message_sent"` → `ConversationEvents.A2A_MESSAGE_SENT`
- `"a2a.message.error"` → `ConversationEvents.A2A_MESSAGE_FAILED`
- `"a2a_message_error"` → `ConversationEvents.A2A_MESSAGE_FAILED`
- `"a2a.handler.error"` → `ConversationEvents.A2A_MESSAGE_FAILED`
- `"a2a.handler.registered"` → `SystemEvents.A2A_AGENT_REGISTERED`
- `"a2a.cleanup.success"` → `SystemEvents.OPERATION_COMPLETED`
- `"a2a.cleanup.error"` → `ErrorEvents.INTERNAL_ERROR`
- `"a2a.cleanup.complete"` → `SystemEvents.OPERATION_COMPLETED`

### 2. src/muxi/utils/user_resolution.py (7 STRING events)
**Raw strings → Proper enums needed:**
- `"user_identifier.resolved"` (2x) → `SystemEvents.OPERATION_COMPLETED`
- `"user_identifier.cache_hit"` → `SystemEvents.OPERATION_COMPLETED` (DEBUG)
- `"user_identifier.cache_miss"` → `SystemEvents.OPERATION_COMPLETED` (DEBUG)
- `"user_identifier.cache_corrupted"` → `ErrorEvents.VALIDATION_FAILED`
- `"user_identifier.associated"` → `SystemEvents.OPERATION_COMPLETED`
- `"user_identifier.association_conflict"` → `ErrorEvents.VALIDATION_FAILED`

### 3. src/muxi/formation/overlord/overlord.py (3 STRING + 3 MALFORMED)
**STRING events:**
- `"service.initialized"` → `SystemEvents.SERVICE_STARTED`
- `"service.started"` → `SystemEvents.SERVICE_STARTED`
- `"service.updated"` → `SystemEvents.OPERATION_COMPLETED`

**MALFORMED events (positional args):**
- Line 860: `SystemEvents.SERVICE_STARTED` - missing description
- Line 1208: `SystemEvents.A2A_HEALTH_CHECK_COMPLETED` - missing level keyword

### 4. src/muxi/services/memory/extractor.py (2 STRING events)
**Raw strings → Proper enums needed:**
- `"memory_extractor_duplicate_skipped"` → `SystemEvents.OPERATION_COMPLETED` (DEBUG)
- `"memory_extractor_similar_stored"` → `SystemEvents.OPERATION_COMPLETED` (DEBUG)

### 5. src/muxi/services/memory/sqlite.py (1 STRING + 1 MALFORMED)
- `"MEMORY_WORKING_LOOKUP"` → `ConversationEvents.MEMORY_WORKING_RETRIEVED` (DEBUG)
- Line 730: Missing both event_type and level keywords

### 6. src/muxi/formation/overlord/chat_orchestrator.py (1 STRING)
- `"memory.long_term.search_failed"` → `ErrorEvents.DATABASE_OPERATION_FAILED`

### 7. src/muxi/services/a2a/auth/inbound.py (1 MALFORMED)
- Line 596: `SystemEvents.A2A_AUTH_VALIDATED` - missing level keyword

### 8. src/muxi/services/a2a/registry_client.py (1 MALFORMED)
- Line 342: `SystemEvents.A2A_HEALTH_CHECK_COMPLETED` - missing level keyword

### 9. src/muxi/formation/formation.py (1 MALFORMED)
- Line 2457: `SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED` - missing description

### 10. src/muxi/services/secrets/secrets_manager.py (1 MALFORMED)
- Line 578: `SystemEvents.SECRET_OPERATION_COMPLETED` - missing description

## Remaining Files Requiring Fixes

### 1. src/muxi/utils/user_resolution.py (7 STRING events)
All need conversion from raw strings to SystemEvents enums.

### 2. src/muxi/services/memory/extractor.py (2 STRING events)
Raw strings need conversion to SystemEvents.OPERATION_COMPLETED.

### 3. src/muxi/services/memory/sqlite.py (1 STRING + 1 MALFORMED)
Line 730: Raw string "MEMORY_WORKING_LOOKUP" + raw string level "debug".

### 4. src/muxi/formation/overlord/chat_orchestrator.py (1 STRING)
Line 832: "memory.long_term.search_failed" → ErrorEvents.DATABASE_OPERATION_FAILED

### 5. src/muxi/formation/overlord/overlord.py (3 STRING + 2 MALFORMED)
- Lines with STRING: service.* events  
- Lines 860, 1208: MALFORMED with conditional levels

### 6. src/muxi/services/a2a/auth/inbound.py (1 MALFORMED)
Line 596: Conditional level expression needs keyword.

### 7. src/muxi/services/a2a/registry_client.py (1 MALFORMED)
Line 342: Conditional level expression needs keyword.

### 8. src/muxi/formation/formation.py (1 MALFORMED)
Line 2457: Missing description field.

### 9. src/muxi/services/secrets/secrets_manager.py (1 MALFORMED)
Line 578: Missing description field.

## Progress & Impact

### Completed (43%)
- ✅ Fixed 15 of 35 malformed events
- ✅ Cleaned up entire a2a/client.py file (largest offender)
- ✅ CSV now accurately categorizes 1,241 events (vs 1,226 before)
- ✅ Improved event type distribution:
  - ConversationEvents: 321 → 327 (+6)
  - SystemEvents: 498 → 504 (+6)
  - ErrorEvents: 370 → 372 (+2)

### Remaining (57%)
- 20 events across 9 files
- Mostly user_resolution.py (7) and overlord.py (5)
- Would take ~1-2 hours to fix manually with proper testing

## Recommended Fix Approach

### Option 1: Batch Fix Script (Fast but risky)
Create automated script to replace all raw strings with proper enums.
- **Pros**: Fast, covers all 35 at once
- **Cons**: Risk of incorrect mappings, needs careful testing

### Option 2: Manual File-by-File (Slow but safe)
Fix each file manually with proper enum mapping.
- **Pros**: Correct mapping, safer
- **Cons**: Time-consuming (35 fixes across 10 files)

### Option 3: Remove Low-Value Events (Strategic)
Many of these are DEBUG-level events that might not be needed.
- Review if events like "cache_hit", "routing.internal" are actually useful
- Remove instead of fix if they're noise

## Impact
These 35 malformed events represent **2.8% of total 1,261 events**.
Fixing them will provide:
- Clean CSV output for analysis
- Proper event type categorization
- Correct filtering by SystemEvents/ConversationEvents/ErrorEvents

## Next Steps
1. Decide on approach (batch/manual/remove)
2. Execute fixes
3. Re-run audit script
4. Verify CSV shows 0 STRING/MALFORMED events
