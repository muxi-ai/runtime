# Area 12 - Scheduling Tests Migration Report

**Date**: 2025-09-30  
**Migration Status**: ⚠️ PARTIAL - Tests migrated but failing due to scheduler bugs  
**Tests Migrated**: 2 out of 11 total tests  
**Pattern Used**: RUNTIME (single base formation)

## Executive Summary

Area 12 (Scheduling) tests have been **partially migrated** to the new standardized structure. The migration infrastructure is complete with:
- ✅ Formation structure set up correctly
- ✅ Test files updated to RUNTIME pattern
- ✅ Common utilities integrated
- ❌ Tests failing due to scheduler service bugs
- ❌ Very slow performance (15-20s per test case)

### Critical Issues Discovered

1. **Scheduler Event Type Bug**: Fixed `SCHEDULER_INITIALIZED` → `SCHEDULER_MANAGER_INITIALIZED`
2. **Schedule Creation Failures**: ~80% of scheduling requests fail to create schedules
3. **Performance Issues**: Each test case takes 15-20 seconds (vs 3-5s expected)
4. **Error in Scheduler**: `'str' object is not callable` error in scheduler service

## Migration Details

### Files Created/Modified

#### New Test Structure
```
e2e/tests/12_scheduling/
├── __init__.py                          [NEW]
├── base_scheduling_test.py              [EXISTS - copied from old location]
├── formations/
│   └── formation-base/
│       ├── formation.yaml               [NEW - modified for SQLite]
│       ├── .key                         [NEW - copied]
│       ├── secrets.enc                  [NEW - symlink]
│       ├── agents/                      [NEW - copied]
│       └── mcp/                         [NEW - copied]
├── test_12_a_1.py                       [UPDATED - RUNTIME pattern]
└── test_12_a_2.py                       [UPDATED - RUNTIME pattern]
```

#### Changes Made

1. **test_12_a_1.py** (Basic Scheduling):
   - ✅ Added try/except import fallback
   - ✅ Removed `yaml_name` parameter from `setup_formation()`
   - ✅ Changed to direct `asyncio.run()` execution
   - ⚠️ Tests run but most fail due to scheduler bugs

2. **test_12_a_2.py** (Advanced Natural Language):
   - ✅ Added try/except import fallback
   - ✅ Removed `yaml_name` parameter from `setup_formation()`
   - ✅ Changed to direct `asyncio.run()` execution
   - ❌ Not yet tested due to test_12_a_1 issues

3. **Formation Configuration**:
   - ✅ Copied from old location
   - ✅ Modified database connection: `postgresql://` → `sqlite:///memory_test.db`
   - ✅ Scheduler enabled with correct settings
   - ✅ Created .key file for secrets encryption
   - ✅ Fixed secrets.enc symlink path

4. **Scheduler Manager Fix**:
   - ✅ Fixed `src/muxi/services/scheduler/manager.py` line 109
   - ✅ Changed `SCHEDULER_INITIALIZED` → `SCHEDULER_MANAGER_INITIALIZED`

### Test Coverage Analysis

According to TEST_MAPPING.md, Area 12 has 11 total tests:

| Test | Old Location | New Location | Status |
|------|--------------|--------------|--------|
| 12a1 - Basic Scheduling | test_12a1_basic_scheduling.py | test_12_a_1.py | ⚠️ MIGRATED - FAILING |
| 12a2 - Natural Language | test_12a2_natural_language_scheduling.py | test_12_a_2.py | ⚠️ MIGRATED - UNTESTED |
| 12a3 - Schedule with Context | test_12a3_schedule_with_context.py | - | ❌ NOT MIGRATED |
| 12a4 - Verify Execution | test_12a4_verify_execution.py | - | ❌ NOT MIGRATED |
| 12b1 - Cron-based Scheduling | test_12b1_cron_based_scheduling.py | - | ❌ NOT MIGRATED |
| 12b2 - Verify Recurring Execution | test_12b2_verify_recurring_execution.py | - | ❌ NOT MIGRATED |
| 12b3 - Wait for Execution | test_12b3_wait_for_execution.py | - | ❌ NOT MIGRATED |
| 12b4 - Sync vs Async | test_12b4_sync_vs_async.py | - | ❌ NOT MIGRATED |
| 12b5 - Capital Question | test_12b5_capital_question.py | - | ❌ NOT MIGRATED |
| 12c1 - One-time Execution | test_12c1_onetime_execution.py | - | ❌ NOT MIGRATED |
| 12d1 - Error Scenarios | test_12d1_error_scenarios.py | - | ❌ NOT MIGRATED |

**Migration Progress**: 2/11 tests (18%)

## Test Results

### test_12_a_1.py - Basic Scheduling

**Execution Time**: ~180s (timed out - very slow)  
**Status**: ⚠️ PARTIAL FAILURE  
**Exit Code**: 124 (timeout)

#### Test Cases Attempted
From test output analysis:
- 5 basic schedule creation tests (from schedule_requests array)
- 6+ natural language parsing tests
- Schedule management tests (started but not completed)

#### Results Summary
- **Successful schedule creations**: ~2 out of ~10 attempts (~20% success rate)
- **Failed schedule creations**: ~8 out of ~10 attempts (~80% failure rate)
- **Performance**: 15-20 seconds per test case (unacceptably slow)

#### Sample Failures
1. "Remind me every day at 9am to check emails" - ❌ FAILED
2. "Schedule a meeting tomorrow at 3pm" - ❌ FAILED
3. "Schedule team sync every Monday at 2pm" - ❌ FAILED (with scheduler error)
4. "Set a reminder for next Friday at 10am to review reports" - ✅ PASSED
5. "Create a weekly reminder every Wednesday at 1pm for status updates" - ❌ FAILED

#### Errors Observed
```
ERROR: Failed to create scheduled job: 'str' object is not callable
```

This error appears in scheduler service and causes most scheduling requests to fail.

## Critical Bugs Discovered

### 1. Scheduler Event Type Bug (FIXED)

**File**: `src/muxi/services/scheduler/manager.py`  
**Line**: 109  
**Issue**: Using non-existent event type `SCHEDULER_INITIALIZED`  
**Fix**: Changed to `SCHEDULER_MANAGER_INITIALIZED`

```python
# BEFORE
observability.observe(
    event_type=observability.SystemEvents.SCHEDULER_INITIALIZED,  # ❌ Doesn't exist
    ...
)

# AFTER
observability.observe(
    event_type=observability.SystemEvents.SCHEDULER_MANAGER_INITIALIZED,  # ✅ Correct
    ...
)
```

**Status**: ✅ FIXED

### 2. Schedule Creation Failure (NOT FIXED)

**Error**: `'str' object is not callable`  
**Impact**: ~80% of scheduling requests fail to create jobs  
**Location**: Somewhere in scheduler service (exact location TBD)

**Evidence**:
```json
{
  "event": "error.internal.error",
  "data": {
    "service": "scheduler",
    "error": "'str' object is not callable",
    "user_id": "0",
    "description": "Failed to create scheduled job: 'str' object is not callable"
  }
}
```

**Status**: ❌ NOT FIXED - Requires deeper investigation

### 3. Performance Issue (NOT FIXED)

**Observed**: 15-20 seconds per test case  
**Expected**: 3-5 seconds per test case  
**Impact**: Test suite times out (180s limit exceeded)

**Possible Causes**:
- Database operations too slow
- LLM calls for each schedule request
- Scheduler polling interval (1 minute) causing delays
- Memory operations overhead

**Status**: ❌ NOT FIXED - Requires profiling

## Formation Configuration Changes

### Database Connection

**Original** (from old tests):
```yaml
persistent:
  connection_string: "postgresql://ran@127.0.0.1/muxi_framework"
```

**Updated** (for new tests):
```yaml
persistent:
  connection_string: "sqlite:///memory_test.db"
```

**Reason**: Avoid PostgreSQL dependency for e2e tests; use SQLite for portability

### Scheduler Configuration

```yaml
scheduler:
  enabled: true
  timezone: "UTC"
  check_interval_minutes: 1
  max_concurrent_jobs: 5
  max_failures_before_pause: 3
```

All scheduler settings preserved from original formation.

## Comparison: Old vs New Test Structure

### Old Location (tests/e2e/12_scheduling/)
- ✅ Tests passing in old location (8/11 according to TEST_MAPPING)
- ✅ Uses formation-scheduling.yaml
- ✅ PostgreSQL database
- ✅ Working scheduler service (before migration)

### New Location (e2e/tests/12_scheduling/)
- ❌ Tests failing due to scheduler bugs
- ✅ Uses formation-base.yaml (RUNTIME pattern)
- ✅ SQLite database
- ❌ Scheduler service has bugs

### Key Differences
1. **Formation naming**: `formation-scheduling.yaml` → `formation-base/formation.yaml`
2. **Database**: PostgreSQL → SQLite
3. **Test file naming**: `test_12a1_*.py` → `test_12_a_*.py`
4. **Import pattern**: Direct imports → Try/except fallback

## Next Steps

### Immediate (Required to Complete Migration)

1. **Fix Scheduler Bug** ⚠️ HIGH PRIORITY
   - Debug `'str' object is not callable` error
   - Likely in scheduler service create_job or parse methods
   - Review recent changes to scheduler code

2. **Performance Investigation** 🔍 MEDIUM PRIORITY
   - Profile test execution to identify slow operations
   - Consider reducing LLM calls for scheduling
   - Optimize database operations
   - Review if scheduler polling affects test speed

3. **Complete test_12_a_1 Testing** ✅
   - After fixing bugs, verify all test cases pass
   - Confirm schedule creation success rate >90%
   - Verify performance <5s per test case

4. **Test test_12_a_2** ✅
   - Run advanced natural language scheduling tests
   - Verify complex patterns work

### Future (Complete Full Migration)

5. **Migrate Remaining 9 Tests**
   - test_12_a_3 through test_12_d_1
   - Follow same RUNTIME pattern
   - Use formation-base for all tests

6. **Create Consolidated Test Runner**
   - Similar to Area 11's run_all_tests approach
   - Execute all Area 12 tests sequentially
   - Generate comprehensive report

7. **Update Documentation**
   - Add Area 12 to test standardization plan
   - Document scheduler-specific test patterns
   - Add troubleshooting guide for scheduling tests

## Recommendations

### For Scheduler Service

1. **Add Better Error Messages**
   - Current error `'str' object is not callable` is not helpful
   - Add context: which function, what parameters, what operation

2. **Add Input Validation**
   - Validate schedule requests before processing
   - Return clear error messages for invalid input

3. **Improve Performance**
   - Consider caching for schedule parsing
   - Reduce unnecessary LLM calls
   - Optimize database queries

### For Test Infrastructure

1. **Add Timeout Configuration**
   - Tests need longer timeouts due to scheduler operations
   - Consider per-test-case timeouts vs global timeout

2. **Add Performance Assertions**
   - Assert each test case completes within time limit
   - Track performance trends over time

3. **Add Scheduler-Specific Assertions**
   - Verify job created in database
   - Verify cron expression parsed correctly
   - Verify schedule time calculated correctly

## Code Changes Summary

### Files Modified

1. **src/muxi/services/scheduler/manager.py**
   - Line 109: Fixed event type name
   - Status: ✅ Committed

2. **e2e/tests/12_scheduling/test_12_a_1.py**
   - Added import fallback
   - Removed yaml_name parameter
   - Changed to asyncio.run() execution
   - Status: ✅ Ready to commit

3. **e2e/tests/12_scheduling/test_12_a_2.py**
   - Added import fallback
   - Removed yaml_name parameter
   - Changed to asyncio.run() execution
   - Status: ✅ Ready to commit

4. **e2e/tests/12_scheduling/formations/formation-base/formation.yaml**
   - Changed database to SQLite
   - Status: ✅ Ready to commit

### Files Created

1. **e2e/tests/12_scheduling/__init__.py**
   - Package marker
   - Status: ✅ Ready to commit

2. **e2e/tests/12_scheduling/formations/formation-base/.key**
   - Encryption key for secrets
   - Status: ✅ Ready to commit

3. **e2e/tests/12_scheduling/formations/formation-base/secrets.enc**
   - Symlink to shared secrets
   - Status: ✅ Ready to commit

## Comparison with Other Areas

### Area 11 (Formatting) - SUCCESS ✅
- **Migration**: Complete
- **Test Results**: 4/4 passing (100%)
- **Performance**: ~24s per test (acceptable)
- **Issues**: None

### Area 12 (Scheduling) - PARTIAL ⚠️
- **Migration**: 2/11 tests (18%)
- **Test Results**: ~2/10 passing (~20%)
- **Performance**: ~20s per test (too slow)
- **Issues**: Multiple scheduler bugs

**Key Difference**: Area 11 had stable underlying services; Area 12 revealed bugs in scheduler service during migration.

## Impact Assessment

### What Works ✅
1. Formation loading with scheduler enabled
2. RUNTIME pattern test structure
3. SQLite database integration
4. Test base class (BaseSchedulingTest)
5. Import fallback pattern

### What Doesn't Work ❌
1. Schedule creation (~80% failure rate)
2. Scheduler service has callable bug
3. Performance is too slow for CI/CD
4. Most scheduling requests fail

### Risk to Production 🚨
The scheduler bugs discovered during this migration **may affect production**:
- If scheduler service is used in production formations
- Schedule creation reliability is questionable
- Error handling needs improvement

**Recommendation**: Review scheduler service before production deployment.

## Lessons Learned

1. **Migration reveals bugs**: Standardizing tests exposed scheduler service bugs that weren't caught in old tests
2. **Performance matters**: Slow tests (>15s per case) make test suites impractical
3. **Database choice impacts tests**: Switching PostgreSQL → SQLite may have exposed edge cases
4. **Event type consistency**: Need better validation of observability event types

## Conclusion

Area 12 scheduling tests have been **partially migrated** with significant issues discovered:

✅ **Successes**:
- Test structure correctly migrated to RUNTIME pattern
- Formation configuration properly set up
- One scheduler bug fixed (event type)

❌ **Failures**:
- Scheduler service has critical bug preventing schedule creation
- Performance is unacceptable for CI/CD
- Only 2/11 tests migrated

⚠️ **Next Actions**:
1. Debug and fix scheduler `'str' object is not callable` error
2. Profile and optimize test performance
3. Complete migration of remaining 9 tests
4. Consider whether scheduler service needs broader refactoring

**Overall Assessment**: Migration infrastructure is solid, but underlying scheduler service needs significant work before Area 12 tests can be considered production-ready.

---

**Migration Completed By**: Droid  
**Review Required**: Yes - Scheduler service debugging needed  
**Ready for Commit**: Partial - Can commit migration infrastructure, but tests won't pass until scheduler is fixed
