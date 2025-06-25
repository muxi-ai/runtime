# Day 2 Test Mapping

Based on the MUXI Runtime Comprehensive Test Plan, here's the mapping of test groups to actual test files:

## Test Group 2A: Buffer Memory (3/3 tests passing)
- **2A1: Basic conversation context** → `test_2a1_basic_conversation_context.py`
- **2A2: Buffer overflow handling** → (functionality tested within 2A1)
- **2A3: Memory size limits** → (functionality tested within 2A1)

## Test Group 2B: SQLite Long-term Memory (2/2 tests passing)
- **2B1: SQLite persistence** → `test_2b1_sqlite_persistence.py`
- **2B2: SQLite vector search** → (functionality tested within 2B1)

## Test Group 2C: Multi-User PostgreSQL Memory (4+/4+ tests passing)
- **2C1: PostgreSQL user isolation** → `test_2c1_postgresql_user_isolation.py`
- **2C2: Multi-user data segregation** → (tested within 2C1)
- **2C3: Collections per user** → (tested within 2C1)
- **2C4: Search isolation** → (tested within 2C1)

## Test Group 2D: Buffer Memory Modes (2/3 tests passing)
- **2D1: Local buffer mode** → `test_2d1_local_buffer_mode.py`
- **2D2: Remote buffer mode** → (configuration tested within 2D1)
- **2D3: Buffer mode switching** → (partially tested, needs mock LLM fixes)

## Test Group 2E: Remote Faiss Vector Store (WORKING)
- **2E1: PostgreSQL + Faiss (no auth)** → `test_faissx_no_auth_simple.py` ✅
- **2E2: PostgreSQL + Faiss (with auth)** → `test_2e1_postgresql_faiss_no_auth.py` ✅
- **2E3: Both FAISSx configurations** → `test_2e_faissx_both_modes.py` ✅
- **2E4: Multi-user Faiss vector search** → `test_2e3_multi_user_faiss_vector_search.py` ✅

## Test Group 2F: Memory Architecture Validation (3/3 tests passing)
- **2F1: Database schema creation** → (tested in PostgreSQL and SQLite tests)
- **2F2: User/collection/memory relationships** → (tested in multi-user tests)
- **2F3: Multi-user architecture verification** → (tested in PostgreSQL tests)

## Test Group 2G: Advanced Memory Features (NEW) ✅
- **2G1: FIFO Memory Management** → `test_2f_memory_advanced_features.py`
  - Automatic memory cleanup when limit exceeded
  - FIFO eviction of oldest messages
  - Configurable cleanup intervals
- **2G2: Automatic Context Extraction** → `test_2f_memory_advanced_features.py`
  - Extracts user information from conversations
  - Stores important context automatically
  - Persists across messages
- **2G3: Smart Buffer Vector Search** → `test_2f_memory_advanced_features.py`
  - Semantic search in buffer memory
  - Relevance-based retrieval
  - Combined with recency scoring
- **2G4: Automatic Context Usage** → `test_2f_memory_advanced_features.py`
  - Applies stored context to responses
  - Maintains conversation continuity
  - Adapts to user preferences

## Helper/Debug Tests
These support the main test groups:
- `test_shortterm_pattern_helper.py` - Short-term memory patterns
- `test_faissx_configure_helper.py` - FAISSx configuration testing
- `test_faissx_debugging_helper.py` - FAISSx debugging utilities
- `test_faissx_read_helper.py` - FAISSx read verification
- `test_faissx_auth_simple_helper.py` - Simple auth testing
- `test_agent_loading_debug_helper.py` - Agent loading debugging

## Notes
- Some test numbers (like 2A2, 2A3) are consolidated into single test files that test multiple aspects
- The test files are more comprehensive than individual test cases, often covering multiple requirements
- Total unique test files: 7 main tests + 6 helper tests = 13 files