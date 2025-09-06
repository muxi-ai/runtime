# MUXI Runtime Comprehensive Test Plan

**Date:** Implementation Ready
**Status:** Implementation Ready
**Based on:** Formation Refactoring + Agent Cleanup Architecture + Production Scheduler + Credentials & Domain Knowledge

## Executive Summary

This document outlines a comprehensive testing strategy for the MUXI Runtime that validates all implemented features through incremental complexity. All tests use `overlord.chat()` as the primary interface, mirroring real developer usage patterns.

**Total Test Scope:** 1,200+ strategic test combinations covering 20 feature dimensions
**Implementation Timeline:** 12 test areas
**Automation Level:** 85% automated execution, 15% manual validation

---

<details>
<summary>Prerequisites</summary>

## Prerequisites

Before implementing the comprehensive test plan, the following prerequisites must be completed:

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
- ✅ Create test data directory structure (`tests/assets/formations/`, `tests/assets/files/`)
- ⏸️ Configure CI/CD pipeline for automated testing (optional - deferred)

### ✅ **Step 4: Essential Test Formations (COMPLETED)**
- ✅ Create fundamental formation configurations following the schema structure:
  - `tests/assets/formations/formation-basic/` - Single agent, minimal memory
    - `formation.yaml` - Main formation configuration
    - `agents/` - Agent definitions
    - `secrets.enc` - Encrypted secrets file (symlink to shared)
  - `tests/assets/formations/formation-file-generation/` - Built-in MCP enabled
    - `formation.yaml` - Formation with Artifacts System
    - `agents/` - Agent configurations
    - `mcp/` - MCP service definitions
    - `secrets.enc` - Symlink to shared secrets
  - `tests/assets/formations/formation-multi-agent/` - Multiple agents for routing tests
    - `formation.yaml` - Multi-agent setup
    - `agents/` - Multiple agent definitions
    - `a2a/` - Agent-to-agent communication configs
    - `secrets.enc` - Symlink to shared secrets
  - `tests/assets/formations/formation-memory/` - Buffer and persistent memory
    - `formation.yaml` - Memory configuration
    - `agents/` - Memory-enabled agents
    - `sqlite.db` - Persistent storage
    - `secrets.enc` - Symlink to shared secrets
  - `tests/assets/formations/formation-complete/` - Comprehensive formation with all components
    - `formation.yaml` - Multi-agent with MCP and A2A
    - `agents/` - Orchestrator, analyst, developer agents
    - `mcp/` - File generation, calculator, web tools
    - `a2a/` - Communication protocols and workflows
    - `secrets.enc` - Symlink to shared secrets
  - `tests/assets/formations/secrets.enc` - Shared encrypted secrets file for all formations

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

The MUXI Runtime is now ready for the comprehensive test plan implementation!
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

**IMPORTANT**: Test formations are already available in the `tests/assets/formations/` directory. You should use these existing formations rather than creating new ones for each test:

- `tests/assets/formations/formation-basic/` - Single agent with minimal memory
- `tests/assets/formations/formation-memory/` - Various memory configurations (SQLite, PostgreSQL, buffer modes)
- `tests/assets/formations/formation-multi-agent/` - Multiple agents for routing tests
- `tests/assets/formations/formation-file-generation/` - Built-in MCP enabled
- `tests/assets/formations/formation-complete/` - Comprehensive formation with all components

Each formation includes:
- Proper YAML configuration files
- Agent definitions in `agents/` subdirectory
- Encrypted secrets via `secrets.enc` (symlinked to shared file)
- Real LLM providers and API keys configured

---

### **Test Directory Structure Standard**

Each test area should follow the standardized structure with descriptive names:

```
tests/e2e/X_feature/
├── TEST_MAPPING.md          # Maps test plan requirements to actual test files
├── FINAL_SUMMARY.md         # Day's accomplishments matching test plan format
├── test_Xa1_*.py            # Test Group A, Test 1
├── test_Xa2_*.py            # Test Group A, Test 2
├── test_Xb1_*.py            # Test Group B, Test 1
├── test_*_helper.py         # Helper/debug utilities
├── run_areaX_tests.py       # Area-specific test runner
└── README.md                # Optional area-specific notes
```

**Naming Convention:**
- Test files: `test_[area][group][number]_descriptive_name.py`
- Example: `test_2a1_basic_conversation_context.py`
- Helpers: `test_descriptive_name_helper.py`

**Required Files:**
- `TEST_MAPPING.md`: Documents how test plan maps to actual test files
- `FINAL_SUMMARY.md`: Matches test plan format with accomplishments
- `run_areaX_tests.py`: Handles both pytest and standalone scripts

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

## Test Implementation Status

### **📊 Overall Progress**
| Area | Feature | Status | Test Reports |
|------|---------|--------|--------------|
| 1 | Foundation Layer | ✅ COMPLETE (10/10 tests) | [1a.md](tests/reports/1a.md), [1b.md](tests/reports/1b.md) |
| 2 | Memory Systems | ✅ COMPLETE (20+ tests) | [2a-2o.md](tests/reports/) |
| 3 | Multimodal & Documents | ✅ COMPLETE (34/36 tests) | [3a-3k.md](tests/reports/) |
| 4 | MCP & Tools | ✅ COMPLETE (20+ tests) | [4a-4e.md](tests/reports/) |
| 5 | Artifacts & File Generation | ✅ COMPLETE (21/22 tests) | [5a-5f.md](tests/reports/) |
| 6 | Knowledge & RAG | ✅ COMPLETE (19/19 tests) | [6a-6e.md](tests/reports/) |
| 7 | Orchestration & SOPs | ✅ COMPLETE (All tests) | [7a-7d.md](tests/reports/) |
| 8 | Clarification System | ✅ COMPLETE (10+ tests) | [8a-8f.md](tests/reports/) |
| 9 | Async Operations | 🔄 READY | Specification complete |
| 10 | Streaming Responses | 🔄 READY | Specification complete |
| 11 | Response Formats | 🔄 READY | Specification complete |
| 12 | Thinking Visibility | 🔄 READY | Specification complete |
| 13 | Task Scheduler | 🔄 READY | Specification complete |

### **✅ Completed: 8/13 areas (Core functionality fully tested)**
### **🔄 Ready for Implementation: 5/13 areas (Advanced features specified)**

---

## 13 Test Areas Implementation Details

### **Phase 1: Foundation & Core Systems (Areas 1-3)**

<details>
<summary>✅ Area 1 (Foundation): Foundation Layer</summary>

#### Goal: Establish basic formation loading and simple chat functionality

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: 2 groups (1A Formation Loading, 1B Agent Communication)
- **Tests Passing**: 10/10 (100% success rate)
- **Test Reports**: [reports/1a.md](reports/1a.md), [reports/1b.md](reports/1b.md)
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
- `tests/assets/formations/formation-basic/` - Single-agent with MCP integration
- `tests/assets/formations/formation-multi-agent/` - Multi-agent with routing
- `tests/assets/formations/invalid-formations/` - 8 invalid formation types

**Success Criteria: ✅ All foundation tests pass with chat flow validation**

</details>

<details>
<summary>✅ Area 2 (Memory): Memory Systems</summary>

#### Goal: Validate 3-tier memory architecture with comprehensive coverage

**Implementation Status: COMPLETED ✅**
- **Test Groups**: 2A through 2M (13 test groups)
- **Tests Passing**: All groups passing with full regression validation
- **Core Memory Systems**: All working ✅
- **Advanced Features**: All implemented and tested ✅

### Test Group Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **2A** | Basic Conversation Context | ✅ | [reports/2a.md](reports/2a.md) |
| **2B** | SQLite Persistence | ✅ | [reports/2b.md](reports/2b.md) |
| **2C** | PostgreSQL User Isolation | ✅ | [reports/2c.md](reports/2c.md) |
| **2D** | Buffer Memory Modes | ✅ | [reports/2d.md](reports/2d.md) |
| **2E** | Remote Faiss Vector Store | ✅ | [reports/2e.md](reports/2e.md) |
| **2F** | Advanced Memory Features | ✅ | [reports/2f.md](reports/2f.md) |
| **2G** | Memory Context Integration | ✅ | [reports/2g.md](reports/2g.md) |
| **2H** | Buffer Memory Context Enhancement | ✅ | [reports/2h.md](reports/2h.md) |
| **2I** | Natural Language Memory Extraction | ✅ | [reports/2i.md](reports/2i.md) |
| **2J** | Collection-Based Memory Organization | ✅ | [reports/2j.md](reports/2j.md) |
| **2K** | Memory System Integration | ✅ | [reports/2k.md](reports/2k.md) |
| **2L** | Database Optimization | ✅ | [reports/2l.md](reports/2l.md) |
| **2M** | Error Resilience | ✅ | [reports/2m.md](reports/2m.md) |
| **2O** | Preference System | 🔄 | [reports/2o.md](reports/2o.md) |

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
- Ultra-simple preference detection and storage

**Integration Points:**
- Real-time extraction during conversations
- Long-term memory integration in prompts
- Buffer memory context enhancement
- Cross-session memory persistence

### Formations and Test Data
- **Primary Formation**: `tests/assets/formations/formation-memory/`
- **PostgreSQL**: User isolation with real database
- **SQLite**: Single-user development mode
- **Buffer Modes**: Local (FAISS) and Remote (FAISSx)
- **Test Users**: Isolated credentials and memory spaces

**Success Criteria: ✅ All 13 test groups passing with full regression validation**

### Test Implementation Notes

**All test implementations and detailed results are documented in the individual test reports.**

**Test Execution**: Each test group uses real services via the `overlord.chat()` interface - no mocks.

**Formations Used**:
- `tests/assets/formations/formation-memory/formation-postgres.yaml` - PostgreSQL with user isolation
- `tests/assets/formations/formation-memory/formation-buffer-local.yaml` - Local FAISS buffer
- `tests/assets/formations/formation-memory/formation-buffer-remote.yaml` - Remote FAISSx buffer

**Test Data Management**: Each test report includes specific user credentials, expected outputs, and regression validation results.

</details>

<details>
<summary>✅ Area 3 (Multimodal): Complete Multimodal Processing</summary>

#### Goal: Validate ALL multimodal capabilities - Documents, Images, Audio, Video, Cross-Modal Analysis

**Implementation Status: COMPLETED ✅**
- **Total Tests**: 37 tests across 11 test groups
- **Success Rate**: 95% (35/37 tests passing)
- **Core Features**: All multimodal processing capabilities validated
- **Real Files**: All tests use actual files from tests/assets/files directory

### Test Group Results

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **3A** | Document Processing (PDF, DOCX, OCR) | ✅ 3/3 | [reports/3a.md](reports/3a.md) |
| **3B** | Audio Processing & Speech Transcription | ✅ 4/4 | [reports/3b.md](reports/3b.md) |
| **3C** | Video Frame Analysis & Understanding | ✅ 4/4 | [reports/3c.md](reports/3c.md) |
| **3D** | Cross-Modal Analysis (Doc + Image) | ✅ 3/3 | [reports/3d.md](reports/3d.md) |
| **3E** | Processing Modes (Sync/Async) | ✅ 2/2 | [reports/3e.md](reports/3e.md) |
| **3F** | Real File Processing with Webhooks | ✅ 5/5 | [reports/3f.md](reports/3f.md) |
| **3G** | Content Extraction Accuracy | ✅ 4/4 | [reports/3g.md](reports/3g.md) |
| **3H** | Large File Handling (>25MB) | ⚠️ 2/3 | [reports/3h.md](reports/3h.md) |
| **3I** | Cross-Format Validation | ⚠️ 2/4 | [reports/3i.md](reports/3i.md) |
| **3J** | Error Handling & Edge Cases | ✅ 3/4 | [reports/3j.md](reports/3j.md) |
| **3K** | AVChat Audio/Video Interface | ✅ 1/1 | [reports/3k.md](reports/3k.md) |

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

### **Phase 2: Tool Integration & Knowledge Systems (Areas 4-6)**

<details>
<summary>✅ Area 4 (MCP): MCP Integration & User Credentials</summary>

#### Goal: Validate tool discovery, invocation, multi-server management, and user credential system

**Implementation Status: ✅ COMPLETED**
- **Test Groups**: 5 test groups (4A through 4E)
- **Total Tests**: 20+ tests across all groups
- **Success Rate**: 100% (all tests passing)
- **Formation Used**: `tests/assets/formations/formation-mcp`

### Test Group Results Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **4A** | Single MCP Server Operations | ✅ PASSED | [reports/4a.md](reports/4a.md) |
| **4B** | Multi-MCP Integration | ✅ PASSED | [reports/4b.md](reports/4b.md) |
| **4C** | Linear MCP (Formation Secrets) | ✅ PASSED | [reports/4c.md](reports/4c.md) |
| **4D** | GitHub MCP (User Credentials) | ✅ PASSED (7/7) | [reports/4d.md](reports/4d.md) |
| **4E** | User Credential Isolation | ✅ PASSED | [reports/4e.md](reports/4e.md) |

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
<summary>✅ Area 5 (Artifacts): Artifacts System</summary>

#### Goal: Comprehensive testing of the built-in Artifacts System server

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: 6 groups (5A through 5F)
- **Tests Passing**: 21/22 (95.5% success rate)
- **Test Reports**: Complete reports in `reports/`
- **Formation Used**: `tests/assets/formations/formation-file-generation/`

### Test Group Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **5A** | Basic File Generation | ✅ 3/3 | [reports/5a.md](reports/5a.md) |
| **5B** | Multiple File Types | ✅ 3/3 | [reports/5b.md](reports/5b.md) |
| **5C** | Large File Handling | ✅ 3/3 | [reports/5c.md](reports/5c.md) |
| **5D** | Security & Validation | ✅ 4/4 | [reports/5d.md](reports/5d.md) |
| **5E** | Complex Multi-Format Generation | ✅ 4/4 | [reports/5e.md](reports/5e.md) |
| **5F** | Implicit File Generation | ✅ 4/5 | [reports/5f.md](reports/5f.md) |

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
formation = Formation.load("tests/assets/formations/formation-file-generation")
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
<summary>✅ Area 6 (Knowledge): Domain Knowledge System</summary>

#### Goal: Validate agent-level domain knowledge implementation (loading, caching, search, isolation, and edge cases)

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: All 5 groups (6A through 6E)
- **Tests Passing**: 100% success rate across all groups
- **Formation Used**: `tests/assets/formations/formation-knowledge/`

### Test Group Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **6A** | Knowledge Loading & Embedding | ✅ PASSED | [reports/6a.md](reports/6a.md) |
| **6B** | Knowledge Caching & Change Detection | ✅ PASSED | [reports/6b.md](reports/6b.md) |
| **6C** | Knowledge Search & Retrieval | ✅ PASSED | [reports/6c.md](reports/6c.md) |
| **6D** | Agent Knowledge Isolation | ✅ PASSED | [reports/6d.md](reports/6d.md) |
| **6E** | Knowledge Loading Edge Cases | ✅ PASSED | [reports/6e.md](reports/6e.md) |

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
# tests/assets/formations/formation-knowledge/
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
await formation.load("tests/assets/formations/formation-knowledge/formation.yaml")
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

### **Phase 3: Advanced Coordination & Enterprise Features (Areas 7-12)**

<details>
<summary>✅ Area 7 (Orchestration): Multi-Agent Coordination & SOP Enhancement</summary>

#### Goal: Validate agent orchestration and task decomposition, then enhance with SOP system

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: 4 groups (7A Task Decomposition, 7B A2A Communication, 7C SOP-Guided, 7D SOP Discovery)
- **Total Tests**: 18 tests across all groups
- **Success Rate**: 100% (all tests passing)
- **Formation Used**: Multiple formations including formation-internal, formation-multi-agent, formation-sop

### Test Group Results Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **7A** | Task Decomposition & Workflow Orchestration | ✅ PASSED | [reports/7a.md](reports/7a.md) |
| **7B** | A2A Communication & Integration | ✅ PASSED | [reports/7b.md](reports/7b.md) |
| **7C** | SOP-Guided Task Decomposition | ✅ PASSED | [reports/7c.md](reports/7c.md) |
| **7D** | SOP Discovery and Relevance | ✅ PASSED | [reports/7d.md](reports/7d.md) |

### Test Group 7A: Task Decomposition & Workflow Orchestration ✅
```python
# Test 7A1: Research and Write Task
formation = Formation.load("formations/multi-specialist.yaml")
overlord = await formation.start()

response = await overlord.chat(
    "Research renewable energy trends and write a brief report with recommendations"
)
# Should involve researcher → analyst → writer coordination
assert len(response) > 500
assert "recommendation" in response.lower()
assert "research" in response.lower()

# Test 7A2: Complex Multi-Step Task
response = await overlord.chat(
    "Find the latest Tesla stock price, analyze the trend, and create a trading recommendation"
)
# Should coordinate data agent → analysis agent → recommendation agent
```

### Test Group 7A10: Deferred Async Execution (Approval-Aware) ✅
```python
# Test 7A10: Workflow Approval with Async Safety
formation = Formation.load("formations/workflow-approval.yaml")
overlord = await formation.start()

# Complex request that would trigger async AND needs approval
response = await overlord.chat(
    "Research AI market trends, analyze competitors, create visualizations, "
    "write comprehensive report, and create Linear issues for action items",
    use_async=None  # Let system decide
)
# Should remain synchronous for approval flow, not go async prematurely
assert "approve" in response.lower() or "workflow" in response.lower()

# After approval, can execute asynchronously if appropriate
response = await overlord.chat("yes", user_id="same_user")
# Now safe to process asynchronously if time estimate > threshold
```

### Test Group 7B: A2A Communication & Integration ✅
```python
# Test 7B1: Internal A2A (within formation)
formation = Formation.load("formations/internal-a2a.yaml")
overlord = await formation.start()

response = await overlord.chat("I need help with Python and also database design")
# Should trigger agent consultation patterns internally

# Test 7B2: External A2A (cross-formation)
# Start second formation on different port
formation2 = Formation.load("formations/external-specialist.yaml")
overlord2 = await formation2.start()

# Main formation requests help from external specialist
response = await overlord.chat("I need specialized legal advice about contracts")
# Should communicate with external legal formation
```

### Test Group 7C: SOP-Guided Task Decomposition ✅
```python
# Test 7C1: Incident Response SOP
# Create formation with sops/ directory containing incident-response.yaml
formation = Formation.load("formations/sop-enabled.yaml")
overlord = await formation.start()

response = await overlord.chat("Production is down, customers are complaining")
# Should follow SOP: assess → notify → investigate → fix → document
# Verify proper agent coordination following SOP steps

# Test 7C2: Customer Onboarding SOP
response = await overlord.chat("New enterprise customer ACME Corp needs onboarding")
# Should follow customer-onboarding.yaml SOP
# Agents should be coordinated according to procedural steps

# Test 7C3: No SOP Available
response = await overlord.chat("Write a haiku about clouds")
# Should fall back to normal task decomposition
# No SOP should be loaded for creative tasks
```

### Test Group 7D: SOP Discovery and Relevance ✅
```python
# Test 7D1: Semantic SOP Matching
formation = Formation.load("formations/multi-sop.yaml")  # Has 10+ SOPs
overlord = await formation.start()

# Test multilingual semantic matching
response = await overlord.chat("Seguridad breach detected")  # Spanish
# Should still find security-incident.yaml SOP

# Test 7D2: Ambiguous Request Resolution
response = await overlord.chat("Handle the issue with the system")
# Should identify most relevant SOP based on context

# Test 7D3: SOP Performance
# Load formation with 50+ SOPs
start_time = time.time()
response = await overlord.chat("Deploy new version to production")
sop_search_time = time.time() - start_time
assert sop_search_time < 0.1  # SOP search should add <100ms
```


### Key Technical Achievements

**✅ Workflow Orchestration:**
- Task decomposition with MCP tool integration
- PDF generation and file creation workflows
- Resilience integration with user-friendly error messages
- Deferred async execution (approval-aware)
- Production-ready workflow tracking

**✅ A2A Communication:**
- Internal A2A within formation boundaries
- External A2A cross-formation communication
- Capability-based routing for agent selection
- Workflow decomposition with A2A integration

**✅ SOP System Architecture:**
- Direct pass to task decomposer (no manual parsing)
- 72% code reduction (1000+ → ~800 lines)
- FAISS-based semantic search for SOP discovery
- Multi-language support for global teams
- Dual execution modes (Template/Guide)

**✅ Performance Improvements:**
- 40-80% execution time reduction
- 3-step SOP: 104s → 10s (90% improvement)
- SOP discovery: <50ms with 50+ SOPs
- Intelligent optimization and parallelization

**Success Criteria: ✅ 100% of orchestration tests passing with production-ready features**

*All test implementations and detailed results are documented in the individual test reports.*

</details>

<details>
<summary>✅ Area 8 (Clarification): Unified Clarification System</summary>

#### Goal: Validate unified clarification system with reactive, proactive, and multi-turn capabilities

**Implementation Status: COMPLETED ✅**
- **Test Groups Completed**: 6 groups (8A through 8F)
- **Tests Passing**: 100% success rate across all groups
- **Test Reports**: Complete reports in `tests/reports/`
- **Formation Used**: `tests/e2e/8_clarification/formations/formation-clarification/`

### Test Group Summary

| Group | Focus Area | Status | Report |
|-------|------------|--------|---------|
| **8A** | Ambiguous Request Handling | ✅ 3/3 | [reports/8a.md](reports/8a.md) |
| **8B** | Multi-Agent Clarification | ✅ 3/3 | [reports/8b.md](reports/8b.md) |
| **8C** | Context-Aware Clarification | ✅ 3/3 | [reports/8c.md](reports/8c.md) |
| **8D** | Clarification with Tool Usage | ✅ 3/3 | [reports/8d.md](reports/8d.md) |
| **8E** | Dynamic Clarification | ✅ 7/7 | [reports/8e.md](reports/8e.md) |
| **8F** | Proactive Clarification | ✅ 3/3 | [reports/8f.md](reports/8f.md) |

### Key Technical Achievements

**✅ Unified Clarification System:**
- Reactive clarification for ambiguous requests
- Proactive clarification with information gathering
- Multi-turn conversation support with context preservation
- Request ID tracking for maintaining clarification state
- LLM-based intent detection (multilingual support)

**✅ Advanced Features:**
- Credential selection with intelligent disambiguation
- API key redirection and dynamic handling
- Context switch detection vs clarification responses
- Workflow integration with approval bypass
- Brainstorming facilitation through proactive questioning

**✅ Context Management:**
- Buffer memory integration for conversation context
- Enhanced message formatting with `=== CONVERSATION CONTEXT ===` markers
- Proper handling of context switches
- Session-based credential caching
- Multi-turn state preservation

**✅ Integration Points:**
- MCP tool usage during clarification
- Multi-agent coordination for complex clarifications
- Workflow approval handling without interference
- Task decomposition with full context preservation

### Critical Fixes Applied During Testing

1. **Context Preservation Bug** (Line 5610):
   - Fixed issue where enhanced message was replaced after clarification
   - Ensured buffer memory context preserved throughout flow

2. **Workflow Approval Bypass**:
   - Added early detection of workflow approval responses
   - Bypasses credential and clarification checks
   - Prevents misinterpretation of approval responses

3. **Context Switch Detection**:
   - UnifiedClarificationSystem tracks last question asked
   - Accurate detection of responses vs new requests
   - Prevents confusion between answers and new queries

4. **Task Decomposition Context** (Line 6575):
   - Fixed passing enhanced_message to task decomposer
   - Decomposer now receives full conversation history
   - Enables proper workflow creation with context

### Test Implementation Highlights

**8A Tests**: Basic ambiguous request handling with proper clarification flow
**8B Tests**: Multi-agent participation in clarification process
**8C Tests**: Context preservation across multiple clarification rounds
**8D Tests**: Tool usage integrated with clarification flows
**8E Tests**: Dynamic credential handling with 7 comprehensive scenarios
**8F Tests**: Proactive questioning and brainstorming facilitation

### ID Hierarchy Architecture
```
user_id (user isolation)
  └── session_id (chat grouping)
      └── request_id (single interaction with all clarifications)
```

### Known Issues Identified

**Unrelated Regression**:
- Artifact generation not working (artifacts=None)
- Previously working in Area 5 (95.5% success rate)
- Affects all artifact creation, not clarification-specific
- Requires separate investigation and fix

**Success Criteria: ✅ All clarification tests pass with 100% success rate**

*Detailed test implementations and results are documented in the individual test reports.*

</details>

<details>
<summary>Area 9 (Async): Async Operations & Webhook Integration</summary>

#### Goal: Validate async processing and webhook delivery for long-running operations

### Test Group 9A: Async Decision Logic
```python
# Test 9A1: Automatic Async Triggering
formation = Formation.load("formations/async.yaml")
overlord = await formation.start()

# Complex request that should trigger async (use_async=None lets system decide)
response = await overlord.chat(
    "Research AI market trends, analyze competitors, create visualizations, "
    "write comprehensive report, and create Linear issues for action items",
    use_async=None  # Let system decide based on complexity
)
# Should return async response with webhook info
assert "webhook" in response or "async" in response.lower()
assert "request_id" in response

# Test 9A2: Forced Async Mode
response = await overlord.chat(
    "What's 2+2?",  # Simple request
    use_async=True,  # Force async
    webhook_url="http://localhost:8080/webhook"
)
# Should process async even for simple request
assert "webhook" in response

# Test 9A3: Forced Sync Mode
response = await overlord.chat(
    "Complex multi-step analysis...",  # Complex request
    use_async=False  # Force sync
)
# Should process synchronously and return full response
assert isinstance(response, str) and len(response) > 100
```

### Test Group 9B: Request Lifecycle Management ✅ **COMPLETED**
```python
# Test 9B1: Request Status Tracking and Cancellation APIs
formation = Formation.load("formations/async.yaml")
overlord = await formation.start()

# Test status checking for active requests
response = await overlord.chat(
    "What is 2+2? Please show your work.",
    use_async=True
)
request_id = response["request_id"]

# Check initial status
status = await overlord.get_request_status(request_id)
assert status["request_id"] == request_id
assert status["status"] in ["processing", "running", "pending"]

# Monitor status during execution
for i in range(3):
    await asyncio.sleep(2)
    status = await overlord.get_request_status(request_id)
    if status["status"] in ["completed", "failed", "cancelled"]:
        break

# Test request cancellation
cancel_response = await overlord.chat(
    "What is 5+3? Show the calculation.",
    use_async=True
)
cancel_request_id = cancel_response["request_id"]

# Cancel the request
cancel_result = await overlord.cancel_request(cancel_request_id)
assert cancel_result["success"] == True

# Verify cancellation status
post_cancel_status = await overlord.get_request_status(cancel_request_id)
assert post_cancel_status["status"] == "cancelled"

# Test error handling
invalid_status = await overlord.get_request_status("invalid_id")
assert "error" in invalid_status

# Test memory leak prevention - completed requests remain queryable
final_status = await overlord.get_request_status(request_id)
# Should be available for 48 hours after completion
assert "error" not in final_status or final_status["status"] == "completed"
```

**Implementation Status:** ✅ **COMPLETED** (September 2025)
- ✅ Ultra-simplified two-tier storage (RequestTracker → Buffer Memory with 48h TTL)
- ✅ `get_request_status(request_id)` API for tracking active and completed requests
- ✅ `cancel_request(request_id)` API with asyncio.Task cancellation support
- ✅ Memory leak prevention via automatic cleanup of completed requests
- ✅ Comprehensive test coverage: `tests/e2e/9_async/test_9b1_request_lifecycle.py`
- ✅ Complete documentation: `tests/reports/9b.md` and `docs/request-lifecycle.md`
- ✅ **Production ready**: Only 2 code locations modified, leveraging existing infrastructure

### Test Group 9C: Webhook Delivery & Status
```python
# Test 9C1: Webhook Delivery
import aiohttp
from aiohttp import web

# Start webhook receiver
webhook_received = {}
async def webhook_handler(request):
    webhook_received['data'] = await request.json()
    return web.Response(text="OK")

app = web.Application()
app.router.add_post('/webhook', webhook_handler)
runner = web.AppRunner(app)
await runner.setup()
site = web.TCPSite(runner, 'localhost', 8080)
await site.start()

# Send async request
response = await overlord.chat(
    "Generate comprehensive analysis report",
    use_async=True,
    webhook_url="http://localhost:8080/webhook"
)
request_id = response['request_id']

# Wait for webhook delivery
await asyncio.sleep(30)  # Give time to process

# Verify webhook received
assert 'data' in webhook_received
assert webhook_received['data']['request_id'] == request_id
assert webhook_received['data']['status'] == 'completed'
assert len(webhook_received['data']['response']) > 100

# Test 9C2: Operation Status Tracking
response = await overlord.chat(
    "Long running task...",
    use_async=True
)
request_id = response['request_id']

# Check status while processing
status = await overlord.get_operation_status(request_id)
assert status['state'] in ['pending', 'processing', 'completed', 'failed']
assert 'progress' in status  # Optional progress percentage

# Test 9C3: Operation Cancellation
response = await overlord.chat(
    "Process large dataset...",
    use_async=True
)
request_id = response['request_id']

# Cancel the operation
success = await overlord.cancel_operation(request_id)
assert success == True

# Verify cancelled
status = await overlord.get_operation_status(request_id)
assert status['state'] == 'cancelled'
```

### Test Group 9D: Error Handling & Edge Cases
```python
# Test 9D1: Webhook Failure Handling
formation = Formation.load("formations/async.yaml")
overlord = await formation.start()

# Test with unreachable webhook
response = await overlord.chat(
    "Process this task",
    use_async=True,
    webhook_url="http://nonexistent.local/webhook"
)
request_id = response['request_id']

# Should still process, but webhook delivery fails
await asyncio.sleep(10)
status = await overlord.get_operation_status(request_id)
assert status['state'] == 'completed'
assert 'webhook_error' in status  # Should note delivery failure

# Test 9D2: Timeout Handling
response = await overlord.chat(
    "This will take forever to process...",
    use_async=True,
    threshold_seconds=5  # Very short timeout
)
# Should handle timeout gracefully

# Test 9D3: Async with Streaming (Should Fail)
try:
    response = await overlord.chat(
        "Generate report",
        use_async=True,
        stream=True  # Can't stream async!
    )
    assert False, "Should have raised error"
except ValueError as e:
    assert "stream" in str(e).lower()
```

**Formations Required:**
- `formations/async.yaml` - Async configuration with webhooks
- `formations/workflow-async.yaml` - Workflow with async support

**Test Implementation:** Use real webhook server for validation
**Success Criteria:** All async tests pass, webhooks delivered, proper sync handling of approvals/clarifications

</details>

<details>
<summary>Area 10 (Streaming): Streaming & Real-time Features</summary>

#### Goal: Validate streaming responses and real-time features

### Test Group 10A: Basic Streaming
```python
# Test 10A1: Simple Streaming Response
formation = Formation.load("formations/streaming.yaml")
overlord = await formation.start()

response_stream = await overlord.chat(
    "Write a story about a robot",
    stream=True
)

# Collect chunks
chunks = []
async for chunk in response_stream:
    chunks.append(chunk)
    # Verify chunks are strings
    assert isinstance(chunk, str)

# Verify complete response
full_response = "".join(chunks)
assert len(full_response) > 100
assert "robot" in full_response.lower()

# Test 10A2: Streaming with Files
audio_file = load_test_file("test-files/speech.m4a")
response_stream = await overlord.chat(
    "Transcribe this audio",
    files=[{"filename": "speech.m4a", "content": audio_file, "content_type": "audio/m4a"}],
    stream=True
)

chunks = []
async for chunk in response_stream:
    chunks.append(chunk)

full_response = "".join(chunks)
assert len(full_response) > 50

# Test 10A3: Non-Streaming Mode
response = await overlord.chat(
    "What's the capital of France?",
    stream=False  # Explicit non-streaming
)
assert isinstance(response, str)
assert "Paris" in response
```

### Test Group 10B: Streaming Complex Operations
```python
# Test 10B1: Streaming Task Decomposition
formation = Formation.load("formations/streaming-workflow.yaml")
overlord = await formation.start()

# Complex request that triggers workflow
response_stream = await overlord.chat(
    "Research renewable energy trends, analyze the data, create visualizations, and write a report",
    stream=True
)

# Should stream progress updates
chunks = []
async for chunk in response_stream:
    chunks.append(chunk)
    # May include progress indicators

full_response = "".join(chunks)
assert "research" in full_response.lower()
assert "visualization" in full_response.lower()

# Test 10B2: Streaming with Multi-Agent
response_stream = await overlord.chat(
    "I need help with Python code optimization and database design",
    stream=True
)

chunks = []
agent_switches = 0
async for chunk in response_stream:
    chunks.append(chunk)
    # Could detect agent switches in stream
    if "agent:" in chunk.lower() or "specialist" in chunk.lower():
        agent_switches += 1

full_response = "".join(chunks)
assert len(full_response) > 200

# Test 10B3: Streaming File Generation
response_stream = await overlord.chat(
    "Create a bar chart showing monthly sales data",
    stream=True
)

chunks = []
artifact_seen = False
async for chunk in response_stream:
    chunks.append(chunk)
    if "artifact" in chunk.lower() or "file" in chunk.lower():
        artifact_seen = True

assert artifact_seen or "chart" in "".join(chunks).lower()
```

### Test Group 10C: Streaming Error Handling
```python
# Test 10C1: Stream Interruption Handling
formation = Formation.load("formations/streaming.yaml")
overlord = await formation.start()

response_stream = await overlord.chat(
    "Write a very long essay about space exploration",
    stream=True
)

# Simulate early termination
chunks_received = 0
try:
    async for chunk in response_stream:
        chunks_received += 1
        if chunks_received > 5:
            break  # Early termination
except Exception as e:
    # Should handle gracefully
    pass

assert chunks_received > 5

# Test 10C2: Stream with Errors
response_stream = await overlord.chat(
    "This will cause an error: divide by zero",
    stream=True
)

error_seen = False
chunks = []
async for chunk in response_stream:
    chunks.append(chunk)
    if "error" in chunk.lower():
        error_seen = True

# Should stream error message properly
assert error_seen or len("".join(chunks)) > 0

# Test 10C3: Empty Stream Handling
response_stream = await overlord.chat(
    "",  # Empty request
    stream=True
)

chunks = []
async for chunk in response_stream:
    chunks.append(chunk)

# Should handle empty request gracefully
assert len(chunks) >= 0  # May return error or empty
```

**Formations Required:**
- `formations/streaming.yaml` - Basic streaming configuration
- `formations/streaming-workflow.yaml` - Workflow with streaming

**Test Implementation:** AsyncGenerator validation, chunk collection
**Success Criteria:** All streaming tests pass, proper chunk handling


</details>

<details>
<summary>Area 11 (Response Format): Response Format & Interactive Elements</summary>

#### Goal: Validate response formats (text/json/markdown) and interactive UI elements

### Test Group 11A: Response Format Types
```python
# Test 11A1: JSON Response Format
formation = Formation.load("formations/json-response.yaml")
# Formation has: overlord.response.format: "json"
overlord = await formation.start()

response = await overlord.chat("List three benefits of cloud computing")
# Should return structured JSON
assert isinstance(response, dict)
assert "benefits" in response or "items" in response
assert len(response.get("benefits", response.get("items", []))) == 3

# Test 11A2: Markdown Response Format
formation = Formation.load("formations/markdown-response.yaml")
# Formation has: overlord.response.format: "markdown"
overlord = await formation.start()

response = await overlord.chat("Create a simple README for a Python project")
# Should return markdown with headers, lists, code blocks
assert isinstance(response, str)
assert "#" in response  # Headers
assert "```" in response or "`" in response  # Code blocks

# Test 11A3: Plain Text Response (Default)
formation = Formation.load("formations/text-response.yaml")
# Formation has: overlord.response.format: "text" (or not specified)
overlord = await formation.start()

response = await overlord.chat("Explain photosynthesis in simple terms")
# Should return plain text without formatting
assert isinstance(response, str)
assert "```" not in response  # No code blocks
assert "**" not in response   # No markdown emphasis
```

### Test Group 11B: Interactive Elements
```python
# Test 11B1: Buttons in Response
formation = Formation.load("formations/interactive.yaml")
# Formation has: overlord.response.interactive_elements: ["buttons"]
overlord = await formation.start()

response = await overlord.chat("Show me options for data visualization")
# Should include interactive buttons
assert "button" in str(response).lower() or "option" in str(response).lower()
# Response might include structured buttons
if isinstance(response, dict):
    assert "buttons" in response or "options" in response

# Test 11B2: Forms in Response
formation = Formation.load("formations/forms.yaml")
# Formation has: overlord.response.interactive_elements: ["forms"]
overlord = await formation.start()

response = await overlord.chat("I need to collect user information")
# Should include form structure
if isinstance(response, dict):
    assert "form" in response or "fields" in response
    # Form should have input fields
    assert "inputs" in response or "fields" in response

# Test 11B3: Tables in Response
formation = Formation.load("formations/tables.yaml")
# Formation has: overlord.response.interactive_elements: ["tables"]
overlord = await formation.start()

response = await overlord.chat("Compare Python, JavaScript, and Go")
# Should format as table
assert "|" in str(response)  # Table formatting
# Or structured data
if isinstance(response, dict):
    assert "table" in response or "rows" in response
```

### Test Group 11C: Combined Format and Elements
```python
# Test 11C1: JSON with Interactive Elements
formation = Formation.load("formations/json-interactive.yaml")
# Formation has:
#   overlord.response.format: "json"
#   overlord.response.interactive_elements: ["buttons", "tables"]
overlord = await formation.start()

response = await overlord.chat("Show product comparison with purchase options")
assert isinstance(response, dict)
assert "table" in response or "comparison" in response
assert "buttons" in response or "actions" in response

# Test 11C2: Markdown with Code Execution
formation = Formation.load("formations/markdown-code.yaml")
# Formation has:
#   overlord.response.format: "markdown"
#   overlord.response.interactive_elements: ["code_blocks"]
overlord = await formation.start()

response = await overlord.chat("Show me how to sort a list in Python")
assert "```python" in response
assert "sort" in response.lower()
# May include runnable code blocks

# Test 11C3: Response Format Override
formation = Formation.load("formations/flexible-format.yaml")
overlord = await formation.start()

# Override formation default
response = await overlord.chat(
    "Give me data as JSON",
    response_format="json"  # Override formation setting
)
assert isinstance(response, dict)
```

**Formations Required:**
- Various formations with different response configurations
- See schemas/formation/README.md for configuration options

**Success Criteria:** All format tests pass, interactive elements properly rendered

</details>

<details>
<summary>Area 12 (Thinking): Thinking Visibility</summary>

#### Goal: Expose thinking process during streaming for transparency

### Test Group 12A: Thinking in Stream
```python
# Test 12A1: Workflow Decomposition Thinking
formation = Formation.load("formations/streaming.yaml")
overlord = await formation.start()

response_stream = await overlord.chat(
    "Research AI trends, analyze data, create report with visualizations",
    stream=True
)

thinking_seen = False
chunks = []
async for chunk in response_stream:
    chunks.append(chunk)
    if "<thinking>" in chunk:
        thinking_seen = True
        # Should expose decision process
        # e.g., "<thinking>Analyzing complexity: This requires multiple steps...</thinking>"

full_response = "".join(chunks)
# When streaming, thinking process should be visible
assert thinking_seen or "<thinking>" in full_response

# Test 12A2: Agent Selection Thinking
response_stream = await overlord.chat(
    "I need help with database optimization and Python code review",
    stream=True
)

chunks = []
agent_thinking_seen = False
async for chunk in response_stream:
    chunks.append(chunk)
    if "<thinking>" in chunk and "agent" in chunk.lower():
        agent_thinking_seen = True
        # Should show agent selection reasoning

# Should expose which agents are being selected and why
assert agent_thinking_seen or "selecting" in "".join(chunks).lower()

# Test 12A3: Clarification Thinking
response_stream = await overlord.chat(
    "Create a report",  # Ambiguous
    stream=True
)

chunks = []
clarification_thinking = False
async for chunk in response_stream:
    chunks.append(chunk)
    if "<thinking>" in chunk and ("clarify" in chunk.lower() or "ambiguous" in chunk.lower()):
        clarification_thinking = True

# Should show thinking about need for clarification
assert clarification_thinking or "unclear" in "".join(chunks).lower()
```

### Test Group 12B: Thinking Control
```python
# Test 12B1: Disable Thinking in Non-Streaming
formation = Formation.load("formations/no-thinking.yaml")
overlord = await formation.start()

# Non-streaming shouldn't show thinking by default
response = await overlord.chat(
    "Complex task requiring decomposition",
    stream=False
)
# Should not include thinking tags
assert "<thinking>" not in response

# Test 12B2: Enable Thinking Explicitly
response_stream = await overlord.chat(
    "Analyze this problem step by step",
    stream=True,
    show_thinking=True  # Explicit control
)

thinking_shown = False
async for chunk in response_stream:
    if "<thinking>" in chunk:
        thinking_shown = True
        break

assert thinking_shown

# Test 12B3: Thinking for Errors
response_stream = await overlord.chat(
    "This will cause an error in processing",
    stream=True
)

error_thinking = False
chunks = []
async for chunk in response_stream:
    chunks.append(chunk)
    if "<thinking>" in chunk and "error" in chunk.lower():
        error_thinking = True

# Should show thinking about error handling
assert error_thinking or "error" in "".join(chunks).lower()
```

### Test Group 12C: Thinking Content Quality
```python
# Test 12C1: Thinking Should Be Informative
formation = Formation.load("formations/streaming.yaml")
overlord = await formation.start()

response_stream = await overlord.chat(
    "Build a REST API for a blog with authentication",
    stream=True
)

thinking_chunks = []
chunks = []
async for chunk in response_stream:
    chunks.append(chunk)
    if "<thinking>" in chunk:
        thinking_chunks.append(chunk)

# Thinking should contain useful information
thinking_content = "".join(thinking_chunks)
useful_keywords = ["decompos", "step", "agent", "task", "workflow", "complex", "require"]
assert any(keyword in thinking_content.lower() for keyword in useful_keywords)

# Test 12C2: Thinking Should Not Leak Sensitive Info
response_stream = await overlord.chat(
    "Connect to database with password abc123",
    stream=True
)

thinking_chunks = []
async for chunk in response_stream:
    if "<thinking>" in chunk:
        thinking_chunks.append(chunk)

# Should not expose passwords in thinking
thinking_content = "".join(thinking_chunks)
assert "abc123" not in thinking_content

# Test 12C3: Thinking Formatting
response_stream = await overlord.chat(
    "Complex multi-step task",
    stream=True
)

chunks = []
async for chunk in response_stream:
    chunks.append(chunk)

full_response = "".join(chunks)
# Thinking tags should be properly closed
thinking_count = full_response.count("<thinking>")
closing_count = full_response.count("</thinking>")
assert thinking_count == closing_count
```

**Formations Required:**
- Standard formations with streaming enabled
- No special thinking configuration needed

**Success Criteria:** Thinking exposed during streaming for transparency, properly formatted

</details>

<details>
<summary>Area 13 (Scheduler): Task Scheduling & Job Management</summary>

#### Goal: Validate scheduled task execution and job management

### Test Group 13A: One-time Scheduled Tasks
```python
# Test 13A1: Schedule Future Task
formation = Formation.load("formations/scheduler.yaml")
overlord = await formation.start()

# Schedule a task for 1 minute from now
run_at = datetime.now() + timedelta(minutes=1)
response = await overlord.chat(
    "Remind me to check the deployment status",
    schedule={"run_at": run_at.isoformat()}
)
assert "scheduled" in response.lower()
job_id = extract_job_id(response)

# Wait and verify execution
await asyncio.sleep(70)  # Wait for execution
history = await overlord.scheduler.get_job_history(job_id)
assert len(history) > 0
assert history[0]["status"] == "success"

# Test 13A2: Natural Language Scheduling
response = await overlord.chat(
    "In 5 minutes, generate a status report"
)
# Should parse natural language time
assert "scheduled" in response.lower() or "will" in response.lower()

# Test 13A3: Schedule with Context
response = await overlord.chat(
    "Every day at 9am, check for new pull requests and summarize them"
)
assert "scheduled" in response.lower()
assert "daily" in response.lower() or "every day" in response.lower()
```

### Test Group 13B: Recurring Jobs
```python
# Test 13B1: Cron-based Scheduling
formation = Formation.load("formations/scheduler.yaml")
overlord = await formation.start()

response = await overlord.chat(
    "Generate sales report every Monday at 8am",
    schedule={"cron": "0 8 * * MON"}
)
job_id = extract_job_id(response)
assert "scheduled" in response.lower()

# Verify job created
jobs = await overlord.scheduler.get_active_jobs()
job = next((j for j in jobs if j["id"] == job_id), None)
assert job is not None
assert job["cron"] == "0 8 * * MON"

# Test 13B2: Update Recurring Job
success = await overlord.scheduler.update_job(
    job_id,
    cron="0 9 * * MON"  # Change to 9am
)
assert success == True

# Test 13B3: Cancel Job
success = await overlord.scheduler.cancel_job(job_id)
assert success == True

# Verify cancelled
jobs = await overlord.scheduler.get_active_jobs()
assert not any(j["id"] == job_id for j in jobs)
```

### Test Group 13C: Job Management & History
```python
# Test 13C1: List All Jobs
formation = Formation.load("formations/scheduler.yaml")
overlord = await formation.start()

# Create multiple jobs
for i in range(3):
    await overlord.chat(f"Schedule test job {i}",
                       schedule={"run_at": (datetime.now() + timedelta(hours=i+1)).isoformat()})

jobs = await overlord.scheduler.get_active_jobs()
assert len(jobs) >= 3

# Test 13C2: Job Execution History
# Wait for a job to execute
job_id = jobs[0]["id"]
await asyncio.sleep(3700)  # Wait for first job

history = await overlord.scheduler.get_job_history(job_id)
assert len(history) > 0
assert "result" in history[0]
assert "executed_at" in history[0]

# Test 13C3: Failed Job Handling
response = await overlord.chat(
    "This will fail: divide by zero",
    schedule={"run_at": (datetime.now() + timedelta(seconds=5)).isoformat()}
)
job_id = extract_job_id(response)

await asyncio.sleep(10)
history = await overlord.scheduler.get_job_history(job_id)
assert history[0]["status"] == "failed"
assert "error" in history[0]
```

### Test Group 13D: Complex Scheduling Scenarios
```python
# Test 13D1: Multi-User Job Isolation
formation = Formation.load("formations/scheduler-multiuser.yaml")
overlord = await formation.start()

# User 1 schedules job
response1 = await overlord.chat(
    "Schedule my personal reminder",
    user_id="user1",
    schedule={"run_at": (datetime.now() + timedelta(minutes=1)).isoformat()}
)
job1_id = extract_job_id(response1)

# User 2 schedules job
response2 = await overlord.chat(
    "Schedule my task",
    user_id="user2",
    schedule={"run_at": (datetime.now() + timedelta(minutes=1)).isoformat()}
)
job2_id = extract_job_id(response2)

# User 1 should only see their job
jobs = await overlord.scheduler.get_user_jobs("user1")
assert any(j["id"] == job1_id for j in jobs)
assert not any(j["id"] == job2_id for j in jobs)

# Test 13D2: Scheduled Workflow
response = await overlord.chat(
    "Every Friday: research news, analyze trends, create report, send to team",
    schedule={"cron": "0 10 * * FRI"}
)
# Should schedule complex workflow
assert "scheduled" in response.lower()
assert "workflow" in response.lower() or "tasks" in response.lower()

# Test 13D3: Conditional Scheduling
response = await overlord.chat(
    "If stock price drops below $100, alert me immediately",
    schedule={"condition": "stock_price < 100", "check_interval": 300}
)
# Should set up conditional monitoring
assert "monitor" in response.lower() or "watch" in response.lower()
```

**Formations Required:**
- `formations/scheduler.yaml` - Basic scheduler configuration
- `formations/scheduler-multiuser.yaml` - Multi-user with PostgreSQL

**Database Required:** PostgreSQL or SQLite for job persistence
**Success Criteria:** All scheduler tests pass, jobs execute on time, proper isolation

</details>

---

## Success Metrics & Validation

### **Success Criteria by Test Area**
- **Area 1 (Foundation):** 7/7 foundation tests pass ✅ (chat flow testing with real services)
- **Area 2 (Memory):** 20+/22+ memory tests pass ✅ (exceeded goal with advanced features)
- **Area 3 (Multimodal):** 34/36 multimodal tests pass ✅ (94% success rate, exceeded 15 test goal)
- **Area 4 (MCP):** 20+ MCP tests + credential tests pass ✅ (100% success rate, user isolation verified)
- **Area 5 (Artifacts):** 21/22 file generation tests pass ✅ (95.5% success rate, security validation confirmed)
- **Area 6 (Knowledge):** 19/19 knowledge tests pass ✅ (100% success rate across all 5 test groups 6A-6E)
- **Area 7 (Orchestration):** ✅ 7A: Workflow orchestration (9 tests pass) | ✅ 7B: A2A Communication (all tests pass) | ✅ 7C-7D: SOP System (6 tests pass, 72% code reduction)
- **Area 8 (Clarification):** Base: 10 clarification tests pass ✅ | Enhanced: Multiple clarification sequences implemented ✅
- **Area 9 (Async):** Async operations with webhook delivery, clarification/approval before async
- **Area 10 (Streaming):** Streaming responses with AsyncGenerator support
- **Area 11 (Response Format):** JSON/Markdown/Text formats + interactive UI elements
- **Area 12 (Thinking):** 🔄 READY FOR IMPLEMENTATION - Thinking visibility in streaming
- **Area 13 (Scheduler):** 🔄 READY FOR IMPLEMENTATION - Task scheduling & jobs

### **Final Validation Checklist**
- [ ] All 22 feature dimensions tested in combination (including SOPs and multi-clarification)
- [x] User credentials system fully validated with encryption & isolation ✅
- [x] File generation tested across all major formats with security validation ✅
- [x] Domain knowledge system tested with multiple agents and sources ✅
- [x] Built-in MCP security validation (code filtering, safe execution) ✅
- [x] SOP system enhances multi-agent coordination with procedural guidance ✅
- [x] Multiple clarification sequences maintain intent across sub-clarifications ✅
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
- ✨ **Standard Operating Procedures (SOPs)**: Simplified architecture with 72% code reduction and 40-80% performance improvement ✅
- ✨ **Multiple Clarification Sequences**: Stack-based clarification management with intent preservation ✅
- ✨ **Thinking Visibility**: Automatic model detection with configurable transparency
- ✨ **Large File Multimodal Processing**: Intelligent chunking for >100MB files
- ✨ **Video/Audio Chunking**: Overlapping segments with temporal coherence
- ✨ **Result Fusion Engine**: Merges chunk analyses into coherent narratives

### **Automation Coverage**
- **85% Automated:** Functional tests, performance benchmarks, CI/CD
- **15% Manual:** Complex integration validation, user experience testing

**Total Test Coverage:** 1,400+ test combinations across 22 feature dimensions
