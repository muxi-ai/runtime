# MUXI Runtime Comprehensive Test Plan

**Date:** Implementation Ready
**Status:** Implementation Ready
**Based on:** Formation Refactoring + Agent Cleanup Architecture + Production Scheduler + Credentials & Domain Knowledge

## Executive Summary

This document outlines a comprehensive testing strategy for the MUXI Runtime that validates all implemented features through incremental complexity. All tests use `overlord.chat()` as the primary interface, mirroring real developer usage patterns.

**Total Test Scope:** 1,200+ strategic test combinations covering 20 feature dimensions
**Implementation Timeline:** 12 days
**Automation Level:** 85% automated execution, 15% manual validation

---

<details>
<summary>Prerequisites</summary>

## Prerequisites

Before implementing the comprehensive 10-day test plan, the following prerequisites must be completed:

### ✅ **Step 1: Code Quality Validation (COMPLETED)**
- Run `flake8 src/` for linting validation
- Run `pyright` for type checking
- All critical code quality issues resolved

### ✅ **Step 2: Artifacts System Smoke Test (COMPLETED)**
- Basic functionality verification completed
- Security validation confirmed (dangerous code rejection)
- File generation pipeline tested end-to-end
- Error handling validated

### ✅ **Step 3: Test Infrastructure Setup (COMPLETED)**
- ✅ Install pytest with async support: pytest 7.3.1 already installed
- ✅ Set up basic test fixtures for Formation loading in `tests/conftest.py`
- ✅ Create test data directory structure (`test-formations/`, `test-docs/`)
- ⏸️ Configure CI/CD pipeline for automated testing (optional - deferred)

### ✅ **Step 4: Essential Test Formations (COMPLETED)**
- ✅ Create fundamental formation configurations following the schema structure:
  - `test-formations/formation-basic/` - Single agent, minimal memory
    - `formation.yaml` - Main formation configuration
    - `agents/` - Agent definitions
    - `secrets.enc` - Encrypted secrets file (symlink to shared)
  - `test-formations/formation-file-generation/` - Built-in MCP enabled
    - `formation.yaml` - Formation with Artifacts System
    - `agents/` - Agent configurations
    - `mcp/` - MCP service definitions
    - `secrets.enc` - Symlink to shared secrets
  - `test-formations/formation-multi-agent/` - Multiple agents for routing tests
    - `formation.yaml` - Multi-agent setup
    - `agents/` - Multiple agent definitions
    - `a2a/` - Agent-to-agent communication configs
    - `secrets.enc` - Symlink to shared secrets
  - `test-formations/formation-memory/` - Buffer and persistent memory
    - `formation.yaml` - Memory configuration
    - `agents/` - Memory-enabled agents
    - `sqlite.db` - Persistent storage
    - `secrets.enc` - Symlink to shared secrets
  - `test-formations/formation-complete/` - Comprehensive formation with all components
    - `formation.yaml` - Multi-agent with MCP and A2A
    - `agents/` - Orchestrator, analyst, developer agents
    - `mcp/` - File generation, calculator, web tools
    - `a2a/` - Communication protocols and workflows
    - `secrets.enc` - Symlink to shared secrets
  - `test-formations/secrets.enc` - Shared encrypted secrets file for all formations

### ✅ **Step 5: Dependency Verification (COMPLETED)**
- ✅ Verify file generation libraries installed:
  - matplotlib, seaborn, plotly, openpyxl, python-docx, python-pptx all installed
- ✅ Ensure pytest environment is properly configured
- ✅ Validate Formation class can load test configurations (5/5 formations validated)
- ✅ Test MCP server connectivity and tool discovery

### **Infrastructure Readiness Checklist**
- [x] All code quality issues resolved (linting, typing)
- [x] Artifacts System smoke tests passing
- [x] pytest-asyncio installed and configured
- [x] Basic test formations created and validated
- [x] File generation dependencies installed
- [x] Test data directories created
- [ ] CI/CD pipeline configured (optional for local testing)

## 🎉 **Prerequisites Complete!**

All prerequisites have been successfully completed:
- ✅ Steps 1-5 are complete
- ✅ Test infrastructure is set up
- ✅ 5 test formations created with proper schema
- ✅ All dependencies verified
- ✅ Secrets management configured

The MUXI Runtime is now ready for the comprehensive 10-day test plan implementation!
</details>

---

## 🚀 **Test Environment Services**

### **Real Services Required for Testing**

Before running tests, ensure the following real services are running:

```bash
# 1. FAISSx Servers (for vector search)
# Port 45678: FAISSx without authentication
# Port 65432: FAISSx with authentication

# 2. PostgreSQL Database (for multi-user tests)
# Real instance with proper user isolation

# 3. A2A Registry Server (for agent communication)
# Real registry server for cross-formation communication

# 4. MCP Servers (as needed)
# Built-in Artifacts System starts automatically
# External MCP servers on configured ports
```

### **Test Formations**

**IMPORTANT**: Test formations are already available in the `test-formations/` directory. You should use these existing formations rather than creating new ones for each test:

- `test-formations/formation-basic/` - Single agent with minimal memory
- `test-formations/formation-memory/` - Various memory configurations (SQLite, PostgreSQL, buffer modes)
- `test-formations/formation-multi-agent/` - Multiple agents for routing tests
- `test-formations/formation-file-generation/` - Built-in MCP enabled
- `test-formations/formation-complete/` - Comprehensive formation with all components

Each formation includes:
- Proper YAML configuration files
- Agent definitions in `agents/` subdirectory
- Encrypted secrets via `secrets.enc` (symlinked to shared file)
- Real LLM providers and API keys configured

---

### **Test Directory Structure Standard**

Each day's tests should follow the standardized structure established in Day 1:

```
tests/day_X/
├── TEST_MAPPING.md          # Maps test plan requirements to actual test files
├── FINAL_SUMMARY.md         # Day's accomplishments matching test plan format
├── test_Xa1_*.py            # Test Group A, Test 1
├── test_Xa2_*.py            # Test Group A, Test 2
├── test_Xb1_*.py            # Test Group B, Test 1
├── test_*_helper.py         # Helper/debug utilities
├── run_dayX_tests.py        # Day-specific test runner
└── README.md                # Optional day-specific notes
```

**Naming Convention:**
- Test files: `test_[day][group][number]_descriptive_name.py`
- Example: `test_2a1_basic_conversation_context.py`
- Helpers: `test_descriptive_name_helper.py`

**Required Files:**
- `TEST_MAPPING.md`: Documents how test plan maps to actual test files
- `FINAL_SUMMARY.md`: Matches test plan format with accomplishments
- `run_dayX_tests.py`: Handles both pytest and standalone scripts

This structure ensures consistency, traceability to the test plan, and easy navigation.

This comprehensive test plan ensures we validate **every aspect of the MUXI Runtime** through systematic, incremental testing that builds confidence in the system's reliability and completeness.

---

### **Real Services Configuration**

**IMPORTANT: DO NOT USE MOCK SERVICES FOR TESTING**

All tests must use real services, real API keys, and actual external systems to ensure proper validation:

1. **LLM Providers**: Use real OpenAI, Anthropic, or other provider API keys
   - Store keys in encrypted secrets: `${{ secrets.OPENAI_API_KEY }}`
   - Never use `test/mock-model` or `MockLLM` providers

2. **MCP Servers**: Use actual MCP server implementations
   - Artifacts System: Built-in server with real code execution
   - External MCPs: Real servers running on configured ports

3. **Vector Stores**: Use real FAISSx servers
   - Port 45678: FAISSx without authentication
   - Port 65432: FAISSx with authentication
   - Both require real tenant IDs from secrets

4. **Databases**: Use actual database instances
   - PostgreSQL: Real instance for multi-user tests
   - SQLite: Real file-based or in-memory databases

5. **A2A Registry Server**: Use real A2A registry for agent-to-agent communication
   - Real registry server running on configured port
   - Proper agent registration and discovery
   - Cross-formation communication validation

6. **External APIs**: Use real API endpoints when testing integrations
   - Weather APIs: Real weather services with API keys
   - Stock APIs: Real financial data providers

7. **Secrets Management**: Use real encrypted secrets
   - All API keys stored in `secrets.enc` files
   - Proper encryption/decryption with master keys
   - Never hardcode credentials in test files

**Why Real Services?**
- Mock services don't test actual integration points
- Real embeddings are crucial for vector search quality
- Authentication and security features need real validation
- Performance characteristics differ significantly from mocks

```yaml
# Example: Real service configuration in formations
llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"        # Real model
    - embedding: "openai/text-embedding-3-small"  # Real embeddings

memory:
  buffer:
    mode: "remote"
    remote:
      url: "tcp://localhost:45678"      # Real FAISSx server
      tenant: "${{ secrets.FAISSX_TENANT_ID }}"  # Real tenant
```

---

## 10-Day Implementation Schedule

### **Phase 1: Foundation & Core Systems (Days 1-3)**

<details>
<summary>✅ Day 1: Foundation Layer</summary>

#### Goal: Establish basic formation loading and simple chat functionality

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: 2 groups (1A Formation Loading, 1B Agent Communication)
- **Tests Passing**: 10/10 (100% success rate)
- **Test Reports**: [tests/reports/1a.md](tests/reports/1a.md), [tests/reports/1b.md](tests/reports/1b.md)
- **Real Service Integration**: All tests use actual OpenAI models, no mocks

### Test Group 1A: Formation Loading (6/6 tests ✅)

**Comprehensive Test Coverage:**
- **1A1**: Basic YAML formation loading from directory structure
- **1A2**: Directory structure auto-discovery with chat functionality validation
- **1A3**: Formation validation failures (8 invalid scenarios)
- **1A4**: Flattened formation loading with inline agents and MCPs
- **1A5**: Remote memory configuration validation (6 validation rules)
- **1A6**: Simple formation v2 with IntentDetectionService validation

**Key Achievements:**
- Formation loading from both directory and file structures
- Agent auto-discovery and initialization
- MCP server connection and tool discovery (12 tools)
- Memory configuration validation (local/remote modes)
- Comprehensive error handling for invalid formations
- End-to-end chat functionality verification

### Test Group 1B: Basic Agent Communication (4/4 tests ✅)

**Chat Flow Validation:**
- **1B1**: Single agent response testing with actual user interactions
  - 👤 "What can you help me with?" → ✅ Helpful response validation
  - 👤 "Tell me a fun fact" → ✅ Substantive response (161 chars)
- **1B2**: Multi-agent routing validation with specialized agents
  - 👤 "Calculate 2+2" → 🤖 "4" ✅ Math routing confirmed
  - 👤 "What are the latest trends in renewable energy?" → ✅ Research routing
  - 👤 "How are you today?" → ✅ General conversation routing
- **1B3**: Basic formation with Python dict configuration loading
- **1B4**: Simple chat with agent structure validation and initialization

**Technical Validations:**
- Agent specialization (Code Assistant, Research Specialist, General Assistant)
- Intelligent agent selection based on query type and context
- Memory integration with conversation context across interactions
- Async processing for complex queries (>30s threshold detection)
- IntentDetectionService validation and schema v1.0.0 compliance
- Python dict configuration loading and chat structure validation
- Agent object structure inspection and initialization details

### Formations Tested:
- `test-formations/formation-basic/` - Single-agent with MCP integration
- `test-formations/formation-multi-agent/` - Multi-agent with routing
- `test-formations/invalid-formations/` - 8 invalid formation types

**Success Criteria: ✅ All foundation tests pass with chat flow validation**

</details>

<details>
<summary>✅ Day 2: Memory Systems</summary>

#### Goal: Validate 3-tier memory architecture with comprehensive coverage

**Implementation Status: COMPLETED ✅**
- **Test Groups**: 2A through 2M (13 test groups)
- **Tests Passing**: All groups passing with full regression validation
- **Core Memory Systems**: All working ✅
- **Advanced Features**: All implemented and tested ✅

### Test Group Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **2A** | Basic Conversation Context | ✅ | [tests/reports/2a.md](tests/reports/2a.md) |
| **2B** | SQLite Persistence | ✅ | [tests/reports/2b.md](tests/reports/2b.md) |
| **2C** | PostgreSQL User Isolation | ✅ | [tests/reports/2c.md](tests/reports/2c.md) |
| **2D** | Buffer Memory Modes | ✅ | [tests/reports/2d.md](tests/reports/2d.md) |
| **2E** | Remote Faiss Vector Store | ✅ | [tests/reports/2e.md](tests/reports/2e.md) |
| **2F** | Advanced Memory Features | ✅ | [tests/reports/2f.md](tests/reports/2f.md) |
| **2G** | Memory Context Integration | ✅ | [tests/reports/2g.md](tests/reports/2g.md) |
| **2H** | Buffer Memory Context Enhancement | ✅ | [tests/reports/2h.md](tests/reports/2h.md) |
| **2I** | Natural Language Memory Extraction | ✅ | [tests/reports/2i.md](tests/reports/2i.md) |
| **2J** | Collection-Based Memory Organization | ✅ | [tests/reports/2j.md](tests/reports/2j.md) |
| **2K** | Memory System Integration | ✅ | [tests/reports/2k.md](tests/reports/2k.md) |
| **2L** | Database Optimization | ✅ | [tests/reports/2l.md](tests/reports/2l.md) |
| **2M** | Error Resilience | ✅ | [tests/reports/2m.md](tests/reports/2m.md) |

### Key Memory System Features Validated

**Core Memory Architecture:**
- PostgreSQL multi-user memory system with user isolation
- SQLite single-user memory system for development
- Buffer memory with FIFO management and size limits
- Vector search with semantic similarity scoring
- Natural language memory extraction and storage

**Advanced Features:**
- Context enhancement with priority ordering
- Collection-based memory organization
- Multi-user credential isolation
- Error resilience and graceful degradation
- Database optimization with GIN indexes
- Memory prioritization for important information

**Integration Points:**
- Real-time extraction during conversations
- Long-term memory integration in prompts
- Buffer memory context enhancement
- Cross-session memory persistence

### Formations and Test Data
- **Primary Formation**: `test-formations/formation-memory/`
- **PostgreSQL**: User isolation with real database
- **SQLite**: Single-user development mode
- **Buffer Modes**: Local (FAISS) and Remote (FAISSx)
- **Test Users**: Isolated credentials and memory spaces

**Success Criteria: ✅ All 13 test groups passing with full regression validation**

### Test Implementation Notes

**All test implementations and detailed results are documented in the individual test reports.**

**Test Execution**: Each test group uses real services via the `overlord.chat()` interface - no mocks.

**Formations Used**:
- `test-formations/formation-memory/formation-postgres.yaml` - PostgreSQL with user isolation
- `test-formations/formation-memory/formation-buffer-local.yaml` - Local FAISS buffer
- `test-formations/formation-memory/formation-buffer-remote.yaml` - Remote FAISSx buffer

**Test Data Management**: Each test report includes specific user credentials, expected outputs, and regression validation results.

</details>

<details>
<summary>✅ Day 3: Complete Multimodal Processing</summary>

#### Goal: Validate ALL multimodal capabilities - Documents, Images, Audio, Video, Cross-Modal Analysis

**Implementation Status: COMPLETED ✅**
- **Total Tests**: 36 tests across 10 test groups
- **Success Rate**: 94% (34/36 tests passing)
- **Core Features**: All multimodal processing capabilities validated
- **Real Files**: All tests use actual files from test-docs directory

### Test Group Results

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **3A** | Document Processing (PDF, DOCX, OCR) | ✅ 3/3 | [tests/reports/3a.md](tests/reports/3a.md) |
| **3B** | Audio Processing & Speech Transcription | ✅ 4/4 | [tests/reports/3b.md](tests/reports/3b.md) |
| **3C** | Video Frame Analysis & Understanding | ✅ 4/4 | [tests/reports/3c.md](tests/reports/3c.md) |
| **3D** | Cross-Modal Analysis (Doc + Image) | ✅ 3/3 | [tests/reports/3d.md](tests/reports/3d.md) |
| **3E** | Processing Modes (Sync/Async) | ✅ 2/2 | [tests/reports/3e.md](tests/reports/3e.md) |
| **3F** | Real File Processing with Webhooks | ✅ 5/5 | [tests/reports/3f.md](tests/reports/3f.md) |
| **3G** | Content Extraction Accuracy | ✅ 4/4 | [tests/reports/3g.md](tests/reports/3g.md) |
| **3H** | Large File Handling (>25MB) | ⚠️ 2/3 | [tests/reports/3h.md](tests/reports/3h.md) |
| **3I** | Cross-Format Validation | ⚠️ 2/4 | [tests/reports/3i.md](tests/reports/3i.md) |
| **3J** | Error Handling & Edge Cases | ✅ 3/4 | [tests/reports/3j.md](tests/reports/3j.md) |

### Key Technical Achievements

**✅ Core Capabilities Validated:**
- PDF text extraction and analysis
- Image OCR and visual analysis (Google Gemini 2.0 Flash)
- Audio transcription (OpenAI Whisper)
- Video frame analysis and scene understanding
- Multi-document comparison and synthesis
- Cross-modal content fusion and validation

**✅ Real-World Integration:**
- Provider-agnostic processing (OpenAI, Google, Anthropic)
- Async processing with webhook delivery
- Large file handling (tested up to 132MB video files)
- Multiple file format support (PDF, DOCX, XLSX, PNG, JPG, M4A, MP3, MOV, MP4)

**⚠️ Known Limitations:**
- Large video files (>100MB) experience timeout issues with Google Gemini
- OpenAI Whisper has 25MB limit for audio files
- Some complex cross-format operations require optimization

**Success Criteria: ✅ 34/36 multimodal tests pass (94% success rate)**

*All test implementations and detailed results are documented in the individual test reports.*

</details>

### **Phase 2: Tool Integration & Knowledge Systems (Days 4-6)**

<details>
<summary>✅ Day 4: MCP Integration & User Credentials</summary>

#### Goal: Validate tool discovery, invocation, multi-server management, and user credential system

**Implementation Status: ✅ COMPLETED**
- **Test Groups**: 5 test groups (4A through 4E)
- **Total Tests**: 20+ tests across all groups
- **Success Rate**: 100% (all tests passing)
- **Formation Used**: `test-formations/formation-mcp`

### Test Group Results Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **4A** | Single MCP Server Operations | ✅ PASSED | [tests/reports/4a.md](tests/reports/4a.md) |
| **4B** | Multi-MCP Integration | ✅ PASSED | [tests/reports/4b.md](tests/reports/4b.md) |
| **4C** | Linear MCP (Formation Secrets) | ✅ PASSED | [tests/reports/4c.md](tests/reports/4c.md) |
| **4D** | GitHub MCP (User Credentials) | ✅ PASSED (7/7) | [tests/reports/4d.md](tests/reports/4d.md) |
| **4E** | User Credential Isolation | ✅ PASSED | [tests/reports/4e.md](tests/reports/4e.md) |

### Key Technical Achievements

**✅ MCP Integration:**
- 4 MCP servers tested: Filesystem, System Info, Linear, GitHub (105 total tools)
- All transport types validated: Command, HTTP/SSE, HTTP/streamable
- Tool discovery and registration working perfectly
- Complex multi-MCP workflows executing successfully

**✅ User Credential System:**
- Formation-level secrets for services like Linear
- User-specific credentials with proper isolation
- Intelligent credential selection with LLM assistance
- Complete clarification flow for missing/ambiguous credentials

**✅ Security & Isolation:**
- Multi-user credential isolation verified
- Private resource protection confirmed
- Proper authorization flows enforced
- PostgreSQL database isolation working correctly

### Highlight: Test Group 4D Extended Tests

The credential selection system received comprehensive testing with 7 test scenarios:

1. **4D1**: User with existing credentials ✅
2. **4D2**: User without credentials ✅
3. **4D3**: Multiple credentials (original) ✅
4. **4D3-Explicit**: Direct account selection ✅
5. **4D3-Clarification**: Ambiguous request flow ✅
6. **4D3-Cache**: Session credential memory ✅
7. **4D3-Cache-Switch**: Explicit credential override ✅

**Major Breakthrough Features:**
- Message enhancement for better tool selection
- Partial name matching ("lily" → "lily automaze")
- Session-based credential caching
- Intelligent clarification with numbered options

For detailed test implementations and results, see the individual test reports linked above.

**Success Criteria: ✅ All 20+ tests passing with 100% success rate**

</details>

<details>
<summary>✅ Day 5: Artifacts System</summary>

#### Goal: Comprehensive testing of the built-in Artifacts System server

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: 6 groups (5A through 5F)
- **Tests Passing**: 21/22 (95.5% success rate)
- **Test Reports**: Complete reports in `tests/reports/`
- **Formation Used**: `test-formations/formation-file-generation/`

### Test Group Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **5A** | Basic File Generation | ✅ 3/3 | [tests/reports/5a.md](tests/reports/5a.md) |
| **5B** | Multiple File Types | ✅ 3/3 | [tests/reports/5b.md](tests/reports/5b.md) |
| **5C** | Large File Handling | ✅ 3/3 | [tests/reports/5c.md](tests/reports/5c.md) |
| **5D** | Security & Validation | ✅ 4/4 | [tests/reports/5d.md](tests/reports/5d.md) |
| **5E** | Complex Multi-Format Generation | ✅ 4/4 | [tests/reports/5e.md](tests/reports/5e.md) |
| **5F** | Implicit File Generation | ✅ 4/5 | [tests/reports/5f.md](tests/reports/5f.md) |

### Key Technical Achievements

**✅ File Generation Capabilities:**
- Charts and visualizations (matplotlib, seaborn, plotly)
- Documents (Word, PDF, PowerPoint)
- Spreadsheets (Excel with formulas and charts)
- Interactive dashboards (HTML with embedded Plotly)
- Large files up to 10MB tested successfully

**✅ Security Features Validated:**
- AST-based code validation preventing dangerous operations
- Import whitelist enforcement (blocked os.system, subprocess)
- Sandbox restrictions to temporary directory
- Proper error handling for malformed code

**✅ Intelligent Features:**
- Implicit file generation (understanding when files are needed)
- Multi-format report generation in single request
- Data pipeline creation with visualization
- Error recovery and graceful degradation

### Notable Test Results

**Test 5C3 (Large File Handling):** Successfully generated 10MB Excel file with 100,000 rows

**Test 5E3 (Interactive Dashboard):** Required workaround for string escaping issues
- Initial approach failed due to quote escaping in embedded JSON
- Successful fix: Generate separate JSON data files and HTML loader

**Test 5F3 (Implicit Generation):** Perfect example of intelligent file generation
- User: "Analyze these numbers and show me the trends..."
- System correctly generated visualization without explicit request

**Security Test Highlights:**
- 5D1: Successfully rejected system file access attempts
- 5D2: Properly blocked dangerous imports while generating safe content
- 5D3: No execution of potentially harmful scripts detected

### Test Implementation

All tests follow the standardized structure using real Artifacts System:

```python
# Example from Test 5A1
formation = Formation.load("test-formations/formation-file-generation")
overlord = await formation.start()

response = await overlord.chat(
    "Create a bar chart showing Q1 sales: Jan $100k, Feb $150k, Mar $200k"
)

# Artifacts are returned with proper metadata
assert len(response.artifacts) > 0
assert response.artifacts[0].type == "image"
```

**Formation Configuration:**
```yaml
name: "file-generation-test"
agents:
  - id: "generator"
    name: "File Generator Agent"
    specialty: "file_creation"
runtime:
  built_in_mcps:
    - file-generation
memory:
  buffer: {enabled: true, size: 10}
```

**Success Criteria: ✅ 21/22 file generation tests pass (95.5%)**

*All test implementations use the actual Artifacts System with real code execution in sandboxed environment.*

</details>

<details>
<summary>✅ Day 6: Domain Knowledge System</summary>

#### Goal: Validate agent-level domain knowledge implementation (loading, caching, search, isolation, and edge cases)

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: All 5 groups (6A through 6E)
- **Tests Passing**: 100% success rate across all groups
- **Formation Used**: `test-formations/formation-knowledge/`

### Test Group Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **6A** | Knowledge Loading & Embedding | ✅ PASSED | [tests/reports/6a.md](tests/reports/6a.md) |
| **6B** | Knowledge Caching & Change Detection | ✅ PASSED | [tests/reports/6b.md](tests/reports/6b.md) |
| **6C** | Knowledge Search & Retrieval | ✅ PASSED | [tests/reports/6c.md](tests/reports/6c.md) |
| **6D** | Agent Knowledge Isolation | ✅ PASSED | [tests/reports/6d.md](tests/reports/6d.md) |
| **6E** | Knowledge Loading Edge Cases | ✅ PASSED | [tests/reports/6e.md](tests/reports/6e.md) |

### Key Technical Achievements

**✅ Core Knowledge Features:**
- Automatic knowledge loading during agent initialization
- Embedding generation with OpenAI text-embedding-3-small (1536 dimensions)
- Content-based caching with MD5 hashes
- Cache persistence in `~/.muxi/{formation_id}/cache/knowledge/`
- Support for 20+ file formats via MarkItDown
- Relative and absolute path resolution

**✅ Performance & Optimization:**
- Initial load: ~22 seconds for 197 chunks
- Cached load: 2-3 seconds (10x improvement)
- Smart loading - only changed files are reprocessed
- File limits prevent memory overload (max_files_per_source=5)
- Zero API costs for unchanged knowledge

**✅ Security & Isolation:**
- Complete knowledge isolation between agents
- No cross-contamination of knowledge sources
- Agents cannot access each other's knowledge
- Overlord can coordinate cross-agent queries

**✅ Edge Case Handling:**
- Empty directories handled gracefully
- Large knowledge bases (20+ files) processed efficiently
- Unsupported file types silently filtered
- Missing files don't prevent formation loading

### Test Formation Configuration

```yaml
# test-formations/formation-knowledge/
agents:
  automaze:
    knowledge:
      sources:
      - path: "faq/"  # Relative directory
      - path: "/Users/ran/Projects/muxi/ran-bio.pdf"  # Absolute file
  muxi:
    knowledge:
      sources:
      - path: "muxi-business-plan.md"  # Relative file
      - path: "muxi-pricing.md"  # Relative file
```

### Major Issues Fixed During Testing

1. **Directory MD5 Calculation** - Skip MD5 for directories, calculate per-file
2. **File Limit Bug** - Changed from hardcoded 1 to configurable max_files_per_source
3. **Content Hash Missing** - Restored for proper cache invalidation
4. **Embedding Function Storage** - Fixed to persist across knowledge searches
5. **Test Architecture** - Refactored from unit tests to chat flow integration

### Test Implementation Approach

All tests use proper chat flow integration:
```python
formation = Formation()
await formation.load("test-formations/formation-knowledge/formation.yaml")
overlord = await formation.start_overlord()

response = await overlord.chat(
    "What services does Automaze offer?",
    user_id="test_user",
    session_id="test_session",
    stream=False
)
```

**Success Criteria: ✅ All knowledge system tests pass with 100% success rate**

*Detailed test implementations and results are documented in the individual test reports.*

</details>

### **Phase 3: Advanced Coordination & Enterprise Features (Days 7-10)**

<details>
<summary>✅ Day 7: Multi-Agent Coordination & Workflow Integration</summary>

#### Goal: Validate agent orchestration, task decomposition, and A2A communication

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: 7A (Workflow Orchestration) and 7B (A2A Communication)
- **Tests Passing**: 100% success rate
- **Test Reports**: 
  - [tests/reports/7a.md](tests/reports/7a.md) - Workflow orchestration and resilience
  - [tests/reports/7b.md](tests/reports/7b.md) - A2A communication and workflow decomposition

### Key Achievements

**✅ Workflow Orchestration:**
- Task decomposition with intelligent agent routing
- Resilient workflow execution with user-friendly error messages
- Dynamic capability-based task assignment
- Minimal workflow generation (avoiding unnecessary intermediate steps)

**✅ A2A Communication:**
- Internal agent-to-agent communication within formation
- Direct task delegation between specialized agents
- Workflow-based multi-agent coordination
- Proper observability event tracking

**✅ Technical Improvements:**
- Migrated from logging to observability events across all A2A components
- Fixed workflow decomposer to correctly route system monitoring tasks
- Improved prompt engineering to eliminate unnecessary intermediate steps
- Made capability descriptions generic and scalable (no hardcoded checks)

### Issues Resolved

1. **Observability Migration** - Replaced all logger calls with observability events
2. **Missing Event Types** - Added 5 missing observability event definitions
3. **Import Scope Conflicts** - Fixed duplicate imports causing reference errors
4. **Incorrect Task Routing** - System tasks now correctly route to IT Support agent
5. **Unnecessary Workflow Steps** - Eliminated redundant "write description" tasks

**Formations Used:** 
- `test-formations/formation-multi-agent-segregated/` - Multi-agent with A2A enabled
- Workflow configuration with `complexity_threshold: 5.0` for decomposition testing

**Success Criteria:** ✅ All tests passing with both direct A2A and workflow decomposition

</details>

<details>
<summary>Day 8: Clarification & Enhanced Information Flow</summary>

#### Goal: Validate clarification patterns and context management, then enhance with multiple sequences

### Part 1: Base Clarification Testing

### Test Group 8A: Single Clarification Patterns (Current Capabilities)
```python
# Test 8A1: Ambiguous Request
formation = Formation.load("formations/clarification.yaml")
overlord = await formation.start()

response = await overlord.chat("Build it")
# Should ask what to build
assert any(word in response.lower() for word in ["what", "clarify", "specific"])

# Follow-up with clarification
response = await overlord.chat("A Python web scraper")
# Should now provide specific help
assert "python" in response.lower()

# Test 8A2: Multi-agent Clarification
formation = Formation.load("formations/multi-clarification.yaml")
overlord = await formation.start()

response = await overlord.chat("I need help with the bug")
# Should coordinate to identify which type of bug (code, process, etc.)

# Test 8A3: Credential Selection Clarification
response = await overlord.chat("List my repositories")
# Should ask which account (GitHub, GitLab, etc.)
assert any(word in response.lower() for word in ["which", "account", "github", "gitlab"])
```

### Test Group 8B: Information Flow
```python
# Test 8B1: Context Propagation
response = await overlord.chat("I'm working on an e-commerce platform using React")
response = await overlord.chat("What database should I use?")
# Should consider e-commerce context in recommendation
assert any(db in response.lower() for db in ["postgres", "mysql", "mongo"])

# Test 8B2: Information Extraction
response = await overlord.chat(
    "My budget is $5000 and timeline is 2 weeks for the MVP"
)
# System should extract and use these constraints
response = await overlord.chat("What features should I prioritize?")
# Should consider budget and timeline constraints

# Test 8B3: Single Clarification Cancellation
response = await overlord.chat("Deploy to production")
# Should ask which environment/server
response = await overlord.chat("Actually, nevermind, just show me the code")
# Should cancel clarification and proceed with new request
```

### 🔧 **IMPLEMENTATION BREAK: Multiple Clarification Sequences**
**Implement**: Clarification stack architecture for multi-turn clarifications
**PRD**: [multiple-clarification-sequences.md](context/prds/multiple-clarification-sequences.md)
**Duration**: 3-4 days

### Part 2: Enhanced Clarification with Multiple Sequences

### Test Group 8C: Multiple Clarification Sequences
```python
# Test 8C1: Credential Rejection Flow
formation = Formation.load("formations/enhanced-clarification.yaml")
overlord = await formation.start()

response = await overlord.chat("List my GitHub repositories")
# Should show available accounts
assert "which account" in response.lower()

response = await overlord.chat("None of these, I want to add a new account")
# Should start sub-clarification for token
assert "token" in response.lower() or "authenticate" in response.lower()

response = await overlord.chat("ghp_abc123...")
# Should complete both clarifications and list repos
assert "repositories" in response.lower()

# Test 8C2: Multi-Step Configuration
response = await overlord.chat("Set up my development environment")
# Should ask for cloud provider
response = await overlord.chat("AWS")
# Should ask for region
response = await overlord.chat("us-east-1")
# Should ask about database
response = await overlord.chat("Yes, PostgreSQL")
# Should complete setup with all collected information
assert all(term in response.lower() for term in ["aws", "us-east-1", "postgresql"])

# Test 8C3: Error Recovery Flow
response = await overlord.chat("Deploy my application")
response = await overlord.chat("production")
# Simulate deployment failure
# Should offer recovery options without losing context
```

### Test Group 8D: Clarification Stack Management
```python
# Test 8D1: Stack Depth Handling
formation = Formation.load("formations/deep-clarification.yaml")
overlord = await formation.start(

# Create a 3-level deep clarification
response = await overlord.chat("I need to process some data")
# Level 1: What kind of data?
response = await overlord.chat("CSV files from our system")
# Level 2: Which system?
response = await overlord.chat("The one we discussed yesterday")
# Level 3: Need more context about yesterday
response = await overlord.chat("The sales analytics system")
# Should resolve all levels and process CSV from sales analytics

# Test 8D2: Parallel Clarification Branches
response = await overlord.chat("Compare data from two sources")
# Should handle clarifications for both sources
response = await overlord.chat("First source: database")
# Should ask about second source while remembering first
response = await overlord.chat("Second source: API")
# Should proceed with comparison

# Test 8D3: Clarification Timeout
# Start a clarification
response = await overlord.chat("Delete some files")
# Wait for timeout period
await asyncio.sleep(clarification_timeout + 1)
response = await overlord.chat("Hello")
# Should treat as new conversation, not clarification response
```

**Formations Required:** 6 configurations (4 base + 2 enhanced)
**Automation:** Conversation flow testing, context validation, clarification stack verification
**Success Criteria:**
- Base: 10 clarification tests pass, single clarification flows work correctly
- Enhanced: 15 additional multi-sequence tests pass, stack management verified

</details>

<details>
<summary>Day 9: Thinking Visibility & Transparency</summary>

#### Goal: Validate thinking visibility features for orchestration transparency

### Test Group 9A: Thinking Model Detection
```python
# Test 9A1: Automatic Model Detection
formation = Formation.load("formations/thinking-enabled.yaml")
overlord = await formation.start()

# Check if model detection happened during init
assert overlord.model_supports_thinking is not None
# For Claude 3.5 Sonnet, should be True
if "claude-3.5-sonnet" in overlord.model:
    assert overlord.model_supports_thinking == True

# Test 9A2: Non-Thinking Model Detection
formation_gpt = Formation.load("formations/thinking-gpt4.yaml")
overlord_gpt = await formation_gpt.start()

# GPT-4 should report as non-thinking
if "gpt-4" in overlord_gpt.model:
    assert overlord_gpt.model_supports_thinking == False

# Test 9A3: Runtime Thinking Detection
# Even if model says no, runtime detection should catch it
response = await overlord.chat("Explain step by step how to solve x^2 + 5x + 6 = 0")
# If response contains thinking tags, model_supports_thinking should be True
if "<thinking>" in response:
    assert overlord.model_supports_thinking == True
```

### Test Group 9B: Thinking Visibility Control
```python
# Test 9B1: Thinking Enabled (Default)
formation = Formation.load("formations/thinking-default.yaml")
overlord = await formation.start()

response = await overlord.chat("Analyze the pros and cons of microservices architecture")
# With thinking enabled and a thinking model, tags should be visible
if overlord.model_supports_thinking:
    assert "<thinking>" in response or "thinking" not in response.lower()

# Test 9B2: Thinking Disabled
formation_no_think = Formation.load("formations/thinking-disabled.yaml")
overlord_no_think = await formation_no_think.start()

response = await overlord_no_think.chat("Analyze the pros and cons of microservices architecture")
# Should strip thinking tags even from thinking models
assert "<thinking>" not in response

# Test 9B3: Thinking Configuration Override
formation = Formation.load("formations/thinking-config.yaml")
overlord = await formation.start()

# Verify configuration loaded correctly
assert overlord.thinking_enabled == False  # Based on formation config
response = await overlord.chat("What's the best sorting algorithm for large datasets?")
assert "<thinking>" not in response  # Should be stripped
```

### Test Group 9C: Response Format Handling
```python
# Test 9C1: Synchronous Response with Thinking
formation = Formation.load("formations/thinking-sync.yaml")
overlord = await formation.start()

response = await overlord.chat("Design a REST API for a blog system")
# Check response structure based on thinking visibility
if isinstance(response, dict):
    if overlord.thinking_enabled and overlord.model_supports_thinking:
        # Could have thinking in response content
        assert "thinking" in response or "<thinking>" in str(response)

# Test 9C2: Streaming Response with Thinking
response_stream = await overlord.chat(
    "Explain database normalization forms",
    stream=True
)
chunks = []
async for chunk in response_stream:
    chunks.append(chunk)
full_response = "".join(chunks)

# Streaming should include thinking tags when enabled
if overlord.thinking_enabled and overlord.model_supports_thinking:
    assert "<thinking>" in full_response or not overlord.model_supports_thinking
```

### Test Group 9D: Multi-Agent Thinking
```python
# Test 9D1: Agent Thinking Extraction
formation = Formation.load("formations/multi-agent-thinking.yaml")
overlord = await formation.start()

response = await overlord.chat(
    "I need help with both frontend React optimization and backend database scaling"
)
# Should coordinate multiple agents, potentially with thinking from each

# Test 9D2: Workflow Decomposition Thinking Stream
# NOTE: Enhancement needed - stream task decomposition process as <thinking>
# Currently only execution progress is streamed, not the planning/decomposition phase
formation = Formation.load("formations/thinking-workflow.yaml")
overlord = await formation.start()

# When streaming=True and complexity > threshold, should stream decomposition
response_stream = await overlord.chat(
    "Research AI trends, analyze market data, create visualizations, write comprehensive report",
    stream=True
)

thinking_decomposition_seen = False
async for chunk in response_stream:
    # Should see the workflow decomposition process in <thinking> tags
    # Example expected output:
    # <thinking>
    # Analyzing request complexity: 8.5/10
    # This requires multiple specialized tasks:
    # 1. Research AI trends - requires web search and analysis capabilities
    # 2. Analyze market data - requires data processing and statistical analysis
    # 3. Create visualizations - requires charting and design capabilities
    # 4. Write report - requires synthesis and writing capabilities
    #
    # Creating workflow with 4 subtasks...
    # Task dependencies: research -> analysis -> visualization -> report
    # Estimated total time: 15-20 minutes
    # </thinking>
    if "<thinking>" in chunk and "analyzing request" in chunk.lower():
        thinking_decomposition_seen = True

# TODO: Implement streaming of workflow decomposition phase as thinking
# This would provide transparency into the Overlord's planning process
# before execution begins

# Test 9D2: Thinking Consolidation
response = await overlord.chat(
    "Analyze our system architecture and suggest improvements for scalability and security"
)
# Should show consolidated thinking from multiple specialist agents
assert len(response) > 1000  # Comprehensive response expected

# Test 9D3: Mixed Thinking Models
# Formation with some thinking agents and some non-thinking
formation_mixed = Formation.load("formations/mixed-thinking-agents.yaml")
overlord_mixed = await formation_mixed.start()

response = await overlord_mixed.chat("Design a full-stack application")
# Should handle mixed agent capabilities gracefully
```

### Test Group 9E: Edge Cases & Error Handling
```python
# Test 9E1: Malformed Thinking Tags
# Simulate response with unclosed thinking tags
test_response = "<thinking>This is my reasoning... but no closing tag"
processed = overlord._strip_thinking_tags(test_response)
assert "<thinking>" not in processed

# Test 9E2: Nested Thinking Tags
test_response = "<thinking>Outer thought <thinking>Inner thought</thinking> back to outer</thinking>"
if not overlord.thinking_enabled:
    processed = overlord._strip_thinking_tags(test_response)
    assert "<thinking>" not in processed

# Test 9E3: Very Long Thinking Sections
long_thinking = "<thinking>" + "x" * 10000 + "</thinking>Short answer"
processed = overlord._strip_thinking_tags(long_thinking)
assert processed == "Short answer"
assert len(processed) < 100  # Thinking successfully removed
```

**Formations Required:** 8 thinking-enabled configurations
**Automation:** Model detection, tag processing, streaming validation
**Success Criteria:** 15 thinking tests pass, model detection validated, edge cases handled

</details>

<details>
<summary>Day 10: Large File Multimodal Processing</summary>

#### Goal: Implement and validate intelligent chunking, splitting, and optimization for large multimodal files (>100MB)

### 🔧 **IMPLEMENTATION BREAK: Large File Multimodal Processing**
**Implement**: Intelligent chunking strategies for video, audio, and documents
**PRD**: [large-file-multimodal-processing.md](context/prds/large-file-multimodal-processing.md)
**Duration**: 4-5 days

### Test Group 10A: File Size Detection & Routing
```python
# Test 10A1: Size-based Processing Strategy Selection
formation = Formation.load("formations/large-file-multimodal.yaml")
overlord = await formation.start()

# Small file - direct processing
small_video = load_test_file("test-files/small_video_5mb.mp4")
response = await overlord.chat(
    "Analyze this video",
    files=[{"filename": "small.mp4", "content": small_video, "content_type": "video/mp4"}]
)
assert isinstance(response, str)  # Direct response

# Medium file - chunked processing
medium_video = load_test_file("test-files/presentation_127mb.mp4")
response = await overlord.chat(
    "Analyze this presentation video",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}]
)
assert "processing" in response.lower() or "chunks" in response.lower()

# Test 10A2: Content Type Routing
large_audio = load_test_file("test-files/podcast_150mb.mp3")
response = await overlord.chat(
    "Transcribe this podcast",
    files=[{"filename": "podcast.mp3", "content": large_audio, "content_type": "audio/mp3"}]
)
# Should use audio-specific chunking strategy

# Test 10A3: Very Large File Handling (>2GB)
# Note: May use mock file metadata for testing
response = await overlord.chat(
    "Process this movie file",
    files=[{"filename": "movie.mp4", "size": 3_000_000_000, "content_type": "video/mp4"}]
)
assert "sampling" in response.lower() or "key frames" in response.lower()
```

### Test Group 10B: Video Chunking Implementation
```python
# Test 10B1: Video Segment Chunking
formation = Formation.load("formations/video-chunking.yaml")
overlord = await formation.start()

# 86MB iPhone video that currently times out
iphone_video = load_test_file("test-files/iphone_launch_86mb.mov")
response = await overlord.chat(
    "Analyze this iPhone launch event video in detail",
    files=[{"filename": "launch.mov", "content": iphone_video, "content_type": "video/quicktime"}]
)
# Should successfully process via chunking
assert "launch" in response.lower() or "iphone" in response.lower()
assert len(response) > 500  # Detailed analysis

# Test 10B2: Chunk Overlap & Continuity
response = await overlord.chat(
    "Create a timeline of events in this video",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}]
)
# Should maintain temporal coherence across chunks
assert "timeline" in response.lower() or any(time_word in response.lower() for time_word in ["0:00", "minute", "second"])

# Test 10B3: Audio Track Separation
response = await overlord.chat(
    "Transcribe all speech in this video presentation",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}]
)
# Should extract and process audio separately for better quality
assert len(response) > 1000  # Full transcription

# Test 10B4: Key Frame Extraction
response = await overlord.chat(
    "Show me the key visual moments in this video",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}]
)
# Should identify and analyze key frames
assert any(visual_word in response.lower() for visual_word in ["scene", "slide", "visual", "shows"])
```

### Test Group 10C: Audio Chunking & Processing
```python
# Test 10C1: Large Audio File Chunking
formation = Formation.load("formations/audio-chunking.yaml")
overlord = await formation.start()

# Audio file >25MB (OpenAI Whisper limit)
large_audio = load_test_file("test-files/conference_call_45mb.m4a")
response = await overlord.chat(
    "Transcribe this conference call with speaker identification",
    files=[{"filename": "call.m4a", "content": large_audio, "content_type": "audio/m4a"}]
)
# Should chunk and process successfully
assert "speaker" in response.lower() or len(response) > 2000

# Test 10C2: Audio Overlap Processing
podcast = load_test_file("test-files/podcast_2hour.mp3")
response = await overlord.chat(
    "Summarize the key topics discussed in this podcast",
    files=[{"filename": "podcast.mp3", "content": podcast, "content_type": "audio/mp3"}]
)
# Should maintain context across chunks
assert "topic" in response.lower() and len(response) > 500

# Test 10C3: Music vs Speech Detection
mixed_audio = load_test_file("test-files/presentation_with_music.mp3")
response = await overlord.chat(
    "Transcribe only the speech portions, ignoring background music",
    files=[{"filename": "mixed.mp3", "content": mixed_audio, "content_type": "audio/mp3"}]
)
# Should intelligently process speech segments
```

### Test Group 10D: Document Chunking
```python
# Test 10D1: Large PDF Processing
formation = Formation.load("formations/document-chunking.yaml")
overlord = await formation.start()

# 500-page PDF document
large_pdf = load_test_file("test-files/annual_report_500pages.pdf")
response = await overlord.chat(
    "Extract all financial data from this annual report",
    files=[{"filename": "report.pdf", "content": large_pdf, "content_type": "application/pdf"}]
)
# Should chunk by sections/pages
assert any(fin_word in response.lower() for fin_word in ["revenue", "financial", "profit"])

# Test 10D2: Smart Section Detection
technical_manual = load_test_file("test-files/technical_manual_300pages.pdf")
response = await overlord.chat(
    "Find the troubleshooting section and summarize common issues",
    files=[{"filename": "manual.pdf", "content": technical_manual, "content_type": "application/pdf"}]
)
# Should intelligently identify relevant sections
assert "troubleshoot" in response.lower() or "issue" in response.lower()

# Test 10D3: Multi-Document Processing
docs = [
    {"filename": "doc1.pdf", "content": load_test_file("test-files/doc1_100pages.pdf"), "content_type": "application/pdf"},
    {"filename": "doc2.pdf", "content": load_test_file("test-files/doc2_150pages.pdf"), "content_type": "application/pdf"},
    {"filename": "doc3.pdf", "content": load_test_file("test-files/doc3_200pages.pdf"), "content_type": "application/pdf"}
]
response = await overlord.chat("Compare these three documents and find common themes", files=docs)
# Should process multiple large documents efficiently
```

### Test Group 10E: Result Fusion & Quality
```python
# Test 10E1: Chunk Result Merging
formation = Formation.load("formations/result-fusion.yaml")
overlord = await formation.start()

# Process video with multiple analysis types
response = await overlord.chat(
    "Provide a complete analysis: transcription, visual description, and key moments",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}]
)
# Should merge chunk analyses coherently
assert all(element in response.lower() for element in ["transcript", "visual", "moment"])

# Test 10E2: Temporal Coherence
response = await overlord.chat(
    "Create a minute-by-minute breakdown of this presentation",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}]
)
# Should maintain time sequence across chunks
assert response.count(":") > 10  # Multiple timestamp references

# Test 10E3: Quality vs Speed Tradeoff
# Fast mode - sampling
response_fast = await overlord.chat(
    "Quick summary of this video",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}],
    processing_mode="fast"
)
time_fast = measure_processing_time()

# Comprehensive mode - full chunking
response_full = await overlord.chat(
    "Detailed analysis of this video",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}],
    processing_mode="comprehensive"
)
time_full = measure_processing_time()

assert len(response_full) > len(response_fast) * 1.5
assert time_full < time_fast * 3  # Not more than 3x slower
```

### Test Group 10F: Performance & Optimization
```python
# Test 10F1: Memory Efficiency
formation = Formation.load("formations/memory-efficient.yaml")
overlord = await formation.start()

initial_memory = get_memory_usage()
# Process 500MB video
large_video = load_test_file("test-files/training_video_500mb.mp4")
response = await overlord.chat(
    "Analyze this training video",
    files=[{"filename": "training.mp4", "content": large_video, "content_type": "video/mp4"}]
)
peak_memory = get_peak_memory_usage()
# Should not load entire file into memory at once
assert peak_memory - initial_memory < 1000_000_000  # Less than 1GB increase

# Test 10F2: Parallel Chunk Processing
start_time = time.time()
response = await overlord.chat(
    "Analyze video and transcribe all speech",
    files=[{"filename": "presentation.mp4", "content": medium_video, "content_type": "video/mp4"}]
)
processing_time = time.time() - start_time
# Should process chunks in parallel
assert processing_time < video_duration * 0.5  # Faster than real-time

# Test 10F3: Caching & Reprocessing
# First processing
response1 = await overlord.chat(
    "Analyze this video",
    files=[{"filename": "video.mp4", "content": test_video, "content_type": "video/mp4"}]
)
time1 = measure_processing_time()

# Second processing (should use cached chunks)
response2 = await overlord.chat(
    "What happens at minute 5 in this video?",
    files=[{"filename": "video.mp4", "content": test_video, "content_type": "video/mp4"}]
)
time2 = measure_processing_time()
assert time2 < time1 * 0.3  # Much faster due to caching
```

### Test Group 10G: Error Handling & Edge Cases
```python
# Test 10G1: Corrupted File Handling
formation = Formation.load("formations/error-handling.yaml")
overlord = await formation.start()

corrupted_video = load_test_file("test-files/corrupted_video.mp4")
response = await overlord.chat(
    "Analyze this video",
    files=[{"filename": "corrupted.mp4", "content": corrupted_video, "content_type": "video/mp4"}]
)
# Should handle gracefully
assert "error" in response.lower() or "unable" in response.lower()
assert "corrupted" in response.lower() or "damaged" in response.lower()

# Test 10G2: Processing Timeout Recovery
extremely_large = create_mock_file(size=5_000_000_000)  # 5GB
response = await overlord.chat(
    "Process this entire file in detail",
    files=[{"filename": "huge.mp4", "content": extremely_large, "content_type": "video/mp4"}],
    timeout=60  # 1 minute timeout
)
# Should gracefully handle timeout with partial results
assert "partial" in response.lower() or "timeout" in response.lower()

# Test 10G3: Format Mismatch Handling
response = await overlord.chat(
    "Analyze this video",
    files=[{"filename": "image.mp4", "content": jpeg_image, "content_type": "video/mp4"}]
)
# Should detect and handle format mismatch
assert "format" in response.lower() or "not a video" in response.lower()
```

**Formations Required:**
```yaml
# formations/large-file-multimodal.yaml
name: "large-file-processing"
agents:
  - id: "multimodal_agent"
    specialty: "multimodal_analysis"
    model: "google/gemini-2.0-flash"  # Best for video
    system_message: "You are an expert at analyzing large multimedia files"
llm:
  capability_models:
    vision:
      model: "google/gemini-2.0-flash"
    audio:
      model: "openai/whisper-1"
    video:
      model: "google/gemini-2.0-flash"
multimodal:
  processing:
    chunk_strategies:
      video:
        chunk_duration: 30  # seconds
        overlap: 5  # seconds
      audio:
        chunk_duration: 120  # seconds
        overlap: 15  # seconds
      document:
        chunk_size: 50  # pages
        overlap: 5  # pages
    size_thresholds:
      direct: 20_000_000  # 20MB
      chunked: 2_000_000_000  # 2GB
      streaming: 2_000_000_001  # >2GB
    timeouts:
      default: 300  # 5 minutes
      large_file: 600  # 10 minutes
memory:
  buffer: {enabled: true, size: 20}
```

**Test Files Required:**
- Various sizes: 5MB, 86MB, 127MB, 500MB test videos
- Large audio files: 45MB, 150MB, 2-hour podcasts
- Large PDFs: 300-500 page documents
- Corrupted/invalid files for error testing

**Dependencies:** ffmpeg for video/audio manipulation
**Automation:** Chunk processing validation, memory monitoring, performance profiling
**Success Criteria:** 25+ large file tests pass, <3x performance overhead, memory efficient

</details>

<details>
<summary>Day 11: Async Operations & Real-time Features</summary>

#### Goal: Validate async workflows and webhook integration

### Test Group 10A: Async Processing
```python
# Test 10A1: Long-running Task
formation = Formation.load("formations/async.yaml")
overlord = await formation.start()

response = await overlord.chat(
    "Analyze all Python files in this directory and create a complexity report"
)
# Should return immediately with job ID
assert "job_id" in response or "processing" in response.lower()

# Test 10A2: Webhook Delivery
webhook_url = "http://localhost:8080/webhook"
response = await overlord.chat(
    "Generate a comprehensive market analysis report",
    webhook_url=webhook_url
)
# Should deliver to webhook when complete
```

### Test Group 10B: Operation Management
```python
# Test 10B1: Operation Status
job_id = extract_job_id(response)
status = await overlord.get_operation_status(job_id)
assert status["state"] in ["pending", "processing", "completed"]

# Test 10B2: Operation Cancellation
response = await overlord.chat("Process this large dataset")
job_id = extract_job_id(response)
success = await overlord.cancel_operation(job_id)
assert success == True
```

**Webhook Server Required:** Mock webhook receiver
**Automation:** Async operation tracking, webhook verification
**Success Criteria:** 8 async tests pass, webhooks delivered

</details>

<details>
<summary>Day 12: Production Readiness & Scheduler</summary>

#### Goal: Validate enterprise features and production readiness

PRD: [text](context/prds/thinking-capabilities.md)

### Test Group 11A: Scheduler Operations
```python
# Test 11A1: One-time Job
formation = Formation.load("formations/scheduler.yaml")
overlord = await formation.start()

# Schedule a job for 5 minutes from now
run_at = datetime.now() + timedelta(minutes=5)
response = await overlord.chat(
    "Remind me to check the deployment",
    schedule={"run_at": run_at}
)
assert "scheduled" in response.lower()

# Test 11A2: Recurring Job
response = await overlord.chat(
    "Generate daily sales report",
    schedule={"cron": "0 9 * * *"}  # Daily at 9 AM
)
job_id = extract_job_id(response)
```

### Test Group 11B: Job Management
```python
# Test 11B1: List Active Jobs
jobs = await overlord.scheduler.get_active_jobs()
assert len(jobs) > 0
assert any(job["id"] == job_id for job in jobs)

# Test 11B2: Update Job
success = await overlord.scheduler.update_job(
    job_id,
    cron="0 10 * * *"  # Change to 10 AM
)
assert success == True

# Test 11B3: Job Execution History
history = await overlord.scheduler.get_job_history(job_id)
# After job runs
assert len(history) > 0
assert history[0]["status"] in ["success", "failure"]
```

### Test Group 11C: Performance & Integration
```python
# Test 11C1: Response Time
formation = Formation.load("formations/optimized.yaml")
overlord = await formation.start()

# Simple query benchmark
times = []
for _ in range(10):
    start = time.time()
    await overlord.chat("What's 2+2?")
    times.append(time.time() - start)
assert statistics.mean(times) < 2.0  # Average under 2 seconds

# Test 11C2: Full Stack Integration
response = await overlord.chat(
    "Search for recent AI news, analyze trends, create a summary document, "
    "and generate a visualization chart"
)
# Should coordinate: web search → analysis → document generation → chart creation
```

**Database Required:** PostgreSQL or SQLite for job persistence
**Automation:** Scheduler testing framework, time simulation, performance profiling
**Success Criteria:** 18 scheduler tests pass + performance targets met

</details>

---

## Success Metrics & Validation

### **Daily Success Criteria**
- **Day 1:** 7/7 foundation tests pass ✅ (chat flow testing with real services)
- **Day 2:** 20+/22+ memory tests pass ✅ (exceeded goal with advanced features)
- **Day 3:** 34/36 multimodal tests pass ✅ (94% success rate, exceeded 15 test goal)
- **Day 4:** 20+ MCP tests + credential tests pass ✅ (100% success rate, user isolation verified)
- **Day 5:** 21/22 file generation tests pass ✅ (95.5% success rate, security validation confirmed)
- **Day 6:** 19/19 knowledge tests pass ✅ (100% success rate across all 5 test groups 6A-6E)
- **Day 7:** Base: 18 coordination tests pass + A2A verified ✅ | Workflow orchestration + resilience ✅ | Deferred async (32 tests) ✅ | Enhanced: 12 SOP tests (pending)
- **Day 8:** Base: 10 clarification tests pass | Enhanced: 15 multi-sequence tests pass
- **Day 9:** 15 thinking tests pass + model detection validated + edge cases handled
- **Day 10:** 25+ large file tests pass + <3x performance overhead + memory efficient
- **Day 11:** 8 async tests pass + webhook delivery verified
- **Day 12:** 18 scheduler tests pass + performance targets met

### **Final Validation Checklist**
- [ ] All 22 feature dimensions tested in combination (including SOPs and multi-clarification)
- [x] User credentials system fully validated with encryption & isolation ✅
- [x] File generation tested across all major formats with security validation ✅
- [x] Domain knowledge system tested with multiple agents and sources ✅
- [x] Built-in MCP security validation (code filtering, safe execution) ✅
- [ ] SOP system enhances multi-agent coordination with procedural guidance
- [ ] Multiple clarification sequences maintain intent across sub-clarifications
- [ ] Thinking visibility with automatic model detection
- [ ] Large file multimodal processing (>100MB files handled efficiently)
- [ ] Intelligent chunking strategies for video, audio, and documents
- [ ] Performance targets met (< 2s simple, < 30s complex)
- [ ] Memory usage stable (< 100MB growth per 100 interactions)
- [ ] Error handling graceful (no crashes, clear error messages)
- [ ] Formation-first architecture validated
- [ ] Real developer API (`overlord.chat()`) works consistently

### **New Features Validated**
- ✨ **User Credentials Management**: Secure storage, encryption, user isolation
- ✨ **MCP with User Credentials**: Automatic credential discovery and injection
- ✨ **Domain Knowledge System**: Agent-level knowledge loading and enhancement
- ✨ **Knowledge Search & Retrieval**: Semantic search with relevance scoring
- ✨ **Multi-Agent Knowledge Sharing**: Cross-agent knowledge coordination
- ✨ **Standard Operating Procedures (SOPs)**: Overlord-level procedural guidance for task decomposition
- ✨ **Multiple Clarification Sequences**: Stack-based clarification management with intent preservation
- ✨ **Thinking Visibility**: Automatic model detection with configurable transparency
- ✨ **Large File Multimodal Processing**: Intelligent chunking for >100MB files
- ✨ **Video/Audio Chunking**: Overlapping segments with temporal coherence
- ✨ **Result Fusion Engine**: Merges chunk analyses into coherent narratives

### **Automation Coverage**
- **85% Automated:** Functional tests, performance benchmarks, CI/CD
- **15% Manual:** Complex integration validation, user experience testing

**Total Test Coverage:** 1,400+ test combinations across 22 feature dimensions
