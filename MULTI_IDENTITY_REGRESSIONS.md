# Multi-Identity Regressions Found During E2E Testing

**Date:** January 9, 2025  
**Branch:** `multiple-identities`  
**Status:** ❌ **REGRESSIONS FOUND - NOT READY FOR MERGE**

---

## Executive Summary

During random E2E regression testing (5 tests from different areas), **critical regressions were discovered** that prevent merge. The multi-identity implementation works correctly in isolation (direct DB tests pass), but integration with existing code has issues.

**Test Results:**
- ✅ Test 1/5: Foundation - Simple Chat (PASSING after fixes)
- ❌ Test 2/5: Memory - SQLite Persistence (FAILING - SQLite module incomplete)
- ⏸️ Test 3-5: Not run yet (blocked by Test 2 failure)

**Critical Issues:**
1. ✅ **FIXED:** db_manager None handling
2. ✅ **FIXED:** ObservabilityManager signature mismatch
3. ❌ **NOT FIXED:** SQLite module still has 10+ external_user_id references

---

## Regression #1: db_manager None Handling ✅ FIXED

### Problem

When `user_id` is provided but no database is configured, the system tried to resolve it anyway:

```python
internal_user_id, muxi_user_id = await resolve_user_identifier(
    identifier=user_id,
    formation_id=self.overlord.formation_id,
    db_manager=None,  # ❌ This causes AttributeError
    kv_cache=None,
)
```

**Error:**
```
AttributeError: 'NoneType' object has no attribute 'get_async_session'
```

### Root Cause

Not all formations have databases configured. Minimal formations (like foundation tests) don't have `long_term_memory` or `db_manager`.

### Fix Applied

**File:** `src/muxi/formation/overlord/chat_orchestrator.py`

```python
# Use long_term_memory's db_manager if overlord's is not available
db_mgr = self.overlord.db_manager or (
    self.overlord.long_term_memory.db_manager 
    if self.overlord.long_term_memory else None
)

# Only resolve if db_manager is available
if db_mgr is not None:
    internal_user_id, muxi_user_id = await resolve_user_identifier(
        identifier=user_id,
        formation_id=self.overlord.formation_id,
        db_manager=db_mgr,
        kv_cache=None,
    )
else:
    # No database available - skip resolution
    # user_id will be used directly by downstream code
    internal_user_id = None
    muxi_user_id = None
```

### Impact

✅ Backwards compatible - formations without databases still work
✅ Test 1/5 now passing

---

## Regression #2: ObservabilityManager Signature Mismatch ✅ FIXED

### Problem

`ObservabilityManager.track_request()` didn't accept the new user ID parameters:

```python
with self.overlord.observability_manager.track_request(
    request_id=request_id,
    session_id=session_id,
    formation_id=self.overlord.formation_id,
    user_id=str(user_id) if user_id is not None else None,
    internal_user_id=internal_user_id,  # ❌ unexpected keyword argument
    muxi_user_id=muxi_user_id,  # ❌ unexpected keyword argument
) as context:
```

**Error:**
```
ObservabilityManager.track_request() got an unexpected keyword argument 'internal_user_id'
```

### Root Cause

`RequestContextManager.track_request()` was updated with the new parameters, but `ObservabilityManager.track_request()` was not.

### Fix Applied

**File:** `src/muxi/services/observability/manager.py`

```python
@contextmanager
def track_request(
    self,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    formation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    internal_user_id: Optional[int] = None,  # ✅ Added
    muxi_user_id: Optional[str] = None,  # ✅ Added
):
    """Context manager for request tracking with automatic context propagation (sync version)."""
    # ... (rest of implementation updated)
```

### Impact

✅ Signatures now consistent across both managers
✅ Test 1/5 now passing

---

## Regression #3: SQLite Module Incomplete ❌ NOT FIXED

### Problem

The SQLite module (`src/muxi/services/memory/sqlite.py`) was **partially updated** but still has many references to the deleted `external_user_id` column:

**Found References:**
1. Line 99: `async def get_or_create_user(self, external_user_id: str)`
2. Line 114: Query using `external_user_id`
3. Line 135: INSERT using `external_user_id`
4. Line 173: CREATE TABLE with `external_user_id TEXT NOT NULL`
5. Line 177: UNIQUE constraint on `external_user_id`
6. Line 227: SELECT using `external_user_id`
7. Line 621: SELECT using `external_user_id`
8. Plus docstrings and comments

**Error When Running:**
```
(sqlite3.IntegrityError) NOT NULL constraint failed: users.external_user_id
[SQL: INSERT INTO users (public_id, formation_id) VALUES (?, ?)]
```

### Root Cause

During the initial multi-identity implementation, the SQLite module was updated in one location (line 75-85) to query `user_identifiers`, but the rest of the module was **not updated**. This was missed during the two rounds of code review.

### Partial Fixes Applied

**File:** `src/muxi/services/memory/sqlite.py`

Fixed 2 out of 10+ locations:
1. Line 236: Updated INSERT statement (removed external_user_id)
2. Line 246: Updated SELECT to use JOIN with user_identifiers

**Still Broken:**
- CREATE TABLE statement still defines external_user_id
- get_or_create_user() method signature
- Multiple SELECT queries
- Docstrings

### Impact

❌ **BLOCKING:** Test 2/5 (Memory/SQLite) fails
❌ **BLOCKING:** All tests using SQLite memory will fail
❌ **BLOCKING:** Cannot merge until fully fixed

---

## Additional Testing Needed

### User Requested: Observability Events Testing

**Requirement:**
> "we also need to test that user_id (dev provided) and muxi_user_id are present in observability events"

**Status:** ⏸️ **NOT TESTED YET**

Need to verify that observability events include:
- `user_id` (developer-provided identifier from API call)
- `muxi_user_id` (public_id from users table)
- `internal_user_id` (internal database ID)

**Test Plan:**
1. Create test that makes chat request with user_id
2. Capture observability events
3. Assert all 3 user IDs are present in events
4. Verify format and values are correct

---

## SQLite Module - Comprehensive Fix Needed

### Files Requiring Updates

**Primary File:**
- `src/muxi/services/memory/sqlite.py` (~736 lines)

### Required Changes

1. **Remove external_user_id from CREATE TABLE** (line ~173)
   ```sql
   -- OLD
   CREATE TABLE IF NOT EXISTS users (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       public_id TEXT NOT NULL UNIQUE,
       external_user_id TEXT NOT NULL,  -- ❌ Remove this
       formation_id TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(external_user_id, formation_id)  -- ❌ Remove this
   )
   
   -- NEW
   CREATE TABLE IF NOT EXISTS users (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       public_id TEXT NOT NULL UNIQUE,
       formation_id TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(public_id, formation_id)  -- ✅ Use public_id
   )
   ```

2. **Add user_identifiers table creation**
   ```sql
   CREATE TABLE IF NOT EXISTS user_identifiers (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       user_id INTEGER NOT NULL,
       identifier TEXT NOT NULL,
       identifier_type TEXT,
       formation_id TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
       UNIQUE(identifier, formation_id)
   )
   
   CREATE INDEX IF NOT EXISTS idx_user_identifiers_identifier 
       ON user_identifiers(identifier, formation_id);
   CREATE INDEX IF NOT EXISTS idx_user_identifiers_user_id 
       ON user_identifiers(user_id);
   ```

3. **Update get_or_create_user() method** (line 99)
   - Change signature to use `identifier` instead of `external_user_id`
   - Query user_identifiers table
   - Use resolve_user_identifier() utility

4. **Update all SELECT queries** (lines 114, 227, 621, etc.)
   ```sql
   -- OLD
   SELECT id FROM users WHERE external_user_id = ? AND formation_id = ?
   
   -- NEW
   SELECT u.id FROM users u
   JOIN user_identifiers ui ON u.id = ui.user_id
   WHERE ui.identifier = ? AND ui.formation_id = ?
   ```

5. **Update all INSERT statements**
   - Remove external_user_id from INSERT
   - Add corresponding INSERT into user_identifiers

6. **Update docstrings and comments**
   - Replace references to external_user_id
   - Document new multi-identity approach

### Estimated Effort

- **Time:** 2-3 hours
- **Lines Changed:** ~50-80 lines
- **Complexity:** Medium (systematic find-and-replace + testing)
- **Risk:** Medium (SQLite is used in many tests)

---

## Test Results Summary

### Tests Run

**Test 1/5: Foundation - Simple Chat** ✅
- **File:** `e2e/tests/1_foundation/test_1b_4_simple_chat.py`
- **Status:** PASSING (after fixes)
- **Duration:** 15.87s
- **Coverage:** Basic chat without database

**Test 2/5: Memory - SQLite Persistence** ❌
- **File:** `e2e/tests/2_memory/test_2b1_sqlite_persistence.py`
- **Status:** FAILING
- **Error:** `NOT NULL constraint failed: users.external_user_id`
- **Blocked:** SQLite module incomplete

**Test 3-5:** ⏸️ NOT RUN
- Blocked by Test 2 failure
- Need to fix SQLite before continuing

---

## Commits Made

### Commit 1: Test Report
```
1667998c docs: add comprehensive E2E test report for multi-identity
```
- Created full E2E test report (890 lines)
- Documented all passing tests
- Performance metrics

### Commit 2: Regression Fixes
```
4488bdc7 fix: critical regression fixes for multi-identity
```
- Fixed db_manager None handling
- Fixed ObservabilityManager signature
- Partial SQLite module fix (2/10+ locations)

---

## Recommended Next Steps

### Before Merge (REQUIRED)

1. **Complete SQLite Module Fix** ⚠️ **BLOCKING**
   - Update all 10+ external_user_id references
   - Update CREATE TABLE statements
   - Add user_identifiers table creation
   - Test on fresh SQLite databases

2. **Run Full Regression Suite** ⚠️ **BLOCKING**
   - Complete tests 2-5 of random regression tests
   - Run at least 10-15 random E2E tests
   - Ensure zero failures

3. **Observability Events Testing** ⚠️ **REQUIRED**
   - Create test for user_id/muxi_user_id in events
   - Verify all 3 user IDs present
   - Document event format

4. **Clean Migration Path**
   - Test migration on existing SQLite databases
   - Provide migration script for SQLite users
   - Document breaking changes

### After Initial Fixes

5. **Memobase Module Review**
   - Check for external_user_id references (found 17)
   - Update if still using old approach
   - May be intentional (user-facing API)

6. **Full E2E Test Suite**
   - Run all 200+ E2E tests
   - Fix any additional regressions
   - Update test results report

---

## Risk Assessment

### Current State: ⚠️ HIGH RISK

**Reasons:**
1. ❌ Core SQLite module incomplete (used by many tests)
2. ❌ Only 1/5 regression tests passing
3. ❌ Observability events not tested
4. ❌ Migration path for existing SQLite databases unclear

### After Fixes: ✅ LOW RISK (estimated)

**If all fixes applied:**
- ✅ SQLite module complete
- ✅ All regression tests passing
- ✅ Observability verified
- ✅ Migration documented

---

## Conclusion

The multi-identity implementation is **fundamentally sound** (direct DB tests pass 100%), but has **integration issues** that were missed during initial testing.

**Key Findings:**
1. Core logic is correct (resolve_user_identifier, associate_user_identifiers)
2. Database schema is correct (User, UserIdentifier models)
3. Entry point integration works (chat_orchestrator)
4. BUT: SQLite module was only partially updated
5. AND: Some signature mismatches in observability

**Recommendation:** ❌ **DO NOT MERGE YET**

**Required Work:**
- 2-4 hours to complete SQLite module
- 2-3 hours for full regression testing
- 1 hour for observability testing
- **Total:** ~5-8 hours additional work

**Confidence After Fixes:** 95%

---

**Report Generated:** January 9, 2025  
**Author:** Droid (Factory AI)  
**Branch:** `multiple-identities`  
**Total Commits:** 23
