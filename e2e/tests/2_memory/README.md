# Area 2: Memory Tests

## Overview
Area 2 tests validate the three-tier memory architecture in MUXI Runtime:
- **Buffer Memory**: Short-term context with FIFO and vector search
- **Persistent Memory**: Long-term storage with PostgreSQL/SQLite
- **Vector Memory**: Semantic search with FAISSx integration

## Test Organization

### Pattern
All Area 2 tests follow **Pattern 2: Shared Directory** approach:
- Single shared formation directory: `formations/formation-memory/`
- Multiple YAML files for different memory configurations
- Tests inherit from `BaseMemoryTest` class
- Each test loads specific YAML configuration

### Test Categories

#### Core Memory Tests (Fully Migrated)
1. **Basic Operations** (2a1, 2b1, 2c1, 2d1)
   - Buffer memory configuration
   - SQLite persistence
   - PostgreSQL user isolation
   - Local vs remote buffer modes

#### Vector Search Tests (Templates Created)
2. **FAISSx Integration** (2e, 2e1, 2e3)
   - Authentication modes
   - PostgreSQL + FAISSx hybrid
   - Multi-user vector search

#### Advanced Features (Templates Created)
3. **Extraction & Collections** (2i1-2i3, 2j1)
   - Natural language extraction
   - Complex extraction patterns
   - Collection field usage

4. **Optimization & Resilience** (2k1-2k2, 2l1, 2m1)
   - Enhanced prompt integration
   - Memory priority
   - Database optimization
   - Error resilience

5. **Preference System** (2o, 2o1, 2o2)
   - Preference detection
   - Preference storage
   - Preference retrieval

## Formation Configurations

| Configuration | File | Purpose |
|--------------|------|---------|
| `basic` | formation-basic.yaml | Simple memory setup |
| `buffer_local` | formation-buffer-local.yaml | In-memory FAISS |
| `buffer_remote` | formation-buffer-remote.yaml | FAISSx server |
| `sqlite` | formation-sqlite.yaml | SQLite persistence |
| `postgres` | formation-postgres.yaml | PostgreSQL persistence |
| `postgres_faissx` | formation-postgres-and-faissx.yaml | Hybrid storage |
| `postgres_faissx_auth` | formation-postgres-and-faissx-with-auth.yaml | With authentication |
| `auto_extract` | formation-auto-extract.yaml | Auto-extraction |
| `memory_limits` | formation-memory-limits.yaml | Resource limits |

## Running Tests

### Individual Test
```bash
cd tests/e2e_new/2_memory
python test_2a1_basic_conversation_context.py
```

### All Memory Tests
```bash
pytest tests/e2e_new/2_memory/test_*.py -v
```

### With Required Services
```bash
# Start PostgreSQL
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=testpass postgres:15

# Start FAISSx (no auth)
faissx.server run --port 45678 &

# Start FAISSx (with auth)
faissx.server run --port 65432 --enable-auth --auth-file formations/faissx-auth.json &

# Run tests
pytest tests/e2e_new/2_memory/ -v
```

## Migration Status

### Summary (Updated: January 2025)
- **Total Tests**: 20 test files
- **Valid Tests**: 14 tests (runnable with proper structure)
- **Invalid Tests**: 6 tests (syntax errors, need migration)
- **Tests Passing**: 3/14 tests (21.4% pass rate)
- **Test Collection Issue**: Tests with __init__ constructors not collected by pytest

### Current Issues
1. **Pytest Collection Problem**: All test classes inherit from BaseMemoryTest which has __init__, preventing pytest collection
2. **Streaming Hang**: Tests using stream=True or async iteration were hanging (fixed by using stream=False)
3. **Formation Shutdown**: formation.shutdown() was calling os._exit() (fixed by using stop_overlord())
4. **Database Tables**: All 5 tables now created upfront (removed lazy loading)

### Root Cause Analysis: Why Tests Were Timing Out

The tests were timing out for three main reasons:

1. **Streaming Response Handling**:
   - Tests using `stream=True` were creating async generators
   - Without proper async iteration handling, tests would hang waiting for stream completion
   - Solution: Changed all tests to use `stream=False` for synchronous responses

2. **Formation Shutdown Issue**:
   - `formation.shutdown()` was calling `os._exit()` which abruptly terminates the process
   - This prevented proper test cleanup and made tests appear to hang
   - Solution: Use `stop_overlord()` instead for graceful shutdown

3. **Async Iterator Timeout**:
   - Some tests were iterating over async responses without timeout protection
   - If the response stream didn't complete, tests would hang indefinitely
   - Solution: Added `asyncio.wait_for()` wrappers with 10-second timeouts

### Test Status (Actual Results)
#### Passing Tests:
- ✅ test_2a1_basic_conversation_context.py
- ✅ test_2b1_sqlite_persistence.py
- ✅ test_2d1_local_buffer_mode.py (fixed streaming)

#### Failing Tests:
##### PostgreSQL Extension Error (DATABASE_EXTENSION_CREATION_FAILED):
- ❌ test_2c1_postgresql_user_isolation.py
- ❌ test_2i1_natural_language_extraction.py
- ❌ test_2i2_complex_extraction.py
- ❌ test_2i3_context_aware_extraction.py
- ❌ test_2j1_collection_field_usage.py
- ❌ test_2k1_enhanced_prompt_integration.py

##### Timeout Issues (FAISSx service not running):
- ❌ test_2e_faissx_both_modes.py (TIMEOUT 60s)
- ❌ test_2e1_postgresql_faiss_no_auth.py (TIMEOUT 60s)
- ❌ test_2e3_multi_user_faiss_vector_search.py (TIMEOUT 60s)
- ❌ test_2k2_memory_priority.py (TIMEOUT 60s)

#### Tests with Syntax Errors (need migration):
- ❌ test_2f_memory_advanced_features.py (IndentationError line 89)
- ❌ test_2l1_database_optimization.py (IndentationError line 2)
- ❌ test_2m1_error_resilience.py (IndentationError line 2)
- ❌ test_2o_preference_system.py (IndentationError line 2)
- ❌ test_2o1_preference_detection.py (IndentationError line 2)
- ❌ test_2o2_preference_retrieval.py (IndentationError line 2)

## Key Improvements from Migration

1. **Standardized Structure**: All tests follow same pattern
2. **Shared Base Class**: `BaseMemoryTest` reduces duplication
3. **Consistent Output**: Using `TestOutputFormatter`
4. **Proper Cleanup**: Automatic resource cleanup
5. **Better Organization**: Clear test categories
6. **Formation Reuse**: Single shared formation directory

## Next Steps

1. **Complete Logic Migration**: Fill in test logic for 15 template files
2. **Validate Tests**: Run full test suite with services
3. **Remove Old Tests**: Clean up original test files
4. **Update CI/CD**: Add new test paths to automation

## Notes

- Helper tests (`*_helper.py`) are debug utilities and have lower priority
- All tests require the shared `secrets.enc` and `.key` files
- Some tests require external services (PostgreSQL, FAISSx)
- Tests now use `sys.exit()` instead of `os._exit()` for proper cleanup

## Test Failure Analysis

### Issue 1: PostgreSQL Extension Not Installed
**Error**: `DATABASE_EXTENSION_CREATION_FAILED`
**Affected Tests**: 6 tests (43% of valid tests)
**Root Cause**: PostgreSQL needs the `vector` extension for pgvector functionality
**Solution**: Install pgvector extension in PostgreSQL:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Issue 2: FAISSx Service Not Running
**Error**: Tests timeout after 60 seconds
**Affected Tests**: 4 tests (29% of valid tests)
**Root Cause**: FAISSx server needs to be running on the expected ports
**Solution**: Start FAISSx services:
```bash
# No-auth server on port 45678
faissx.server run --port 45678 &

# Auth server on port 65432
faissx.server run --port 65432 --enable-auth --auth-file formations/faissx-auth.json &
```

### Issue 3: Test Infrastructure Issues
**Error**: Tests not collected by pytest
**Root Cause**: Test classes have __init__ constructors
**Solution**: Run tests directly with Python or refactor to remove __init__ from base class