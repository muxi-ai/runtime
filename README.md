# MUXI Runtime

> The computational engine that powers formation execution in the MUXI AI Server and enables direct deployment in embedded systems.

## Overview

MUXI Runtime is the foundational execution engine of the MUXI Framework, serving as the computational core that runs AI agent formations. It provides a comprehensive set of abstractions and utilities for building, deploying, and managing complex AI agent systems both within the MUXI Server and as a standalone embedded runtime.

Think of MUXI Runtime as analogous to the Docker Runtime - it's the powerful engine that executes formation definitions (YAML configs) as live AI systems, while the MUXI Server acts as the "Docker daemon" handling HTTP, routing, authentication, and formation lifecycle management.

**Dual Deployment Model:**
- **Server Integration**: Powers formation execution within the MUXI AI Server
- **Embedded Systems**: Runs directly in applications for local AI agent capabilities

## Recent Architecture Improvements

### File Generation MCP ✅ **PRODUCTION READY**
- **Built-in MCP Server**: Comprehensive file generation capabilities through secure Python code execution
- **Multi-Format Support**: Charts (matplotlib), documents (docx, PDF), spreadsheets (Excel, CSV), images (PIL, QR codes), presentations (pptx)
- **Security First**: AST-based code validation with whitelist of allowed libraries, no exec/eval allowed
- **Sandboxed Execution**: Subprocess isolation with 30-second timeout, restricted to `outputs/` directory, no network access
- **Auto-Registration**: Built-in MCPs automatically register at formation startup with granular configuration control
- **Dynamic System Prompts**: Automatic augmentation of agent prompts with file generation instructions and examples
- **Formation Integration**: Support for both simple boolean and granular array configuration modes via `runtime.built_in_mcps`
- **Production Ready**: Complete dependency management, testing infrastructure, comprehensive error handling

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
| Monolithic agent capabilities | Unified services architecture |
| Scattered multimodal code | Consolidated multimodal services |
| Fragmented data types | Unified datatypes package |
| Backward compatibility burden | Clean, modern APIs only |
| Static agent management | Hot agent deployment |
| Manual task management | Intelligent task scheduling |
| External-only MCP servers | Built-in MCP servers with auto-registration |

## Features

- **Formation Execution**: Direct execution of formation YAML configurations as live AI systems
- **Hot Agent Deployment**: Add/remove agents during runtime with zero downtime
- **Formation-Overlord Architecture**: Clean separation between operations (Formation) and intelligence (Overlord)
- **Overlord Orchestration**: Central orchestration system for managing multiple agents
- **Agent Framework**: Flexible agent implementation with specialized capabilities
- **Unified Services Architecture**: Consolidated multimodal, memory, MCP, A2A, and observability services
- **Memory Systems**: Sophisticated memory management with buffer and long-term storage, including FIFO cleanup and automatic memory management
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

### New Formation-Based Architecture

```python
from muxi.runtime import Formation

# Create a formation to manage the operational lifecycle
formation = Formation()

# Load and validate formation configuration
formation.load("my-formation.yaml")

# Start the overlord with pre-configured services
overlord = formation.start_overlord()

# Interact with the intelligent system
response = overlord.chat(
    message="Hello, can you help me with a coding problem?",
    user_id="user123",
    session_id="session_abc"
)
print(response)

# Hot agent deployment during runtime
new_agent_id = await formation.add_agent({
    "id": "specialist_coder",
    "name": "Python Specialist",
    "specialties": ["python", "debugging"],
    "model": {"provider": "openai", "model": "gpt-4o"}
})

# Remove agents safely during runtime
await formation.remove_agent("old_agent_id")

# Graceful shutdown - finish conversations/tasks
formation.stop_overlord()

# Cleanup operational resources
formation.stop()
```

### Runtime Formation Management ✅ **NEW**

MUXI Runtime now supports dynamic addition and removal of agents and MCP servers at runtime, providing flexible component management for live formations:

```python
# Add agents dynamically using inline schema
await formation.add_agent({
    "schema": "1.0.0",
    "id": "code_reviewer",
    "name": "Code Review Assistant",
    "description": "Specialized in code review and best practices",
    "llm_models": [
        {
            "text": "anthropic/claude-3-opus",
            "api_key": "${{ secrets.ANTHROPIC_API_KEY }}",
            "settings": {"temperature": 0.1}
        }
    ],
    "role": "specialist",
    "specialties": ["code_review", "best_practices"]
})

# Add agents from YAML/JSON files
await formation.add_agent("path/to/new_agent.yaml")

# Add MCP servers dynamically
await formation.add_mcp({
    "schema": "1.0.0",
    "id": "weather-tools",
    "description": "Weather information tools",
    "type": "http",
    "endpoint": "https://api.weather.com/mcp",
    "auth": {
        "type": "api_key",
        "key": "${{ secrets.WEATHER_API_KEY }}"
    }
})

# Add MCP servers from configuration files
await formation.add_mcp("configs/mcp/database-tools.yaml")

# List available components
agents = formation.list_agents()
mcp_servers = formation.list_mcp_servers()

# Check MCP server status
status = formation.get_mcp_status("weather-tools")
print(f"Weather Tools Status: {status}")

# Remove components when no longer needed
await formation.remove_agent("code_reviewer")
await formation.remove_mcp("weather-tools")

# Remove MCP servers with immediate disconnection
formation.remove_mcp_async("database-tools")  # Non-blocking removal
```

#### Schema-Based Configuration

The dynamic component system accepts both inline schemas and file paths:

```python
# Inline schema (Python dict)
agent_schema = {
    "schema": "1.0.0",
    "id": "sales_assistant",
    "name": "Sales Support Agent",
    "description": "Helps with sales inquiries and product information",
    "system_message": "You are a helpful sales assistant...",
    "llm_models": [{"text": "openai/gpt-4o"}],
    "knowledge": {
        "enabled": True,
        "sources": [
            {"path": "knowledge/products/", "description": "Product catalog"}
        ]
    }
}
await formation.add_agent(agent_schema)

# File path (YAML/JSON)
await formation.add_agent("agents/support_agent.yaml")
```

#### Component Validation

The system provides comprehensive validation:

- **Schema compliance** checking (version, required fields)
- **Conflict detection** (duplicate IDs, overlapping configurations)
- **Resource validation** (model availability, MCP endpoint connectivity)
- **Integration testing** (agent-to-overlord communication verification)

```python
# Validation errors provide helpful feedback
try:
    await formation.add_agent({"id": "existing_agent"})
except ValueError as e:
    print(f"Conflict detected: {e}")
    # Output: "Agent with ID 'existing_agent' already exists"

try:
    await formation.add_mcp({"invalid": "schema"})
except ValueError as e:
    print(f"Schema error: {e}")
    # Output: "Missing required field: 'id'"
```

### Streaming Conversation (ChatGPT-like streaming)
```python
async for chunk in overlord.chat(
    message="Explain how async generators work",
    user_id="user123",
    session_id="session_abc",
    stream=True  # Enable streaming
):
    print(chunk, end="", flush=True)
```

### Task Scheduling (Natural Language) ✅ **NEW**

MUXI Runtime now supports intelligent task scheduling through natural language, enabling both recurring workflows and one-time scheduled tasks:

```python
# Schedule recurring tasks using natural language
response = overlord.chat(
    message="Check my email every hour for messages from my wife",
    user_id="user123",
    session_id="session_abc"
)
# System intelligently detects this as a recurring job and sets up cron scheduling

# Schedule one-time tasks using natural language
response = overlord.chat(
    message="Remind me to call mom tomorrow at 2pm",
    user_id="user123",
    session_id="session_abc"
)
# System intelligently detects this as a one-time job and schedules for specific datetime

# The scheduler automatically:
# - Detects job type (recurring vs one-time)
# - Converts natural language to proper scheduling format
# - Executes tasks with preserved user context
# - Maintains security isolation per user
# - Handles timezone conversions and UTC storage
# - Completes and cleans up one-time jobs automatically
```

#### Scheduler Configuration in Formation

```yaml
# formation.yaml
scheduler:
  enabled: true
  check_interval_minutes: 1
  max_concurrent_jobs: 10
  max_failures_before_pause: 3
  timezone: "America/New_York"

memory:
  persistent:
    connection_string: "${POSTGRES_DATABASE_URL}"  # Shared with scheduler
```

#### Advanced Scheduling Features

```python
# The system handles complex scheduling patterns:
# - "Every weekday at 9am except holidays"
# - "First Monday of each month"
# - "Every 30 minutes during business hours"
# - "Tomorrow at 2pm but not if it's a weekend"

# Scheduler provides comprehensive job management:
from muxi.runtime.services.scheduler import SchedulerService

scheduler = SchedulerService.get_instance(overlord)

# List active jobs
jobs = await scheduler.job_manager.get_jobs_by_user("user123")

# Pause/resume jobs
await scheduler.job_manager.pause_job(job_id)
await scheduler.job_manager.resume_job(job_id)

# Get job statistics
stats = await scheduler.job_manager.get_job_statistics(job_id)
print(f"Total runs: {stats['total_runs']}, Failures: {stats['total_failures']}")
```

### Legacy Pattern (Removed)
```python
# ❌ No longer supported - use Formation-based architecture above
# from muxi.runtime.overlord import Overlord
# overlord = Overlord(config_dict)  # Removed for cleaner architecture
```

## Secrets Management (Development)

MUXI Runtime includes an encrypted secrets management system for storing sensitive configuration like API keys. For development and testing, use the provided utility scripts:

### Adding Secrets

```bash
# Add a secret to a formation
python runtime/muxi/runtime/utils/add_secret.py <formation_path> <SECRET_NAME> "<secret_value>"

# Examples
python runtime/muxi/runtime/utils/add_secret.py examples/configs OPENAI_API_KEY "sk-your-key-here"
python runtime/muxi/runtime/utils/add_secret.py formation-a.yaml WEATHER_API_KEY "your-weather-key"
```

### Listing Secrets

```bash
# List all secrets in a formation
python runtime/muxi/runtime/utils/add_secret.py <formation_path> list

# Example
python runtime/muxi/runtime/utils/add_secret.py examples/configs list
```

### Deleting Secrets

```bash
# Delete a specific secret
python runtime/muxi/runtime/utils/delete_secret.py <formation_path> <SECRET_NAME>

# Examples
python runtime/muxi/runtime/utils/delete_secret.py examples/configs OPENAI_API_KEY
python runtime/muxi/runtime/utils/delete_secret.py formation-a.yaml WEATHER_API_KEY

# List secrets (to verify deletion)
python runtime/muxi/runtime/utils/delete_secret.py examples/configs list
```

### Using Secrets in Configuration

In your formation YAML files, reference secrets using GitHub Actions-style syntax:

```yaml
# formation.yaml
agents:
  - agent_id: assistant
    model:
      provider: openai
      api_key: "${{ secrets.OPENAI_API_KEY }}"  # Encrypted secret reference
      model: gpt-4o

mcp_servers:
  - server_id: weather-api
    url: "https://api.weather.com"
    credentials:
      api_key: "${{ secrets.WEATHER_API_KEY }}"  # Encrypted secret reference
```

### Security Features

- **AES-256-GCM Encryption**: All secrets are encrypted with per-formation master keys
- **Secure File Permissions**: Secret files (`.key`, `secrets.enc`) use 0o600 permissions
- **Formation Isolation**: Each formation has its own encrypted secrets store
- **No Plaintext Storage**: Secrets are never stored in plaintext on disk

## Architecture

MUXI Runtime consists of several key components organized around the Formation-Services-Overlord architecture:

```
muxi/runtime/
├── formation/                  # Formation orchestration and lifecycle
│   ├── formation.py           # Main formation orchestration
│   ├── agents/                # Agent management
│   ├── overlord/              # Intelligent decision-making
│   └── config/                # Configuration management
├── services/                  # Unified service architecture
│   ├── memory/                # Memory systems
│   ├── multimodal/            # Multi-modal processing (moved from agents)
│   ├── mcp/                   # Model Context Protocol
│   ├── a2a/                   # Agent-to-Agent communication
│   ├── llm/                   # Language model services
│   ├── observability/         # Monitoring and tracing
│   ├── secrets/               # Secrets management
│   ├── scheduler/             # Task scheduling system (recurring & one-time jobs)
│   └── db.py                  # Unified database manager (PostgreSQL/SQLite)
├── types/                     # Consolidated data types
│   ├── errors.py              # Unified error types
│   └── response.py            # Unified response format
└── utils/                     # Runtime utilities
```

## Runtime in the MUXI Ecosystem

MUXI Runtime is part of the broader MUXI Framework ecosystem, designed around formation-based AI system deployment:

- **MUXI Runtime**: The computational engine executing formations (this repository) - **✅ 100% Complete + Architectural Transformation**
- **MUXI Server**: Formation execution server with REST/SSE/WebRTC/MCP/Webhook APIs - **⏳ Ready to Start Development**
- **OneLLM**: Provider-agnostic LLM interface with multi-modal support - **✅ OpenAI Complete**
- **FAISSx**: Distributed FAISS vector database for memory systems - **✅ Integration Complete**
- **MUXI CLI**: Command-line interface for formation management - **⏳ Next Priority**
- **MUXI Schemas**: Formation and agent configuration schemas - **✅ Complete**

### Formation-First Architecture

The runtime executes **Formation configs** (YAML files defining complete AI systems) as live **Formations** (running AI systems), following a Docker-like paradigm:

| Docker Concept | MUXI Equivalent |
|---------------|-----------------|
| Dockerfile | Formation.yaml |
| Docker Container | Running Formation |
| Docker Runtime | MUXI Runtime |
| Docker Daemon | MUXI Server |

## License

Elastic License 2.0

