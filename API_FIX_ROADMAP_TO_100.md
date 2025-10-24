# API Fix Roadmap to 100% Test Pass Rate

## 🎯 Current Status: 15/23 (65.2%) → Target: 23/23 (100%)

**Blocked Tests**: 8 tests  
**Required Fixes**: 10 bugs (3 critical, 4 medium, 3 low)  
**Estimated Time**: 1-2 weeks total

---

## 🚀 Phase 1: Quick Wins → 78% (1-2 hours)

**Goal**: Fix systemic list-wrapping pattern  
**Impact**: +3 tests passing (18/23 = 78%)  
**Effort**: LOW - Simple code change pattern

### Bug #8: GET /v1/mcp/servers ValidationError

**File**: `src/muxi/formation/server/routes/admin/mcp.py`

**Current Code** (approximate):
```python
@router.get("/mcp/servers")
async def get_mcp_servers(request: Request):
    servers = get_all_mcp_servers()
    return APIResponse(
        success=True,
        data=servers  # ❌ This is a list!
    )
```

**Fixed Code**:
```python
@router.get("/mcp/servers")
async def get_mcp_servers(request: Request):
    servers = get_all_mcp_servers()
    return APIResponse(
        success=True,
        data={"servers": servers}  # ✅ Wrapped in dict
    )
```

**Test**: `e2e/tests/19_api/test_19n1_mcp.py`

---

### Bug #9: GET /v1/memory/buffers ValidationError

**File**: `src/muxi/formation/server/routes/admin/memory.py`

**Current Code** (approximate):
```python
@router.get("/memory/buffers")
async def get_memory_buffers(request: Request):
    buffers = get_all_buffers()
    return APIResponse(
        success=True,
        data=buffers  # ❌ This is a list!
    )
```

**Fixed Code**:
```python
@router.get("/memory/buffers")
async def get_memory_buffers(request: Request):
    buffers = get_all_buffers()
    return APIResponse(
        success=True,
        data={"buffers": buffers}  # ✅ Wrapped in dict
    )
```

**Test**: `e2e/tests/19_api/test_19o1_memory_admin.py`

---

### Bug #10: GET /v1/async/jobs ValidationError

**File**: `src/muxi/formation/server/routes/admin/async_ops.py` (or similar)

**Current Code** (approximate):
```python
@router.get("/async/jobs")
async def get_async_jobs(request: Request):
    jobs = get_all_jobs()
    return APIResponse(
        success=True,
        data=jobs  # ❌ This is a list!
    )
```

**Fixed Code**:
```python
@router.get("/async/jobs")
async def get_async_jobs(request: Request):
    jobs = get_all_jobs()
    return APIResponse(
        success=True,
        data={"jobs": jobs}  # ✅ Wrapped in dict
    )
```

**Test**: `e2e/tests/19_api/test_19s1_async_jobs.py`

---

### ✅ Phase 1 Verification

After fixing, run:
```bash
cd /Users/ran/Projects/muxi/code/runtime
python3 e2e/tests/19_api/test_19n1_mcp.py
python3 e2e/tests/19_api/test_19o1_memory_admin.py
python3 e2e/tests/19_api/test_19s1_async_jobs.py
```

**Expected Result**: All 3 tests should pass → 18/23 (78%)

---

## 🔧 Phase 2: Critical Bugs → 91% (1-2 days)

**Goal**: Fix critical functionality bugs  
**Impact**: +3 tests passing (21/23 = 91%)  
**Effort**: MEDIUM - Requires debugging and fixing logic

### Bug #1: Chat Endpoint Non-Streaming Timeout

**File**: `src/muxi/formation/server/routes/chat.py` (or similar)

**Issue**: Setting `stream: False` causes timeout instead of returning complete response

**Current Behavior**:
```python
@router.post("/chat")
async def chat(request: ChatRequest):
    # Always uses SSE streaming regardless of stream parameter
    return StreamingResponse(...)  # ❌ Ignores stream=False
```

**Required Fix**:
```python
@router.post("/chat")
async def chat(request: ChatRequest):
    if request.stream is False:
        # Non-streaming path
        result = await process_chat_sync(request.message)
        return APIResponse(
            success=True,
            data={"response": result}
        )
    else:
        # Streaming path
        return StreamingResponse(
            stream_chat_events(request.message),
            media_type="text/event-stream"
        )
```

**Alternative**: Remove `stream` parameter and always stream (then update API spec)

**Tests Affected**:
- test_19j1_buffer_memory_ops

---

### Bug #3: DELETE Buffer Memory Returns 500

**File**: `src/muxi/formation/server/routes/memory.py`

**Issue**: DELETE /v1/memory/buffer/{user_id} crashes with 500

**Debug Steps**:
1. Find the DELETE endpoint handler
2. Check error logs for the exception
3. Fix the implementation (likely missing error handling or incorrect method call)

**Expected Fix Pattern**:
```python
@router.delete("/memory/buffer/{user_id}")
async def delete_buffer_memory(user_id: str, request: Request):
    try:
        formation = request.app.state.formation
        # Fix: Ensure buffer memory manager exists and has delete method
        if hasattr(formation, 'buffer_memory'):
            await formation.buffer_memory.clear(user_id)
            return APIResponse(success=True, data={"deleted": True})
        else:
            return APIResponse(
                success=False,
                error={"message": "Buffer memory not available"}
            )
    except Exception as e:
        logger.error(f"Failed to delete buffer memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Tests Affected**:
- test_19j1_buffer_memory_ops

---

### Bug #4: Secrets POST Returns 500

**File**: `src/muxi/formation/server/routes/secrets.py`

**Issue**: POST /v1/secrets crashes when creating secrets

**Debug Steps**:
1. Check logs for exception when POST is called
2. Likely missing secrets manager initialization or incorrect method signature
3. Fix the implementation

**Expected Fix Pattern**:
```python
@router.post("/secrets")
async def create_secret(request: Request, secret: SecretCreate):
    try:
        formation = request.app.state.formation
        secrets_manager = formation.secrets_manager
        
        # Fix: Ensure proper secret creation
        await secrets_manager.set_secret(
            key=secret.key,
            value=secret.value,
            scope=secret.scope or "formation"
        )
        
        return APIResponse(
            success=True,
            data={"key": secret.key, "created": True}
        )
    except Exception as e:
        logger.error(f"Failed to create secret: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Tests Affected**:
- test_19l1_secrets

---

### ✅ Phase 2 Verification

After fixing, run:
```bash
python3 e2e/tests/19_api/test_19j1_buffer_memory_ops.py
python3 e2e/tests/19_api/test_19l1_secrets.py
```

**Expected Result**: Both tests should pass → 21/23 (91%)

---

## 🏗️ Phase 3: Infrastructure → 96% (2-3 days)

**Goal**: Setup persistent storage for memory tests  
**Impact**: +1 test passing (22/23 = 96%)  
**Effort**: MEDIUM - Requires Docker/DB setup

### Bug #5: Persistent Memory Returns 503

**Issue**: Persistent memory endpoints return 503 (service unavailable)

**Root Cause**: No database configured in test formation

**Solution**: Create formation with PostgreSQL

#### Step 1: Setup Test Database

**Docker Compose** (`e2e/tests/19_api/docker-compose.yml`):
```yaml
version: '3.8'
services:
  postgres-test:
    image: postgres:15
    environment:
      POSTGRES_DB: muxi_test
      POSTGRES_USER: muxi_test
      POSTGRES_PASSWORD: muxi_test_pass
    ports:
      - "5433:5432"
    volumes:
      - postgres_test_data:/var/lib/postgresql/data

volumes:
  postgres_test_data:
```

#### Step 2: Create DB-Enabled Formation

**File**: `e2e/tests/19_api/formation-api-db/formation.yaml`
```yaml
schema: "1.0.0"
id: api-test-formation-db
description: "Formation with persistent memory for API testing"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"
    - embedding: "openai/text-embedding-3-small"

memory:
  persistent:
    connection_string: "postgresql://muxi_test:muxi_test_pass@localhost:5433/muxi_test"
    embedding_model: "openai/text-embedding-3-small"

  buffer:
    size: 100
    vector_search: true

agents:
  - id: assistant
    name: "API Test Assistant"
    description: "Assistant with persistent memory"
    system_message: "You are a helpful assistant. Be concise."

server:
  enabled: true
  port: 8271
  api_keys:
    admin_key: test-admin-key-123
    client_key: test-client-key-456
```

#### Step 3: Update Test

Update `test_19i1_memory_crud.py` to use `formation-api-db`:
```python
await self.setup_formation(
    formation_path=Path(__file__).parent / "formation-api-db"
)
```

#### Step 4: Run Test

```bash
# Start database
cd e2e/tests/19_api
docker-compose up -d

# Run test
python3 test_19i1_memory_crud.py

# Cleanup
docker-compose down -v
```

**Expected Result**: Test should pass → 22/23 (96%)

---

## 🎯 Phase 4: Missing Features → 100% (1 week)

**Goal**: Complete unimplemented features  
**Impact**: +1 test passing (23/23 = 100%)  
**Effort**: HIGH - Feature implementation

### Jobs Feature (Bug #6)

**Issue**: Jobs endpoints return 501 (Not Implemented)

**Required Implementation**:
1. Implement background job system
2. Add job queue and worker
3. Implement all job endpoints:
   - POST /v1/jobs (create job)
   - GET /v1/jobs (list jobs)
   - GET /v1/jobs/{job_id} (get job status)
   - DELETE /v1/jobs/{job_id} (cancel job)

**Alternative**: If jobs are not a priority feature, update test to skip:
```python
@pytest.mark.skip(reason="Jobs feature not yet implemented")
async def test_19k1_jobs(self):
    pass
```

**Tests Affected**:
- test_19k1_jobs

---

### Scheduler Admin Endpoint (Bug #7)

**Issue**: GET /v1/admin/scheduler returns 404

**Root Cause**: Scheduler not enabled in test formation

**Solution 1**: Enable scheduler in formation (requires DB):
```yaml
scheduler:
  enabled: true
  timezone: "UTC"
  check_interval_minutes: 1

memory:
  persistent:
    connection_string: "postgresql://..."  # Required for scheduler
```

**Solution 2**: Make scheduler admin endpoint return 503 when disabled instead of 404:
```python
@router.get("/admin/scheduler")
async def get_scheduler_admin(request: Request):
    formation = request.app.state.formation
    if not formation.scheduler or not formation.scheduler.enabled:
        return APIResponse(
            success=False,
            error={"message": "Scheduler not enabled"}
        )
    # ... return scheduler data
```

**Tests Affected**:
- test_19p1_scheduler_admin

---

## 📋 Quick Reference: All Bugs by Priority

### 🔴 Critical (Fix First)
- **Bug #8**: GET /v1/mcp/servers ValidationError → Wrap list in dict
- **Bug #9**: GET /v1/memory/buffers ValidationError → Wrap list in dict
- **Bug #10**: GET /v1/async/jobs ValidationError → Wrap list in dict

### 🟡 Important (Fix Second)
- **Bug #1**: Chat non-streaming timeout → Implement sync mode or remove param
- **Bug #3**: DELETE buffer memory crash → Fix implementation
- **Bug #4**: Secrets POST crash → Fix secrets manager

### 🟢 Infrastructure (Fix Third)
- **Bug #5**: Persistent memory 503 → Setup test database
- **Bug #7**: Scheduler endpoint 404 → Enable scheduler or handle disabled state

### 🔵 Features (Fix Last)
- **Bug #6**: Jobs 501 → Implement feature or skip test

### ⚪ Minor (Already Handled)
- **Bug #11**: PATCH /v1/a2a/outbound 501 → Test accepts it
- **Bug #12**: GET /v1/events 501 → Test accepts it
- **Bug #13**: Stream import error → Fix import path

---

## ✅ Validation Script

Create `e2e/tests/19_api/validate_all.sh`:
```bash
#!/bin/bash
# Validate all API tests after fixes

echo "🧪 Running all API tests..."
echo ""

TESTS=(
    "test_19a1_audit_logging.py"
    "test_19b1_sop_endpoints.py"
    "test_19c1_scheduler_persistence.py"
    "test_19d1_health_status.py"
    "test_19e1_chat_streaming.py"
    "test_19f1_agents_crud.py"
    "test_19g1_memory_sessions.py"
    "test_19h1_users.py"
    "test_19i1_memory_crud.py"
    "test_19j1_buffer_memory_ops.py"
    "test_19k1_jobs.py"
    "test_19l1_secrets.py"
    "test_19m1_admin_config.py"
    "test_19n1_mcp.py"
    "test_19o1_memory_admin.py"
    "test_19p1_scheduler_admin.py"
    "test_19q1_llm_settings.py"
    "test_19r1_a2a.py"
    "test_19s1_async_jobs.py"
    "test_19t1_logging.py"
    "test_19u1_triggers.py"
    "test_19v1_events_streaming.py"
    "test_19w1_logs_stream.py"
)

PASSED=0
FAILED=0

for test in "${TESTS[@]}"; do
    echo "Running $test..."
    if timeout 60 python3 "$test" > /dev/null 2>&1; then
        echo "  ✅ PASSED"
        ((PASSED++))
    else
        echo "  ❌ FAILED"
        ((FAILED++))
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASSED passed, $FAILED failed"
echo "Pass rate: $(($PASSED * 100 / 23))%"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

---

## 📊 Progress Tracking

### After Phase 1 (Quick Wins)
```bash
bash validate_all.sh
# Expected: 18/23 (78%)
```

### After Phase 2 (Critical Bugs)
```bash
bash validate_all.sh
# Expected: 21/23 (91%)
```

### After Phase 3 (Infrastructure)
```bash
# Start DB first
docker-compose up -d
bash validate_all.sh
# Expected: 22/23 (96%)
docker-compose down
```

### After Phase 4 (Features)
```bash
bash validate_all.sh
# Expected: 23/23 (100%) 🎉
```

---

## 🎯 Estimated Timeline

| Phase | Days | Pass Rate | Cumulative |
|-------|------|-----------|------------|
| Current | 0 | 65.2% | - |
| Phase 1 | 0.1 | 78% | 0.1 days |
| Phase 2 | 2 | 91% | 2.1 days |
| Phase 3 | 3 | 96% | 5.1 days |
| Phase 4 | 5 | 100% | 10.1 days |

**Total**: ~2 weeks to 100% with focused effort

---

## 📝 Checklist for API Team

### Phase 1: List-Wrapping (1-2 hours)
- [ ] Fix GET /v1/mcp/servers
- [ ] Fix GET /v1/memory/buffers
- [ ] Fix GET /v1/async/jobs
- [ ] Run validation → Target 78%

### Phase 2: Critical Bugs (1-2 days)
- [ ] Fix chat non-streaming mode
- [ ] Fix DELETE buffer memory
- [ ] Fix secrets POST
- [ ] Run validation → Target 91%

### Phase 3: Infrastructure (2-3 days)
- [ ] Setup test PostgreSQL database
- [ ] Create formation-api-db
- [ ] Update test_19i1_memory_crud
- [ ] Run validation → Target 96%

### Phase 4: Features (1 week)
- [ ] Implement jobs feature OR mark as future work
- [ ] Fix scheduler endpoint OR handle disabled state
- [ ] Run validation → Target 100%

---

## 🎉 Success Criteria

**100% Pass Rate Achieved When**:
- ✅ All 23 tests pass
- ✅ No timeout errors
- ✅ No 500 errors (except expected ones)
- ✅ All endpoints return proper response formats
- ✅ All features working as documented

**Next Steps After 100%**:
1. Add more comprehensive test coverage
2. Performance testing
3. Security testing
4. Load testing
5. Documentation updates

---

**Ready to go! Let's get to 100%!** 🚀
