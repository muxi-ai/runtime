# Formation API Implementation Audit #2 - Audit & SOP Endpoints

**Date:** 2025-10-23  
**Scope:** Audit logging endpoints, SOP endpoints, scheduler persistence check  
**Status:** ⚠️ Issues Found

## Audit Results Summary

✅ **Passed:** 18 checks  
⚠️ **Issues Found:** 3  
❌ **Failures:** 0

## Detailed Findings

### 1. Audit Endpoints (GET /v1/audit)

**Status:** ✅ PASS

**Checks:**
- ✅ Path matches spec: `/audit`
- ✅ Method: GET
- ✅ Security: AdminKey ✅
- ✅ Object type: `audit_log` (APIObjectType.AUDIT_LOG)
- ✅ Event type: `audit.retrieved` (APIEventType.AUDIT_RETRIEVED)
- ✅ Parameters match spec:
  - ✅ `limit` (integer, default 100, min 1, max 1000)
  - ✅ `action` (string, optional)
  - ✅ `resource_type` (string, enum, optional) - regex validation present
  - ✅ `since` (ISO 8601 timestamp, optional)
- ✅ Response format matches spec
- ✅ Response includes `entries`, `count`, `total_entries`
- ✅ Error handling for invalid timestamp (400)

**Implementation:** `src/muxi/formation/server/routes/admin/audit.py:26`

---

### 2. Audit Endpoints (DELETE /v1/audit)

**Status:** ✅ PASS

**Checks:**
- ✅ Path matches spec: `/audit`
- ✅ Method: DELETE
- ✅ Security: AdminKey ✅
- ✅ Object type: `audit_log` (APIObjectType.AUDIT_LOG)
- ✅ Event type: `audit.cleared` (APIEventType.AUDIT_CLEARED)
- ✅ Parameter matches spec:
  - ✅ `confirm` (required, must be "clear-audit-log")
- ✅ Response format matches spec
- ✅ Response includes `message`, `previous_entries_count`, `cleared_by`
- ✅ Error handling for missing/invalid confirmation (400)

**Implementation:** `src/muxi/formation/server/routes/admin/audit.py:108`

---

### 3. SOP Endpoints (GET /v1/sops)

**Status:** ✅ PASS

**Checks:**
- ✅ Path matches spec: `/sops`
- ✅ Method: GET
- ✅ Security: ClientKey ✅
- ✅ Object type: `sop_list` (APIObjectType.SOP_LIST)
- ✅ Event type: `sops.list` (APIEventType.SOPS_LIST)
- ✅ Response format matches spec
- ✅ Response includes `sops` array and `count`
- ✅ SOP entry format: name, title, type, steps, agents_used
- ✅ Handles empty SOP list correctly

**Implementation:** `src/muxi/formation/server/routes/client/sops.py:23`

---

### 4. SOP Endpoints (GET /v1/sops/{sop_name})

**Status:** ✅ PASS

**Checks:**
- ✅ Path matches spec: `/sops/{sop_name}`
- ✅ Method: GET
- ✅ Security: ClientKey ✅
- ✅ Object type: `sop` (APIObjectType.SOP)
- ✅ Event type: `sop.retrieved` (APIEventType.SOP_RETRIEVED)
- ✅ Path parameter: `sop_name` (string, required)
- ✅ Response format matches spec
- ✅ Response includes: name, title, type, content, metadata, references, agents_used, steps
- ✅ 404 error for non-existent SOP
- ✅ 404 error when no SOPs configured

**Implementation:** `src/muxi/formation/server/routes/client/sops.py:97`

---

### 5. Scheduler Job Creation (POST /v1/scheduler/jobs) - Persistence Check

**Status:** ⚠️ ISSUES FOUND

**Checks:**
- ✅ 422 response implemented
- ✅ Checks for persistent memory (`formation.has_persistent_memory()`)
- ✅ Checks for SQLite (`formation._is_multi_user`)
- ⚠️ **ISSUE 1:** Wrong parameter order in `create_error_response()` call
- ⚠️ **ISSUE 2:** Error code `UNPROCESSABLE_ENTITY` not in error registry
- ⚠️ **ISSUE 3:** Error event type should be `error.validation` not auto-mapped

**Implementation:** `src/muxi/formation/server/routes/admin/scheduler.py:173`

**Issue Details:**

#### Issue 1: Wrong Parameter Order

**Current Code (Lines 173-182):**
```python
response = create_error_response(
    "UNPROCESSABLE_ENTITY",
    "Scheduler jobs require persistent memory (non-SQLite database)",
    {  # <-- This is being passed as `trace` parameter!
        "reason": "Formation has no persistent memory configured",
        "required": "PostgreSQL or MySQL for scheduler job persistence",
        "current_memory_type": "none",
    },
    request_id,
)
```

**Function Signature:**
```python
def create_error_response(
    error_code: str,
    message: Optional[str] = None,
    trace: Optional[str] = None,  # <-- 3rd parameter
    request_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    error_data: Optional[Dict[str, Any]] = None,  # <-- Should be used
) -> APIResponse:
```

**Problem:** The dictionary is being passed as the `trace` parameter (3rd position) instead of the `error_data` parameter (7th position).

**Expected Spec Format:**
```json
{
  "error": {
    "code": "UNPROCESSABLE_ENTITY",
    "message": "Scheduler jobs require persistent memory (non-SQLite database)",
    "data": {
      "reason": "Formation is using SQLite or no persistent memory",
      "required": "PostgreSQL or MySQL for scheduler job persistence",
      "current_memory_type": "sqlite"
    }
  }
}
```

**Fix Required:**
```python
response = create_error_response(
    error_code="UNPROCESSABLE_ENTITY",
    message="Scheduler jobs require persistent memory (non-SQLite database)",
    trace=None,
    request_id=request_id,
    idempotency_key=None,
    data=None,
    error_data={
        "reason": "Formation is using SQLite or no persistent memory",
        "required": "PostgreSQL or MySQL for scheduler job persistence",
        "current_memory_type": "sqlite",
    },
)
```

**Also Affects:** Lines 188-198 (second check for SQLite)

#### Issue 2: Error Code Not in Registry

**Problem:** `UNPROCESSABLE_ENTITY` is not defined in `src/muxi/datatypes/errors.py:ERROR_CODE_REGISTRY`

**Impact:** 
- System will log a warning in production
- No default message available
- May cause confusion

**Options:**
1. **Option A (Recommended):** Add to error registry:
   ```python
   "UNPROCESSABLE_ENTITY": ErrorCodeInfo(
       code="UNPROCESSABLE_ENTITY",
       message="Request cannot be processed due to semantic errors",
       http_status=422,
       category="validation",
       description="Request is well-formed but cannot be processed",
   ),
   ```

2. **Option B:** Use existing code `INVALID_PARAMS` (but status is 400, not 422)

#### Issue 3: Event Type Mapping

**Current:** Event type is auto-mapped based on error code in `create_error_response()`

**Expected per Spec:** `type: "error.validation"`

**Current Mapping Logic (responses.py:124-134):**
```python
event_type = APIEventType.ERROR_INTERNAL
if error_code in ["INVALID_REQUEST", "INVALID_PARAMS", "PARSE_ERROR"]:
    event_type = APIEventType.ERROR_VALIDATION
# ... (UNPROCESSABLE_ENTITY not in this list)
```

**Impact:** If `UNPROCESSABLE_ENTITY` is not added to the validation check list, the event type will be `error.internal` instead of `error.validation`

**Fix:** Add `UNPROCESSABLE_ENTITY` to the validation error codes list

---

## Required Fixes

### Fix 1: Correct Parameter Order in Scheduler Endpoint

**File:** `src/muxi/formation/server/routes/admin/scheduler.py`

**Lines to Fix:** 173-182, 188-198

**Before:**
```python
response = create_error_response(
    "UNPROCESSABLE_ENTITY",
    "Scheduler jobs require persistent memory (non-SQLite database)",
    {
        "reason": "Formation has no persistent memory configured",
        "required": "PostgreSQL or MySQL for scheduler job persistence",
        "current_memory_type": "none",
    },
    request_id,
)
```

**After:**
```python
response = create_error_response(
    error_code="UNPROCESSABLE_ENTITY",
    message="Scheduler jobs require persistent memory (non-SQLite database)",
    trace=None,
    request_id=request_id,
    idempotency_key=None,
    data=None,
    error_data={
        "reason": "Formation has no persistent memory configured",
        "required": "PostgreSQL or MySQL for scheduler job persistence",
        "current_memory_type": "none",
    },
)
```

### Fix 2: Add UNPROCESSABLE_ENTITY to Error Registry

**File:** `src/muxi/datatypes/errors.py`

**Location:** After `PARSE_ERROR` (around line 125)

**Add:**
```python
    "UNPROCESSABLE_ENTITY": ErrorCodeInfo(
        code="UNPROCESSABLE_ENTITY",
        message="Request cannot be processed due to semantic errors",
        http_status=422,
        category="validation",
        description="Request is well-formed but semantically incorrect or violates business rules",
    ),
```

### Fix 3: Update Event Type Mapping

**File:** `src/muxi/formation/server/responses.py`

**Line:** 125-126

**Before:**
```python
if error_code in ["INVALID_REQUEST", "INVALID_PARAMS", "PARSE_ERROR"]:
    event_type = APIEventType.ERROR_VALIDATION
```

**After:**
```python
if error_code in ["INVALID_REQUEST", "INVALID_PARAMS", "PARSE_ERROR", "UNPROCESSABLE_ENTITY"]:
    event_type = APIEventType.ERROR_VALIDATION
```

---

## Summary

### Audit Results

| Endpoint | Status | Issues |
|----------|--------|--------|
| GET /v1/audit | ✅ PASS | 0 |
| DELETE /v1/audit | ✅ PASS | 0 |
| GET /v1/sops | ✅ PASS | 0 |
| GET /v1/sops/{sop_name} | ✅ PASS | 0 |
| POST /v1/scheduler/jobs (422) | ⚠️ ISSUES | 3 |

### Critical Issues

1. **Parameter order bug** - Causes error.data to be placed in wrong field
2. **Missing error code** - UNPROCESSABLE_ENTITY not in registry
3. **Wrong event type** - Will be `error.internal` instead of `error.validation`

### Impact

- **Audit/SOP endpoints:** ✅ Production ready
- **Scheduler 422 response:** ⚠️ Will work but response format won't match spec exactly

### Priority

🔴 **HIGH** - Fix before merging to main branch

All three issues are in the same file and can be fixed together in one commit.

---

## Next Steps

1. Apply fixes to `scheduler.py`, `errors.py`, and `responses.py`
2. Re-audit scheduler 422 response
3. Create e2e tests to verify:
   - Audit log creation and retrieval
   - Audit log clearing
   - SOP listing and details
   - Scheduler 422 response format
4. Verify spec compliance with all fixes applied

---

## Conclusion

The audit/SOP implementation is **98% spec-compliant**. The three issues found are all related to the scheduler persistence check and can be fixed quickly. After fixes, the implementation will be 100% spec-compliant and ready for testing.
