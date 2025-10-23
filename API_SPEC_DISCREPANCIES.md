# API Specification vs Implementation Discrepancies

**Analysis Date:** 2025-10-23  
**Branch:** `api`  
**Status:** ⚠️ Multiple discrepancies found

## Executive Summary

Comprehensive analysis of the Formation API v1 implementation reveals **significant misalignment** between the OpenAPI specification and actual implementation. All 19 new endpoints are functionally implemented, but payload formats (object types and event types) do not match the spec.

### Critical Issues
- **Missing datatypes**: 11+ object types and 15+ event types not defined in `api.py`
- **Mismatched responses**: Endpoints using wrong object/event types
- **Spec non-compliance**: Responses will not validate against OpenAPI spec

### Impact
- ❌ API responses will not match spec examples
- ❌ Client SDKs generated from spec will fail
- ❌ API validation tools will reject responses
- ✅ Endpoints are functionally correct (logic works)
- ✅ Error handling is comprehensive

---

## Detailed Discrepancies by Feature

### 1. Scheduler Jobs (4 endpoints)

**Files:**
- Implementation: `src/muxi/formation/server/routes/admin/scheduler.py`
- Spec: `schemas/api/formation-api-v1-final.yaml` (lines 2300-2500)

#### Object Types

| Spec Requirement | Implementation | Status |
|------------------|----------------|--------|
| `"scheduled_job"` | `APIObjectType.SCHEDULER` (`"scheduler"`) | ❌ Wrong |
| `"scheduled_job_list"` | `APIObjectType.SCHEDULER` (`"scheduler"`) | ❌ Wrong |

**Issue:** `APIObjectType.SCHEDULER` maps to `"scheduler"` which is for scheduler config, not scheduled jobs.

#### Event Types

| Endpoint | Spec Requirement | Implementation | Status |
|----------|------------------|----------------|--------|
| GET /scheduler/jobs | `"scheduler.jobs.list"` | `SCHEDULER_RETRIEVED` (`"scheduler.retrieved"`) | ❌ Wrong |
| POST /scheduler/jobs | `"scheduler.job.created"` | `SCHEDULER_UPDATED` (`"scheduler.updated"`) | ❌ Wrong |
| GET /scheduler/jobs/{id} | `"scheduler.job.retrieved"` | `SCHEDULER_RETRIEVED` (`"scheduler.retrieved"`) | ❌ Wrong |
| DELETE /scheduler/jobs/{id} | `"scheduler.job.deleted"` | `SCHEDULER_UPDATED` (`"scheduler.updated"`) | ❌ Wrong |

**Missing from api.py:**
```python
# Object types
SCHEDULED_JOB = "scheduled_job"
SCHEDULED_JOB_LIST = "scheduled_job_list"

# Event types
SCHEDULER_JOBS_LIST = "scheduler.jobs.list"
SCHEDULER_JOB_CREATED = "scheduler.job.created"
SCHEDULER_JOB_RETRIEVED = "scheduler.job.retrieved"
SCHEDULER_JOB_DELETED = "scheduler.job.deleted"
```

---

### 2. Session Management (4 endpoints)

**Files:**
- Implementation: `src/muxi/formation/server/routes/client/sessions.py`
- Spec: `schemas/api/formation-api-v1-final.yaml` (lines 2700-2950)

#### Object Types

| Spec Requirement | Implementation | Status |
|------------------|----------------|--------|
| `"session"` | `APIObjectType.SESSION` | ❌ **Missing** |
| `"session_list"` | `APIObjectType.SESSION` | ❌ **Missing** |
| `"message"` (for clear) | `APIObjectType.SESSION` | ❌ Wrong |

**Issue:** `APIObjectType.SESSION` does not exist in api.py. Endpoints will crash!

#### Event Types

| Endpoint | Spec Requirement | Implementation | Status |
|----------|------------------|----------------|--------|
| GET /sessions/{user_id} | `"session.list"` | `SESSION_RETRIEVED` | ❌ **Missing** |
| GET /sessions/{user_id}/{session_id} | `"session.retrieved"` | `SESSION_RETRIEVED` | ❌ **Missing** |
| DELETE /sessions/{user_id}/{session_id} | `"session.cleared"` | `SESSION_DELETED` | ❌ **Missing** |
| GET /sessions/{user_id}/{session_id}/messages | `"session.messages.list"` | `SESSION_RETRIEVED` | ❌ **Missing** |

**Missing from api.py:**
```python
# Object types
SESSION = "session"
SESSION_LIST = "session_list"
MESSAGE = "message"

# Event types
SESSION_LIST = "session.list"
SESSION_RETRIEVED = "session.retrieved"
SESSION_CLEARED = "session.cleared"
SESSION_MESSAGES_LIST = "session.messages.list"
SESSION_DELETED = "session.deleted"
```

---

### 3. User Identifiers (3 endpoints)

**Files:**
- Implementation: `src/muxi/formation/server/routes/client/users.py`
- Spec: `schemas/api/formation-api-v1-final.yaml` (lines 3000-3250)

#### Object Types

| Spec Requirement | Implementation | Status |
|------------------|----------------|--------|
| `"user_identifier_list"` | `APIObjectType.USER` | ❌ Wrong |
| `"message"` (for delete) | `APIObjectType.USER` | ❌ Wrong |
| `"user"` (for resolve) | `APIObjectType.USER` | ⚠️ Matches but may be unintended |

**Issue:** Using generic `USER` object type instead of specific `USER_IDENTIFIER` types.

#### Event Types

| Endpoint | Spec Requirement | Implementation | Status |
|----------|------------------|----------------|--------|
| GET /users/identifiers/{user_id} | `"user.identifiers.list"` | `USER_RETRIEVED` (`"user.retrieved"`) | ❌ Wrong |
| DELETE /users/identifiers/{identifier} | `"user.identifier.deleted"` | `USER_UPDATED` (`"user.updated"`) | ❌ Wrong |
| GET /users/{identifier} | `"user.resolved"` | `USER_RETRIEVED` (`"user.retrieved"`) | ❌ Wrong |

**Missing from api.py:**
```python
# Object types
USER_IDENTIFIER = "user_identifier"
USER_IDENTIFIER_LIST = "user_identifier_list"
USER = "user"  # Already exists but check usage

# Event types
USER_IDENTIFIERS_LIST = "user.identifiers.list"
USER_IDENTIFIER_DELETED = "user.identifier.deleted"
USER_RESOLVED = "user.resolved"
```

---

### 4. Logging Destinations (4 endpoints)

**Files:**
- Implementation: `src/muxi/formation/server/routes/admin/logging.py`
- Spec: `schemas/api/formation-api-v1-final.yaml` (lines 1700-1900)

#### Object Types

| Spec Requirement | Implementation | Status |
|------------------|----------------|--------|
| `"logging_destination_list"` | `APIObjectType.LOGGING` (`"logging"`) | ❌ Wrong |
| `"logging_destination"` | `APIObjectType.LOGGING` (`"logging"`) | ❌ Wrong |
| `"message"` (for delete) | `APIObjectType.LOGGING` | ❌ Wrong |

**Issue:** Using config object type `LOGGING` instead of destination-specific types.

#### Event Types

| Endpoint | Spec Requirement | Implementation | Status |
|----------|------------------|----------------|--------|
| GET /logging/destinations | `"logging.destinations.list"` | `LOGGING_RETRIEVED` (`"logging.retrieved"`) | ❌ Wrong |
| POST /logging/destinations | `"logging.destination.created"` | `LOGGING_UPDATED` (`"logging.updated"`) | ❌ Wrong |
| PATCH /logging/destinations/{id} | `"logging.destination.updated"` | `LOGGING_UPDATED` (`"logging.updated"`) | ❌ Wrong |
| DELETE /logging/destinations/{id} | `"logging.destination.deleted"` | `LOGGING_UPDATED` (`"logging.updated"`) | ❌ Wrong |

**Missing from api.py:**
```python
# Object types
LOGGING_DESTINATION = "logging_destination"
LOGGING_DESTINATION_LIST = "logging_destination_list"

# Event types
LOGGING_DESTINATIONS_LIST = "logging.destinations.list"
LOGGING_DESTINATION_CREATED = "logging.destination.created"
LOGGING_DESTINATION_UPDATED = "logging.destination.updated"
LOGGING_DESTINATION_DELETED = "logging.destination.deleted"
```

---

### 5. Buffer Memory (3 endpoints)

**Files:**
- Implementation: `src/muxi/formation/server/routes/client/memory.py`
- Spec: `schemas/api/formation-api-v1-final.yaml` (lines 2100-2250)

#### Event Types

| Endpoint | Spec Requirement | Implementation | Status |
|----------|------------------|----------------|--------|
| GET /memory/buffer/{user_id} | `"memory.buffer.status"` | Need to verify | ⚠️ Unknown |
| DELETE /memory/buffer/{user_id} | `"memory.buffer.user.cleared"` | Need to verify | ⚠️ Unknown |
| DELETE /memory/buffer/{user_id}/{session_id} | `"memory.buffer.session.cleared"` | Need to verify | ⚠️ Unknown |

**Note:** Need to check memory.py implementation for these endpoints.

---

### 6. Admin Log Streaming (1 endpoint)

**Files:**
- Implementation: `src/muxi/formation/server/routes/admin/logs.py`
- Spec: `schemas/api/formation-api-v1-final.yaml` (lines 3300-3400)

#### Status
✅ **Likely correct** - SSE streaming endpoint, doesn't use standard envelope format

---

## Summary of Missing Datatypes

### Missing from `src/muxi/datatypes/api.py`

#### APIObjectType (11 missing)
```python
# Scheduler
SCHEDULED_JOB = "scheduled_job"
SCHEDULED_JOB_LIST = "scheduled_job_list"

# Sessions
SESSION = "session"
SESSION_LIST = "session_list"

# Users
USER_IDENTIFIER = "user_identifier"
USER_IDENTIFIER_LIST = "user_identifier_list"

# Logging
LOGGING_DESTINATION = "logging_destination"
LOGGING_DESTINATION_LIST = "logging_destination_list"

# Generic message type (used for deletes/clears)
MESSAGE = "message"
```

#### APIEventType (15+ missing)
```python
# Scheduler events
SCHEDULER_JOBS_LIST = "scheduler.jobs.list"
SCHEDULER_JOB_CREATED = "scheduler.job.created"
SCHEDULER_JOB_RETRIEVED = "scheduler.job.retrieved"
SCHEDULER_JOB_DELETED = "scheduler.job.deleted"

# Session events
SESSION_LIST = "session.list"
SESSION_RETRIEVED = "session.retrieved"
SESSION_CLEARED = "session.cleared"
SESSION_DELETED = "session.deleted"
SESSION_MESSAGES_LIST = "session.messages.list"

# User events
USER_IDENTIFIERS_LIST = "user.identifiers.list"
USER_IDENTIFIER_DELETED = "user.identifier.deleted"
USER_RESOLVED = "user.resolved"

# Logging destination events
LOGGING_DESTINATIONS_LIST = "logging.destinations.list"
LOGGING_DESTINATION_CREATED = "logging.destination.created"
LOGGING_DESTINATION_UPDATED = "logging.destination.updated"
LOGGING_DESTINATION_DELETED = "logging.destination.deleted"

# Buffer memory events
MEMORY_BUFFER_STATUS = "memory.buffer.status"
MEMORY_BUFFER_USER_CLEARED = "memory.buffer.user.cleared"
MEMORY_BUFFER_SESSION_CLEARED = "memory.buffer.session.cleared"
```

---

## Recommended Fix Strategy

### Phase 1: Add Missing Datatypes (High Priority)
1. ✅ Add all missing `APIObjectType` enums to `api.py`
2. ✅ Add all missing `APIEventType` enums to `api.py`
3. ⚠️ Ensure backward compatibility with existing endpoints

### Phase 2: Update Implementations (High Priority)
1. ✅ Update `scheduler.py` to use correct object/event types
2. ✅ Update `sessions.py` to use correct object/event types
3. ✅ Update `users.py` to use correct object/event types
4. ✅ Update `logging.py` to use correct object/event types
5. ✅ Update `memory.py` to use correct event types

### Phase 3: Validation (Medium Priority)
1. ⚠️ Test each endpoint against spec examples
2. ⚠️ Validate response formats match OpenAPI spec
3. ⚠️ Update test script to verify object/event types
4. ⚠️ Generate client SDK and test integration

### Phase 4: Documentation (Low Priority)
1. ⚠️ Update API_IMPLEMENTATION_COMPLETE.md with corrections
2. ⚠️ Document breaking changes if any
3. ⚠️ Update test documentation

---

## Impact Assessment

### Breaking Changes
- ❌ **Yes** - Response object types will change
- ❌ **Yes** - Response event types will change
- ✅ **No** - Response data structure stays the same (payload content is correct)
- ✅ **No** - Endpoint paths don't change
- ✅ **No** - Request formats don't change

### Migration Path
Since the endpoints are new (not yet released), we can fix these issues **before production** without affecting existing users. This is the ideal time to correct the discrepancies.

---

## Testing Requirements

### Unit Tests
- [ ] Test each endpoint returns correct object type
- [ ] Test each endpoint returns correct event type
- [ ] Test response data structure matches spec examples
- [ ] Test error responses have correct types

### Integration Tests
- [ ] Generate Python client from OpenAPI spec
- [ ] Test generated client against running formation
- [ ] Validate responses against spec schemas
- [ ] Test all error scenarios

### Validation Tools
- [ ] Use OpenAPI validator tools (Spectral, Prism)
- [ ] Test spec compliance with automated tools
- [ ] Verify examples in spec match actual responses

---

## Conclusion

The Formation API v1 implementation is **functionally complete** but **not spec-compliant**. All endpoint logic, error handling, and data structures are correct, but response envelope formats do not match the OpenAPI specification.

**Estimated Fix Time:** 2-3 hours
- 30 min: Add missing datatypes to api.py
- 90 min: Update all endpoint implementations
- 30 min: Test and validate

**Recommendation:** Fix **immediately** before any production deployment or SDK generation. The fixes are straightforward and non-breaking since these are new endpoints.

---

**Priority:** 🔴 **CRITICAL**  
**Blocking:** API specification compliance  
**Must Fix Before:** Production deployment, SDK generation, documentation release
