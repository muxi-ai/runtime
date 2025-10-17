---
created: 2025-08-21T17:31:00Z
last_updated: 2025-10-17T12:23:10Z
version: 1.7
author: Claude Code PM System
---

# MUXI Runtime Project Structure

This document describes the current structure of the MUXI Runtime repository - the core execution engine that powers AI agent formations.

## Overview

MUXI Runtime is organized as a Python package with comprehensive test coverage and documentation:

```
runtime/
├── src/muxi/runtime/      # Core runtime engine
├── tests/                 # Unit and integration tests
├── e2e/                   # Complete E2E testing environment
│   ├── tests/            # 215+ E2E test files across 12 areas
│   ├── docker/           # Docker configurations for testing
│   ├── scripts/          # Test runner scripts
│   ├── utils/            # Testing utilities (async cleanup, webhook, A2A registry)
│   └── fixtures/         # Test data and formations
├── docs/                  # Documentation
├── test-formations/       # Example formations
├── schemas/               # YAML schema definitions
├── examples/              # Usage examples
└── migrations/            # Database migrations
```

## Source Code Structure (`src/muxi/runtime/`)

### Data Types (`datatypes/`)
Core data structures and type definitions used throughout the runtime:
- `artifacts.py` - Artifact system types
- `async_operations.py` - Async operation enums and structures
- `clarification.py` - Streamlined clarification types (removed 4 unused dataclasses Dec 2025)
- `mcp.py` - MCP protocol message formats
- `memory.py` - Memory system data types
- `observability.py` - Event streaming structures
- `resilience.py` - Fault tolerance types
- `workflow.py` - Workflow execution types

### Extensions (`extensions/`)
Runtime extensions and loadable modules:
- `sqlite-vec/` - SQLite vector extension binaries for all platforms
- `base.py` - Extension loading interface
- `sqlite_vec.py` - Python interface for vector operations

### Formation Management (`formation/`)
Core formation orchestration and lifecycle:

#### Agents (`agents/`)
- `agent.py` - Base agent implementation with specialization
- `knowledge/` - Domain knowledge system with MarkItDown

#### Services & Features
- `artifacts/` - Built-in file generation system
- `background/` - Async operations and webhooks
- `config/` - Configuration loading and validation
- `credentials/` - User credential storage and encryption (Issue #53)
- `documents/` - Document processing and chunking
- `memory/` - Memory coordination and user context
- `overlord/` - Central orchestration with SOP guidance (includes unified clarification system)
- `prompts/` - Centralized prompt management (16 markdown files + PromptLoader utility)
- `resilience/` - Circuit breakers and recovery
- `workflow/` - Task decomposition and synthesis (includes SOPs)

### Services (`services/`)
Unified service architecture:

#### Core Services
- `a2a/` - Agent-to-agent communication protocol
- `intent/` - Intent detection and routing
- `llm/` - OneLLM integration layer
- `memory/` - Three-tier memory implementation
- `multimodal/` - Image/audio/video processing (cleaned Dec 2025: removed MultiModalWorkflowIntegrator)
- `observability/` - Event streaming (10 formatters, 4 transports, custom asyncio handler)
- `streaming.py` - Streaming events system with fire-and-forget pattern
- `scheduler/` - Natural language task scheduling (cleaned Dec 2025: removed MultiLLMCircuitBreaker)
- `secrets/` - Encrypted credential management

#### MCP Service (`mcp/`)
Complete Model Context Protocol implementation:
- `built_in/` - File Generation MCP server
- `protocol/` - JSON-RPC message handling
- `transports/` - Command, HTTP/SSE, streamable
- `tools/` - Tool discovery and execution
- `health/` - Server health monitoring
- `resources/` - Resource management

### Utilities (`utils/`)
Shared utility functions:
- `async_operation_manager.py` - Async coordination
- `id_generator.py` - Nano ID generation
- `user_dirs.py` - User directory management
- `dependency_validator.py` - Dependency checking
- `response_converter.py` - Response formatting

## Test Structure (`tests/`)

Comprehensive test coverage organized by feature:

### Area-Based Testing (`e2e/`)
- `1_foundation/` - Foundation layer (formation loading, basic chat)
- `2_memory/` - Memory systems (buffer, persistent, vector)
- `3_multimodal/` - Multimodal processing (images, audio, documents)
- `4_mcp/` - MCP integration and user credentials
- `5_artifacts/` - File generation MCP (artifacts system)
- `6_knowledge/` - Knowledge system with smart caching
- `7_orchestration/` - Workflow orchestration and A2A communication
- `8_clarification/` - Intelligent clarification flows
- `9_async/` - Async decision logic and request lifecycle management (Group 9A & 9B)
- `10_streaming/` - Streaming events with fire-and-forget pattern (Group 10A)

### Feature Tests
- `a2a/` - Agent communication tests
- `async/` - Legacy async operation tests
- `clarification/` - Parameter collection tests
- `scheduler/` - Task scheduling tests
- `observability/` - Event streaming tests
- `integration/` - End-to-end tests
- `api/` - Formation API server tests with OpenAPI compliance verification

### Group 9 Async Operations (`9_async/`)
Comprehensive testing of async decision logic and request lifecycle:
- `formation-async/` - Test formation with async webhook configuration
- `test_9a1_forced_async_mode.py` - Force async parameter testing
- `test_9a3b_with_approval.py` - Async workflow with approval requirements
- `test_9a4_no_webhook_yaml_passed_chat.py` - Webhook override in chat method
- `test_9a5_webhook_yaml_override_chat.py` - YAML webhook configuration
- `test_9b1_request_lifecycle.py` - Request status tracking and cancellation APIs
- `run_async_tests.py` - Test suite runner

### Test Reports
- `reports/` - Detailed test execution reports by day

## Documentation (`docs/`)

Comprehensive documentation covering all aspects:

### Guides
- `configuration/` - Formation YAML configuration
- `features/` - Feature-specific documentation
- `mcp/` - MCP server development
- `scheduler/` - Scheduling system guide

### Audits
- `audits/phase-2-observability/` - Complete Phase 2 observability audit (Oct 2025)
  - 12 comprehensive documents covering all 4 phases
  - Event refactoring details (12 new events, 32 enhanced metadata fields)
  - Testing and validation results
  - Organized from root for cleaner project structure

### References
- `knowledge-system.md` - Domain knowledge architecture
- `memory-systems.md` - Three-tier memory design
- `artifacts.md` - File generation system
- `observability.md` - Event streaming guide
- `multi-user-architecture.md` - Multi-tenant design
- `user-credentials-flow.md` - Credential handling system (Issue #53)
- `request-lifecycle.md` - Complete request processing flow

## E2E Testing Suite (`e2e/`)

Complete end-to-end testing environment with 215+ tests across 12 areas:

### Test Areas (`e2e/tests/`)
- `1_foundation/` - Formation loading and basic chat (10 tests)
- `2_memory/` - Memory systems testing (26 tests)
- `3_multimodal/` - Image, audio, video processing (38 tests)
- `4_mcp/` - Model Context Protocol tools (24 tests)
- `5_artifacts/` - File generation (15 tests)
- `6_knowledge/` - Knowledge base operations (19 tests)
- `7_orchestration/` - Multi-agent coordination (25 tests)
- `8_clarification/` - Clarification flows (49 tests)
- `9_async/` - Async operations (12 tests)
- `10_streaming/` - Response streaming (6 tests)
- `11_formatting/` - Output formatting (4 tests)
- `12_scheduling/` - Task scheduling (11 tests)
- `common/` - Shared test utilities and base classes

### Infrastructure (`e2e/docker/`)
- `Dockerfile.e2e-all-in-one` - Single container with all services
- `docker-compose.all-in-one.yml` - Complete test environment
- `docker-compose.e2e.yml` - Full service stack
- `docker-compose.test-minimal.yml` - Basic services only

### Scripts (`e2e/scripts/`)
- `test-in-docker.sh` - Run tests in Docker with simple commands
- `run-e2e-tests.sh` - Run tests with service orchestration

### Utilities (`e2e/utils/`)
- `async_cleanup.py` - Custom asyncio event loop handler for test cleanup
- `README.md` - Documentation for testing utilities
- Additional test utilities (webhook server, A2A registry)

## Example Formations (`test-formations/`)

Ready-to-use formation examples:
- `formation-basic/` - Simple single-agent setup
- `formation-knowledge/` - Agent with domain knowledge
- `formation-mcp/` - MCP tool integration
- `formation-multi-agent/` - Multiple specialized agents
- `formation-file-generation/` - Artifacts system usage

## Configuration Files

### Python Project
- `pyproject.toml` - Modern Python project configuration
- `requirements.txt` - Direct dependencies
- `uv.lock` - Locked dependency versions
- `pyrightconfig.json` - Type checking configuration

### Development
- `.flake8` - Code style configuration
- `pytest.ini` - Test runner configuration
- `CLAUDE.md` - Development notes and context

### Documentation
- `README.md` - Project overview and quickstart
- `tests/Comprehensive_Test_Plan.md` - Testing strategy
- `tests/Lessons-Learned.md` - Testing best practices

## Key Architectural Patterns

1. **Formation-First**: Everything starts with a YAML formation
2. **Service-Oriented**: Unified service architecture for all features
3. **Test-Driven**: Comprehensive test coverage with real services
4. **Type-Safe**: Full type annotations throughout
5. **Async-First**: Non-blocking I/O for performance

## Development Workflow

1. **Formation Definition**: Create YAML configuration
2. **Load & Validate**: Formation engine validates and loads
3. **Start Overlord**: Central orchestrator manages agents
4. **Process Messages**: Intent routing to specialized agents
5. **Tool Execution**: MCP protocol for external tools
6. **Memory Management**: Automatic context handling

This structure supports the "container runtime for AI agents" vision with clear separation of concerns and production-ready features.

## Update History
- 2025-10-08: Added e2e/utils/ documentation section with async cleanup utilities
- 2025-10-08: Updated observability service description to note custom asyncio handler
- 2025-09-19: Added prompts/ directory with 16 externalized prompts and PromptLoader utility
