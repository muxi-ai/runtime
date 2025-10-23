# API Test Suite Status

## Critical Fix Applied ✅

**API Key Schema Bug**: Formation server expects `admin_key`/`client_key` but formation.yaml had `admin`/`client`.

### Fix Details
- **File**: `e2e/tests/19_api/formation-api/formation.yaml`
- **Change**: 
  ```yaml
  # BEFORE (BROKEN):
  server:
    api_keys:
      admin: test-admin-key-123
      client: test-client-key-456
  
  # AFTER (WORKING):
  server:
    api_keys:
      admin_key: test-admin-key-123  # ← Added _key suffix
      client_key: test-client-key-456  # ← Added _key suffix
  ```
- **Root Cause**: Formation.py lines 1263-1276 look for `admin_key`/`client_key`, not `admin`/`client`
- **Impact**: All tests were getting 401 Unauthorized before this fix

## Test Status

### ✅ PASSING (3 tests)
1. **test_19a1_audit_logging.py** - Audit log GET/DELETE endpoints (6 test cases)
2. **test_19c1_scheduler_persistence.py** - Scheduler 422 response validation
3. **test_19d1_health_status.py** - Health/status endpoints (6 endpoints)
   - Fixed expectations: `/` returns "Up"/"Down" HTML (not "MUXI Formation API")
   - Fixed expectations: `/v1/status` returns `formation_status` object (not `status`)

### 🔧 NEEDS WORK (4 tests)
1. **test_19b1_sop_endpoints.py** - Timed out (not investigated)
2. **test_19e1_chat_streaming.py** - Fixed SSE parsing but needs LLM secrets
   - Fixed to match actual format: `{"token": "..."}` with `event: done`
   - NOT the complex format with `response.started`, `content.delta`, etc.
   - Requires `${{ secrets.OPENAI_API_KEY }}` to be properly configured
3. **test_19f1_agents_crud.py** - Failed (not investigated)
4. **test_19g1_memory_sessions.py** - Not tested yet

## Files Modified

### Staged for Commit (6 files):
```
M  e2e/tests/19_api/formation-api/formation.yaml    # API key schema fix
A  e2e/tests/19_api/TEST_INVENTORY.md               # Full endpoint inventory
A  e2e/tests/19_api/test_19d1_health_status.py      # Fixed & passing
A  e2e/tests/19_api/test_19e1_chat_streaming.py     # Fixed SSE parsing
A  e2e/tests/19_api/test_19f1_agents_crud.py        # Needs debugging
A  e2e/tests/19_api/test_19g1_memory_sessions.py    # Not tested
```

Total: 1,232 lines added

## Commit Blocker

**Droid Shield** is blocking commits due to test API keys in test files:
- Detected in: formation.yaml, test_19d1, test_19e1, test_19f1, test_19g1
- These are test-only keys: `test-admin-key-123` and `test-client-key-456`

### Solutions:
1. **User manual commit**: `git commit -m "..." --no-verify` (may still be blocked)
2. **Disable Droid Shield temporarily**: Run `/settings` in Factory
3. **Extract to separate file**: Move test keys to `.env` file (requires test refactor)

## Next Steps

### Immediate:
1. User manually commits changes (bypassing Droid Shield)
2. Debug test_19b1 (SOP endpoints timeout)
3. Debug test_19f1 (agents CRUD failure)
4. Test test_19g1 (memory/sessions)

### Short Term:
1. Configure secrets.enc with actual OpenAI API key for test_19e1
2. Or mock the LLM responses for chat streaming tests
3. Complete testing of all 4 new test files
4. Push to `api` branch

### Coverage Status:
- **Before**: 3/84 endpoints (3.6%)
- **Current Passing**: 6 health/status endpoints + audit + scheduler = ~15 endpoints
- **Target**: 24/84 endpoints (28.6%) when all 4 new tests pass

## Key Learnings

1. **API Response Formats Differ from Expectations**:
   - Health endpoint: Simple "Up"/"Down" HTML
   - Status endpoint: Complex `formation_status` object structure
   - Chat streaming: Simple `{"token": "..."}` format, not OpenAI-style events

2. **Formation YAML Schema is Strict**:
   - Must use exact field names (e.g., `admin_key` not `admin`)
   - Server silently generates random keys if schema is wrong
   - No validation errors, just 401 responses

3. **Test Infrastructure Works**:
   - httpx.AsyncClient handles SSE streams correctly
   - Formation startup/shutdown is reliable
   - Port cleanup with `lsof -ti:8271 | xargs kill -9` prevents hangs
