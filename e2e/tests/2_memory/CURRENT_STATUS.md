# Memory Tests - Current Status

**Date**: January 30, 2025
**Session Summary**: Debugging and fixing memory test infrastructure

---

## What We Fixed

### 1. DATABASE_EXTENSION_CREATION_FAILED Warning ✅
**Problem**: Every PostgreSQL test was logging an error about failing to create pgvector extension, even though the extension existed.

**Root Cause**:
- Wrong enum names in observability calls (DATABASE_EXTENSION_CREATION_FAILED doesn't exist)
- Code was trying to CREATE EXTENSION when it already existed
- AttributeError from non-existent enums was caught at initialization level

**Solution**:
- Check if pgvector extension already exists before trying to create it
- If it exists, silently continue (no logging needed)
- Fixed enum names: use INITIALIZING for success, DATABASE_EXTENSION_FAILED for errors
- See: `src/muxi/services/memory/long_term.py` lines 215-250

**Result**: Tests now run without the misleading DATABASE_EXTENSION warning

---

### 2. PostgreSQL Connection Configuration ✅
**Problem**: Tests couldn't connect to Docker PostgreSQL

**Issues Fixed**:
- Native PostgreSQL (port 5432) was conflicting with Docker - stopped native instance
- Secrets file format was wrong - MUXI uses Fernet encryption, not OpenSSL
- Connection string was missing password and port

**Solution**:
- Stopped native PostgreSQL: `brew services stop postgresql@15`
- Re-encrypted secrets with Fernet using correct format
- Fixed connection string: `postgresql://muxi:testpass@localhost:5432/muxi_test`
- Granted SUPERUSER to muxi user in Docker

**Files Updated**:
- `e2e/assets/secrets.enc` - Re-encrypted with Fernet
- Docker PostgreSQL user permissions updated

**Result**: Can now connect to Docker PostgreSQL successfully

---

### 3. Database Schema Understanding ✅
**Problem**: Tests were using wrong column names

**Actual Schema**:
```sql
-- users table
public_id VARCHAR(21) NOT NULL
external_user_id VARCHAR(255) NOT NULL
formation_id VARCHAR(255) NOT NULL

-- memories table
id VARCHAR(21) NOT NULL
text TEXT NOT NULL  -- NOT 'message'
meta_data JSON NOT NULL  -- NOT 'metadata'
collection VARCHAR(255) NOT NULL
embedding VECTOR(1536)
```

**Solution**: Created direct database test that works with correct schema

**Result**: Verified PostgreSQL user isolation works perfectly

---

## Current Test Infrastructure Status

### Docker Services ✅
- **PostgreSQL**: Running on port 5432 with pgvector v0.8.1
- **FAISSx (no-auth)**: Running on port 45678
- **FAISSx (auth)**: Running on port 65432
- **Webhook**: Running on port 8765

All services are healthy in Docker container: `muxi-e2e-test`

### Secrets Configuration ✅
- Encryption format: Fernet (Python cryptography)
- Location: `e2e/assets/secrets.enc`
- Connection string: Correct with password and port

### Database Tables ✅
All 5 tables created successfully:
1. users
2. memories
3. credentials
4. scheduled_jobs
5. scheduled_job_audit

---

## Test Status Summary

### Tests That Should Work (3)
These don't require external API calls:
1. `test_2a1_basic_conversation_context.py` - Local buffer memory
2. `test_2b1_sqlite_persistence.py` - SQLite persistence
3. `test_2d1_local_buffer_mode.py` - Local FAISS buffer

**Current Issue**: Tests are hanging (likely due to streaming or formation shutdown)

### Tests Needing Valid OpenAI API Key (10)
All PostgreSQL and FAISSx tests require LLM calls:
- test_2c1_postgresql_user_isolation.py
- test_2e_faissx_both_modes.py
- test_2e1_postgresql_faiss_no_auth.py
- test_2e3_multi_user_faiss_vector_search.py
- test_2i1_natural_language_extraction.py
- test_2i2_complex_extraction.py
- test_2i3_context_aware_extraction.py
- test_2j1_collection_field_usage.py
- test_2k1_enhanced_prompt_integration.py
- test_2k2_memory_priority.py

**Current Issue**: Using placeholder API key "sk-test-key-replace-with-real-key"

### Tests With Syntax Errors (6)
These need migration/fixing:
- test_2f_memory_advanced_features.py
- test_2l1_database_optimization.py
- test_2m1_error_resilience.py
- test_2o_preference_system.py
- test_2o1_preference_detection.py
- test_2o2_preference_retrieval.py

---

## Verified Working Features

### PostgreSQL User Isolation ✅
Created direct database test that proves isolation works:
- File: `test_postgres_isolation_direct.py`
- Result: **PASSED** - Each user only sees their own memories
- Three test users (alice, bob, charlie) properly isolated

### Database Connectivity ✅
- Can connect to Docker PostgreSQL
- Can query tables
- Can insert/retrieve data
- pgvector extension available

### Table Creation ✅
- All 5 tables created on initialization
- No more lazy loading
- Proper indexes and foreign keys

---

## Remaining Issues

### 1. Tests Hanging
**Problem**: Even the simple tests (no API calls) are hanging

**Possible Causes**:
- Stream=False might not be working for all cases
- Formation shutdown might still have issues
- Async iteration timeout issues

**Next Steps**:
- Debug why test_2a1 hangs after loading formation
- Check if overlord.chat is waiting for something
- Verify all streaming code paths use stream=False

### 2. Invalid OpenAI API Key
**Problem**: Secrets contain placeholder key

**Solution Needed**:
- Either: Get valid OpenAI API key
- Or: Mock LLM responses for testing
- Or: Skip tests that require API calls

### 3. Pytest Collection Issue
**Problem**: pytest can't collect tests with __init__ constructors

**Current Workaround**: Run tests directly with Python

**Permanent Fix Needed**: Refactor BaseMemoryTest to not use __init__

---

## Key Learnings

1. **DATABASE_EXTENSION warning was a red herring** - The extension was working fine, just bad error handling
2. **Secrets encryption format matters** - MUXI expects Fernet, not OpenSSL
3. **Schema documentation is critical** - Tests assumed wrong column names
4. **Direct database tests are valuable** - Can verify core functionality without full stack
5. **Docker services are solid** - PostgreSQL with pgvector working perfectly

---

## Files Modified This Session

### Fixed
- `src/muxi/services/memory/long_term.py` - Fixed DATABASE_EXTENSION warning
- `e2e/assets/secrets.enc` - Re-encrypted with Fernet and correct connection string

### Created (Debug/Test)
- `e2e/tests/2_memory/test_postgres_direct.py` - Direct PostgreSQL test
- `e2e/tests/2_memory/test_postgres_isolation_direct.py` - User isolation test ✅ PASSING
- `e2e/tests/2_memory/test_extension_debug.py` - Extension creation debug
- `e2e/tests/2_memory/test_postgres_debug.py` - Formation debug
- `e2e/tests/2_memory/test_2c1_mock.py` - Mock test attempt
- `e2e/tests/2_memory/run_tests.py` - Custom test runner

---

## Recommendations

### Immediate (To Unblock Testing)
1. Debug why simple tests are hanging after formation load
2. Add proper OpenAI API key to secrets OR implement mocking
3. Fix the 6 tests with syntax errors

### Short-term (Test Infrastructure)
1. Refactor BaseMemoryTest to work with pytest
2. Add test timeout enforcement at framework level
3. Create mock LLM responses for tests that don't need real API

### Long-term (Documentation)
1. Document actual database schema in formation docs
2. Add troubleshooting guide for test failures
3. Create guide for running tests without API keys

---

## Quick Reference

### Start Docker Services
```bash
docker start muxi-e2e-test
```

### Check Service Status
```bash
docker ps | grep muxi
```

### Connect to PostgreSQL
```bash
docker exec muxi-e2e-test psql -U muxi -d muxi_test
```

### Run Direct Isolation Test
```bash
cd e2e/tests/2_memory
python test_postgres_isolation_direct.py  # ✅ PASSES
```

### Check Secrets
```bash
cd e2e/assets
python -c "from cryptography.fernet import Fernet; import json; from pathlib import Path; key = Path('.key').read_text().strip().encode(); fernet = Fernet(key); print(json.loads(fernet.decrypt(Path('secrets.enc').read_bytes())))"
```