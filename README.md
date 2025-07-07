# MUXI Runtime

> The computational engine that powers formation execution in the MUXI AI Server and enables direct deployment in embedded systems.

## Overview

MUXI Runtime is the foundational execution engine of the MUXI Framework, serving as the computational core that runs AI agent formations. It provides a comprehensive set of abstractions and utilities for building, deploying, and managing complex AI agent systems both within the MUXI Server and as a standalone embedded runtime.

Think of MUXI Runtime as analogous to the Docker Runtime - it's the powerful engine that executes formation definitions (YAML configs) as live AI systems, while the MUXI Server acts as the "Docker daemon" handling HTTP, routing, authentication, and formation lifecycle management.

**Dual Deployment Model:**
- **Server Integration**: Powers formation execution within the MUXI AI Server
- **Embedded Systems**: Runs directly in applications for local AI agent capabilities

## Recent Architecture Improvements

### MCP SDK Migration & Authentication ✅ **PRODUCTION READY**
- **Official SDK Integration**: Complete migration to MCP Python SDK with streamable HTTP and SSE transport support
- **Authentication Resolution**: Fixed Linear MCP 401 errors with proper Bearer token authentication and GitHub Copilot MCP integration
- **Auto-Fallback Transport**: Intelligent fallback from streamable HTTP to SSE with formation-lifetime caching
- **Initialization Credentials**: Fail-fast validation system for MCP tool discovery during formation startup
- **User-Specific Credentials**: Dynamic user credential resolution (`${{ user.credentials.service }}`) with database storage
- **Agent Tool Call Chaining**: Intelligent tool execution loop enabling agents to automatically recover from errors and complete complex multi-step operations
- **Command-Based MCP Support**: Enhanced YAML command/args configuration for filesystem and local MCP servers
- **Thread Safety**: Comprehensive locking mechanisms and secure credential handling
- **Production Ready**: All MCP server types working (HTTP, SSE, Command-line) with 105+ tools across multiple servers

### Async Performance & Architecture ✅ **PRODUCTION READY**
- **Async SQLAlchemy Migration**: Complete migration achieving 3x database performance improvement with dual database support (PostgreSQL + SQLite)
- **Formation API Async Conversion**: All 208 tests migrated to async patterns with Formation core methods converted to async
- **Event Loop Safety**: Proper asyncio.run() management and atexit handling for reliable async operations
- **Connection Pooling**: Production-optimized configuration (20 pool_size, 40 max_overflow) for high-throughput deployments
- **Comprehensive Async Coverage**: All memory services, scheduler, and database operations using async patterns

### Intelligent Agent Capabilities ✅ **PRODUCTION READY**
- **Agent Tool Call Chaining**: Multi-iteration tool execution with intelligent error recovery, progress detection, and alternative approach exploration
- **User Credential Management**: Runtime resolution of user-specific credentials with clarification flow for missing credentials
- **MCP Authentication Patterns**: Support for formation-level and user-level credential isolation with automatic resolution
- **Error Recovery Intelligence**: Agents can automatically create directories, search for files, try alternative locations, and explain limitations
- **Safety Mechanisms**: Iteration limits, progress detection, retry prevention, and timeout protection prevent infinite loops

### File Generation MCP ✅ **PRODUCTION READY**
- **Built-in MCP Server**: Comprehensive file generation capabilities through secure Python code execution
- **Multi-Format Support**: Charts (matplotlib), documents (docx, PDF), spreadsheets (Excel, CSV), images (PIL, QR codes), presentations (pptx)
- **Security First**: AST-based code validation with whitelist of allowed libraries, no exec/eval allowed
- **Sandboxed Execution**: Subprocess isolation with 30-second timeout, restricted to `outputs/` directory, no network access
- **Auto-Registration**: Built-in MCPs automatically register at formation startup with granular configuration control
- **Dynamic System Prompts**: Automatic augmentation of agent prompts with file generation instructions and examples
- **Formation Integration**: Support for both simple boolean and granular array configuration modes via `runtime.built_in_mcps`
- **Production Ready**: Complete dependency management, testing infrastructure, comprehensive error handling

### Multilingual Intent Detection System ✅ **PRODUCTION READY**
- **Intelligent Intent Recognition**: LLM-based intent detection system supporting 8 intent types with natural language processing
- **Language-Agnostic Processing**: Native multilingual support through LLM capabilities, eliminating hardcoded keyword dependencies
- **Performance Optimization**: IntentCache with LRU eviction and TTL for efficient request handling and reduced LLM calls
- **System Integration**: Successfully integrated across multiple components including agent query routing, scheduler job detection, and document error classification
- **Comprehensive Intent Types**: QUERY_TYPE, CLARIFICATION_CATEGORY, SCHEDULE_TYPE, CONTENT_CATEGORY, ERROR_TYPE, LEARNING_INTENT, PROACTIVE_REQUEST, MESSAGE_TYPE
- **Fallback Architecture**: Graceful degradation to simple heuristics when LLM unavailable, ensuring system reliability
- **Production Ready**: Complete type definitions, comprehensive testing, and observability integration

### Task Scheduling System ✅ **PRODUCTION READY**
- **Dual Job Types**: Supports both recurring workflows ("check email every hour") and one-time scheduled tasks ("remind me tomorrow at 2pm") with intelligent detection
- **Natural Language Scheduling**: Users schedule tasks conversationally using phrases like "check my email every hour for messages from my wife" or "remind me to call mom tomorrow at 2pm"
- **Proactive AI**: Transforms MUXI from reactive assistant into active digital assistant that executes tasks on schedule
- **Unified Database Architecture**: Shared database infrastructure between scheduler and memory services with auto-detection (PostgreSQL/SQLite)
- **Smart Datetime Parsing**: LLM-powered conversion of natural language to specific datetimes with timezone awareness and UTC storage
- **Formation Integration**: Full lifecycle integration with Formation/Overlord architecture with configuration validation
- **Context Preservation**: Maintains user context and permissions across scheduled executions with session-based isolation (`f"job_{job.id}"`)
- **Automatic Completion**: One-time jobs automatically complete and clean up after execution
- **Security Hardened**: All critical security vulnerabilities eliminated with comprehensive input validation and resource limits
- **Performance Optimized**: Intelligent caching reduces LLM usage by 70%+, scales to 10,000+ jobs with constant memory usage
- **Enterprise Features**: Complete audit trail system, Formation API exposure, comprehensive documentation

### Code Quality & Architecture Improvements ✅ **COMPLETED**
- **Pydantic V2 Migration**: All configuration models migrated with modern validators, zero deprecation warnings
- **Configuration Standardization**: Unified schema architecture eliminating duplication across services
- **Comprehensive Linting**: All code now passes flake8 standards with consistent style guidelines
- **Enhanced Type Safety**: 80% reduction in `Dict[str, Any]` usage with specific TypedDict definitions
- **Resilience Patterns**: LLM failover capabilities with automatic retry and fallback mechanisms
- **Performance Monitoring**: Integrated performance metrics and intelligent caching systems

### Formation-Overlord Separation ✅ **COMPLETED**
- **Clean Separation**: Formation handles operational lifecycle, Overlord focuses on intelligent decision-making
- **Hot Agent Management**: Add/remove agents during runtime without formation restart
- **Service Handoff**: Formation creates and configures services, then hands them to Overlord
- **Breaking Changes**: Legacy direct Overlord instantiation removed for cleaner architecture

### Services Consolidation ✅ **COMPLETED**
- **Multimodal Migration**: Moved multimodal capabilities to unified services architecture
- **Datatype Consolidation**: Unified data structures across all services
- **Service Directory**: All reusable components organized in `src/muxi/runtime/services/`
- **Clean Dependencies**: Eliminated backward compatibility layers

### ZeroMQ Token + Encryption ✅ **COMPLETED**
- **Format-Agnostic Encryption**: Works before message serialization with any format (msgpack/jsonl/protobuf)
- **Auto-Detection**: Automatic encryption for `token + tcp://` configurations
- **Production-Ready**: 45/45 tests passing with comprehensive error handling
- **Architecture**: `Raw Event → TokenEncryption → Format → ZMQ Send`
- **Backward Compatibility**: Zero breaking changes to existing functionality

### Hot Agent Deployment ✅ **READY**
- **Runtime Agent Management**: Add/remove agents without formation restart
- **State Preservation**: Maintain all existing traces, sessions, and memory state
- **Validation Pipeline**: Comprehensive agent validation before deployment
- **Rollback Capability**: Safe removal and error recovery

### Backward Compatibility Removal ✅ **COMPLETED**
- **Legacy API Elimination**: Removed all deprecated patterns and APIs for cleaner codebase
- **Architectural Simplification**: No more legacy support burden, pure modern architecture
- **Breaking Changes**: Full commitment to new Formation-Services-Overlord paradigm
- **Development Velocity**: Faster iteration without compatibility constraints

### Architectural Transformation Summary ✅ **COMPLETED**
The MUXI Runtime has undergone a complete architectural transformation:

| **Legacy Architecture** | **New Architecture** |
|------------------------|---------------------|
| Direct Overlord instantiation | Formation-managed lifecycle |
| Synchronous database operations | **Async SQLAlchemy with 3x performance** |
| Monolithic agent capabilities | Unified services architecture |
| Scattered multimodal code | Consolidated multimodal services |
| Fragmented data types | Unified datatypes package |
| Backward compatibility burden | Clean, modern APIs only |
| Static agent management | Hot agent deployment |
| Manual task management | Intelligent task scheduling |
| External-only MCP servers | Built-in MCP servers with auto-registration |

## Latest System Enhancements

### Formation ID Multi-Formation Support ✅ **COMPLETED**
- **Complete Data Isolation**: Added formation-level data isolation to all memory systems (buffer memory, PostgreSQL persistent memory, and SQLite memory)
- **Database Schema Enhancement**: Added `formation_id` and `formation_id_hash` columns to all database tables with automatic filtering
- **SHA256 Hashing**: Efficient database indexing with consistent 64-character strings regardless of formation_id length
- **Automatic Propagation**: Formation_id automatically flows from Formation YAML to all memory services
- **Production Migration**: Database migration system with backward compatibility and default formation support

### Service Architecture Revolution ✅ **COMPLETED**
- **Initialization Transformation**: **Comprehensive service initialization moved from Overlord to Formation** - the key architectural change that centralizes operational lifecycle management
- **Formation-Managed Infrastructure**: Formation now handles all configuration, initialization, and infrastructure setup while Overlord focuses on intelligent decision-making
- **Clean Architectural Separation**: Clear separation of concerns with Formation managing operations and Overlord managing intelligence
- **Enhanced Service Orchestration**: Formation creates and configures services, then hands them to Overlord for intelligent coordination
- **Hot Agent Management**: Add/remove agents during runtime without formation restart capability maintained

### Enhanced Observability System ✅ **COMPLETED**
- **Comprehensive Documentation**: Complete observability system documentation with production-ready configuration examples
- **Event Handling Improvements**: Advanced multitasking support with better resource management
- **Request Context Management**: Sophisticated session_id and request_id tracking throughout the system
- **Logger Configuration**: Enhanced debugging capabilities with improved configuration management
- **Webhook Integration**: Robust error handling and retry mechanisms for reliable webhook delivery
- **Event Emission**: Detailed context capture with comprehensive metadata support

### Multimodal Processing Evolution ✅ **COMPLETED**
- **Multimodal Agent Framework**: Complete testing infrastructure for multimodal functionality validation
- **Formation-Level Configuration**: Advanced logging configuration for multimodal formations
- **Document Processing Enhancement**: Improved handling of various file types with better error recovery
- **Test Framework**: Comprehensive Day 3 testing suite for multimodal capabilities validation
- **Integration Testing**: Real-world multimodal processing scenarios with performance benchmarks

### Memory System Enhancement ✅ **COMPLETED**
- **User Information Storage**: Advanced user context management in memory systems
- **Session-Aware Memory**: Intelligent short-term memory scoring with session context preservation
- **Memory Validation**: Updated validation methods for improved data integrity
- **Buffer Memory Structure**: Enhanced testing framework with mode-based configuration
- **Configuration Models**: Updated datatypes and models for better memory management

### Chat Orchestrator Refinement ✅ **COMPLETED**
- **Document Processing**: Streamlined initialization with better integration patterns
- **Streaming Behavior**: Enhanced determination logic for optimal performance
- **Code Readability**: Improved maintainability and developer experience
- **Session Tracking**: Better session and request ID management throughout conversations
- **Error Recovery**: Enhanced error handling for robust conversation management

### Formation and Overlord Coordination ✅ **COMPLETED**
- **Agent File Loading**: Improved error handling for configuration validation
- **Secret Retrieval**: Enhanced mechanisms with better fallback strategies
- **Startup Process**: Streamlined async initialization for faster formation startup
- **Service Orchestration**: Clean handoff between Formation operational management and Overlord intelligence
- **Resource Management**: Better cleanup and resource allocation strategies

## Features

- **Formation Execution**: Direct execution of formation YAML configurations as live AI systems
- **Hot Agent Deployment**: Add/remove agents during runtime with zero downtime
- **Formation-Overlord Architecture**: Clean separation between operations (Formation) and intelligence (Overlord)
- **Overlord Orchestration**: Central orchestration system for managing multiple agents
- **Agent Framework**: Flexible agent implementation with specialized capabilities
- **Unified Services Architecture**: Consolidated multimodal, memory, MCP, A2A, and observability services
- **Memory Systems**: Sophisticated memory management with buffer and long-term storage, including FIFO cleanup and automatic memory management with async database operations for 3x performance improvement
- **MCP Protocol**: Model Context Protocol implementation for tool integration
- **Built-in MCP Servers**: File Generation MCP for secure creation of charts, documents, spreadsheets, images, and presentations through sandboxed Python execution
- **Knowledge Integration**: Enhanced knowledge base with directory/multi-path support and YAML configuration
- **Security Layer**: Role-based access control and permission management
- **A2A Communication**: Agent-to-Agent protocol for complex agent collaboration
- **Multi-Modal Support**: Handle text, image, audio, video, and document content through unified services
- **OneLLM Integration**: Provider-agnostic LLM interface with multiple model support
- **Async Orchestration**: Production-ready async request-response patterns for long-running agentic tasks with intelligent routing, webhook notifications, background processing, and session tracking
- **Streaming Responses**: Real-time streaming chat responses with AsyncGenerator support for ChatGPT-like streaming behavior
- **Intelligent Clarification**: Advanced parameter collection system that automatically detects incomplete requests and asks natural clarifying questions with multilingual support
- **Unified Response Format**: Standardized response structure across all communication modes (sync, async, webhooks) with consistent error handling, metadata, and session management
- **Observability & Monitoring**: Comprehensive event streaming system with 4 transport types (stdout, file, stream, trail), 10 event formatters (jsonl, text, msgpack, protobuf, datadog, splunk, elastic, grafana, newrelic, opentelemetry), health monitoring, and distributed tracing
- **MCP Code Quality Enhancement**: Comprehensive code quality improvements including elimination of 150+ lines of duplicated code, enhanced error handling with logging, performance optimizations with caching, type safety improvements, JSON-RPC compliance, and proper subprocess safety patterns
- **Task Scheduling System**: Natural language task scheduling for both recurring jobs ("check email every hour") and one-time tasks ("remind me tomorrow at 2pm") with intelligent detection, unified database architecture, proactive AI capabilities, security hardening, and enterprise features including audit trails and Formation API exposure

## Installation

```bash
# From PyPI
pip install muxi-runtime

# Development installation
git clone https://github.com/muxi-ai/runtime.git
cd runtime
pip install -e .
```

## Usage

### New Formation-Based Architecture with Latest Features

```python
from muxi.runtime import Formation

# Create a formation to manage the operational lifecycle
formation = Formation()

# Load and validate formation configuration (now async)
await formation.load("my-formation.yaml")

# Start the overlord with pre-configured services (now async)
overlord = await formation.start_overlord()

# Interact with the intelligent system with user-specific credentials
response = await overlord.chat(
    message="Create a GitHub repository for my project and add the files from /my/project",
    user_id="user123",  # User credentials automatically resolved
    session_id="session_abc"
)
print(response)

# Agent automatically handles complex workflows:
# 1. Attempts to create repository (using user's GitHub credentials)
# 2. If permission error, tries alternative approach
# 3. Searches for files if directory not found
# 4. Creates directories if needed
# 5. Explains limitations if operations fail

# Hot agent deployment during runtime (now async)
new_agent_id = await formation.add_agent({
    "schema": "1.0.0",
    "id": "specialist_coder",
    "name": "Python Specialist",
    "description": "Specialized in Python code review and debugging",
    "llm_models": [{
        "text": "anthropic/claude-3-opus",
        "api_key": "${{ secrets.ANTHROPIC_API_KEY }}",
        "settings": {"temperature": 0.1}
    }],
    "role": "specialist",
    "specialties": ["python", "debugging", "code_review"]
})

# Add MCP servers dynamically (now async)
await formation.add_mcp({
    "schema": "1.0.0",
    "id": "github-tools",
    "description": "GitHub repository management tools",
    "type": "http",
    "endpoint": "https://api.githubcopilot.com/mcp",
    "auth": {
        "type": "bearer",
        "token": "${{ user.credentials.github }}"  # User-specific credentials
    }
})

# Graceful shutdown (now async)
await formation.stop_overlord()
formation.stop()
```

### User Credential Management ✅ **NEW**

MUXI now supports dynamic user-specific credentials that are resolved at runtime:

```yaml
# Formation configuration with user credentials
mcp_servers:
  - id: "github-mcp"
    type: "http"
    endpoint: "https://api.githubcopilot.com/mcp"
    auth:
      type: "bearer"
      token: "${{ user.credentials.github }}"  # Resolved per-user at runtime

  - id: "linear-mcp"
    type: "http"
    endpoint: "https://mcp.linear.app/sse"
    auth:
      type: "bearer"
      token: "${{ secrets.LINEAR_MCP_TOKEN }}"  # Formation-level credential
```

```python
# User without GitHub credentials gets clarification
response = await overlord.chat(
    "Create a GitHub repository",
    user_id="new_user"
)
# Response: "I need your GitHub credentials to create a repository. Please provide your GitHub access token."

# After user provides credentials, operation succeeds automatically
# Credentials are stored securely in database and cached per session
```

### Agent Tool Call Chaining ✅ **NEW**

Agents now intelligently recover from errors and complete complex operations:

```python
# Single prompt that triggers intelligent multi-step execution
response = await overlord.chat(
    "Create a file called 'report.txt' in the new-project directory with today's date",
    user_id="user123"
)

# Agent automatically:
# 1. Attempts: write_file("/path/to/new-project/report.txt", content)
#    → Error: "Directory doesn't exist"
# 2. Analyzes: "I need to create the directory first"
# 3. Executes: create_directory("/path/to/new-project")
#    → Success
# 4. Retries: write_file("/path/to/new-project/report.txt", content)
#    → Success
# 5. Responds: "I've created the new-project directory and added report.txt with today's date"

# Configurable limits prevent infinite loops:
# - max_tool_iterations: 10 (execution loops)
# - max_tool_calls: 50 (total tool calls)
# - max_repeated_errors: 3 (same error threshold)
```

### Advanced MCP Configuration ✅ **ENHANCED**

Support for multiple MCP transport types with auto-fallback:

```yaml
mcp:
  # Global MCP settings
  max_tool_iterations: 10      # Tool chaining loops
  max_tool_calls: 50          # Total tool calls per request
  max_repeated_errors: 3      # Error repetition threshold

  servers:
    # Command-based MCP (local tools)
    - id: "filesystem-tools"
      type: "command"
      command: "npx"
      args: ["@modelcontextprotocol/server-filesystem"]
      env:
        ALLOWED_DIRECTORIES: "/home/user/projects"

    # HTTP with auto-fallback (tries streamable HTTP, falls back to SSE)
    - id: "linear-mcp"
      type: "http"
      endpoint: "https://mcp.linear.app/sse"
      auth:
        type: "bearer"
        token: "${{ secrets.LINEAR_MCP_TOKEN }}"

    # User-specific MCP server
    - id: "github-mcp"
      type: "http"
      endpoint: "https://api.githubcopilot.com/mcp"
      auth:
        type: "bearer"
        token: "${{ user.credentials.github }}"
```
