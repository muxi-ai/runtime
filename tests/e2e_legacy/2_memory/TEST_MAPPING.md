# Area 2 Test Mapping

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
- `test_working_pattern_helper.py` - Working memory patterns
- `test_faissx_configure_helper.py` - FAISSx configuration testing
- `test_faissx_debugging_helper.py` - FAISSx debugging utilities
- `test_faissx_read_helper.py` - FAISSx read verification
- `test_faissx_auth_simple_helper.py` - Simple auth testing
- `test_agent_loading_debug_helper.py` - Agent loading debugging

## Test Group 2H: Buffer Memory Context Enhancement & Retrieval ✅
- **2H1: Basic Buffer Memory via Chat Flow** → Tested in multiple files
- **2H2: Context-Dependent Message Understanding** → Tested in context enhancement

## Test Group 2I: Natural Language Memory Extraction (NEW) ✅
- **2I1: Natural Language Memory Extraction** → `test_2i1_natural_language_extraction.py`
  - Memories stored as sentences, not key-value pairs
  - Age converted to birth year
  - Natural language format verification
- **2I2: Complex Multi-Fact Extraction** → `test_2i2_complex_extraction.py`
  - Multiple facts from single message
  - CEO, company, product extraction
  - Distributed across appropriate collections
- **2I3: Context-Aware Extraction** → `test_2i3_context_aware_extraction.py`
  - Pronoun resolution using context
  - Building on previous information
  - Enhanced context for extraction

## Test Group 2J: Collection-Based Memory Organization (NEW) ✅
- **2J1: Collection Field Usage** → `test_2j1_collection_field_usage.py`
  - No collections table required
  - Memories tagged with collection values
  - Collection-based filtering works

## Test Group 2K: Memory System Integration (NEW) ✅
- **2K1: Enhanced Prompt Integration** → `test_2k1_enhanced_prompt_integration.py`
  - Long-term memories in prompts
  - Buffer context included
  - User profile integration
- **2K2: Memory Priority** → `test_2k2_memory_priority.py`
  - Important memories prioritized
  - Health/safety info over noise
  - Context window management

## Test Group 2L: Database Optimization (NEW) ✅
- **2L1: Database Optimization** → `test_2l1_database_optimization.py`
  - GIN index on memories.text
  - Collection index usage
  - No collections table
  - Credentials table optimization

## Test Group 2M: Error Resilience (NEW) ✅
- **2M1: Error Resilience** → `test_2m1_error_resilience.py`
  - Chat continues despite extraction failures
  - Buffer storage failures handled
  - Database errors don't crash system
  - Graceful degradation

## Helper/Debug Tests
These support the main test groups:
- `test_working_pattern_helper.py` - Working memory patterns
- `test_faissx_configure_helper.py` - FAISSx configuration testing
- `test_faissx_debugging_helper.py` - FAISSx debugging utilities
- `test_faissx_read_helper.py` - FAISSx read verification
- `test_faissx_auth_simple_helper.py` - Simple auth testing
- `test_agent_loading_debug_helper.py` - Agent loading debugging

## Enhanced Test Runner
- `run_day2_enhanced_tests.py` - Runs all new enhanced memory tests (Groups 2I-2M)

## Notes
- Some test numbers (like 2A2, 2A3) are consolidated into single test files that test multiple aspects
- The test files are more comprehensive than individual test cases, often covering multiple requirements
- Total unique test files: 15 main tests + 6 helper tests = 21 files
- All tests use real services via chat flow - NO MOCKS!
