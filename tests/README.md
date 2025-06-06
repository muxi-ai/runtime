# MUXI Runtime Tests Organization

This directory contains all tests for the MUXI Runtime, organized by functional area for better maintainability and discoverability.

## 📁 Directory Structure

### Core Functional Tests

- **`schema_validation/`** - Schema compliance and validation tests
  - SCHEMA_GUIDE.md compliance tests
  - Formation, agent, MCP, and A2A validation
  - Phase 6 comprehensive validation suite

- **`a2a/`** - Agent-to-Agent communication tests
  - A2A protocol implementation
  - Authentication and authorization
  - Registry and discovery
  - Inter-agent collaboration

- **`memory/`** - Memory system tests
  - Buffer memory (local/remote FAISS)
  - Long-term memory (PostgreSQL/SQLite)
  - Memory integration and performance

- **`mcp/`** - Model Context Protocol tests
  - MCP server implementations
  - Tool calling and reconnection
  - Transport layer testing

- **`overlord/`** - Overlord orchestrator tests
  - Intelligent routing
  - Agent management
  - System orchestration

- **`agents/`** - Agent lifecycle and behavior tests
  - Agent creation and configuration
  - Agent knowledge systems
  - Agent collaboration patterns

### Configuration & Integration

- **`configuration/`** - Configuration loading and validation
  - Formation integration
  - Logging configuration
  - Config file processing

- **`secrets/`** - Secrets management tests
  - Secrets interpolation
  - Secure configuration handling
  - Authentication token management

- **`integration/`** - End-to-end integration tests
  - Full system integration
  - Task completion workflows
  - Cross-component testing

### Utilities & Archive

- **`utils/`** - Utility and service tests
  - Enhanced LLM services
  - Knowledge handlers
  - Extraction utilities

- **`archive/`** - Legacy, debug, and temporary tests
  - Debug utilities
  - Deprecated test files
  - Development artifacts

## 🧪 Test Categories

### Active Test Suites
- **Schema Validation**: Comprehensive SCHEMA_GUIDE.md compliance
- **A2A Communication**: Full agent-to-agent protocol testing
- **Memory Systems**: Buffer and long-term memory validation
- **MCP Integration**: Model Context Protocol functionality
- **Configuration**: Formation and agent configuration testing

### Archived Tests
- Debug utilities and temporary test files
- Legacy test implementations
- Development artifacts and demos

## 🚀 Running Tests

### By Category
```bash
# Run all schema validation tests
pytest runtime/tests/schema_validation/

# Run A2A communication tests
pytest runtime/tests/a2a/

# Run memory system tests
pytest runtime/tests/memory/

# Run MCP tests
pytest runtime/tests/mcp/
```

### Comprehensive Testing
```bash
# Run all runtime tests
pytest runtime/tests/ --ignore=runtime/tests/archive/

# Run with coverage
pytest runtime/tests/ --cov=runtime/muxi/runtime --ignore=runtime/tests/archive/
```

## 📊 Test Statistics

- **Total Test Files**: ~130+ organized test files
- **Schema Validation**: 12 comprehensive test suites
- **A2A Communication**: 27 test files covering full protocol
- **Memory Systems**: 11 test files for all memory types
- **MCP Integration**: 17 test files for protocol compliance
- **Active Test Coverage**: All major runtime components

## 🔧 Maintenance

### Adding New Tests
1. Place tests in the appropriate functional directory
2. Follow naming convention: `test_[component]_[feature].py`
3. Update this README if adding new categories

### Cleaning Up
- Archive old/deprecated tests in `archive/`
- Remove debug files after development
- Keep active test suites focused and maintainable

---

This organization ensures that tests are:
- **Discoverable**: Easy to find tests for specific components
- **Maintainable**: Logical grouping reduces maintenance overhead
- **Focused**: Each directory has a clear purpose and scope
- **Comprehensive**: Full coverage of runtime functionality
