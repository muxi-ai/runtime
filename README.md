# MUXI Runtime

> The computational engine that powers formation execution in the MUXI AI Server and enables direct deployment in embedded systems.

## Overview

MUXI Runtime is the foundational execution engine of the MUXI Framework, serving as the computational core that runs AI agent formations. It provides a comprehensive set of abstractions and utilities for building, deploying, and managing complex AI agent systems both within the MUXI Server and as a standalone embedded runtime.****

Think of MUXI Runtime as analogous to the Docker Runtime - it's the powerful engine that executes formation definitions (YAML configs) as live AI systems, while the MUXI Server acts as the "Docker daemon" handling HTTP, routing, authentication, and formation lifecycle management.

**Dual Deployment Model:**
- **Server Integration**: Powers formation execution within the MUXI AI Server
- **Embedded Systems**: Runs directly in applications for local AI agent capabilities

## Features

- **Formation Execution**: Direct execution of formation YAML configurations as live AI systems
- **Overlord Orchestration**: Central orchestration system for managing multiple agents
- **Agent Framework**: Flexible agent implementation with specialized capabilities
- **Memory Systems**: Sophisticated memory management with buffer and long-term storage
- **MCP Protocol**: Model Context Protocol implementation for tool integration
- **Knowledge Integration**: Enhanced knowledge base with directory/multi-path support and YAML configuration
- **Security Layer**: Role-based access control and permission management
- **A2A Communication**: Agent-to-Agent protocol for complex agent collaboration
- **Multi-Modal Support**: Handle text, image, audio, video, and document content
- **OneLLM Integration**: Provider-agnostic LLM interface with multiple model support

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

```python
from muxi.runtime import Overlord, Agent

# Create an overlord to manage agents and shared memory
overlord = Overlord(
    id="my-overlord",
    description="My orchestration system",
    buffer_size=10,
    buffer_multiplier=5
)

# Add agents to the overlord
assistant = Agent(
    id="assistant",
    system_message="You are a helpful assistant.",
    model="openai/gpt-4o"
)

coder = Agent(
    id="coder",
    system_message="You are an expert programmer.",
    model="anthropic/claude-3-opus"
)

overlord.add_agent(assistant)
overlord.add_agent(coder)

# Run a conversation
response = overlord.chat("assistant", "Hello, can you help me with a coding problem?")
print(response)
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

MUXI Runtime consists of several key components:

```
muxi/runtime/
├── agent.py          # Agent implementation
├── overlord.py       # Overlord orchestration
├── config/           # Configuration components
├── memory/           # Memory systems
│   ├── buffer.py     # Buffer memory
│   ├── long_term.py  # Long-term memory
│   └── extractor.py  # Information extraction
├── mcp/              # Model Context Protocol
│   ├── service.py    # Centralized MCP service
│   └── transport/    # Transport implementations
└── knowledge/        # Knowledge base integration
```

## Runtime in the MUXI Ecosystem

MUXI Runtime is part of the broader MUXI Framework ecosystem, designed around formation-based AI system deployment:

- **MUXI Runtime**: The computational engine executing formations (this repository) - **✅ 100% Complete**
- **MUXI Server**: Formation execution server with REST/SSE/WebRTC/MCP/Webhook APIs - **⏳ Next Phase**
- **OneLLM**: Provider-agnostic LLM interface with multi-modal support - **✅ OpenAI Complete**
- **FAISSx**: Distributed FAISS vector database for memory systems - **🚧 Integration In Progress**
- **MUXI CLI**: Command-line interface for formation management (planned)
- **MUXI Schemas**: Formation and agent configuration schemas

### Formation-First Architecture

The runtime executes **Formation configs** (YAML files defining complete AI systems) as live **Formations** (running AI systems), following a Docker-like paradigm:

| Docker Concept | MUXI Equivalent |
|---------------|-----------------|
| Dockerfile | Formation.yaml |
| Docker Container | Running Formation |
| Docker Runtime | MUXI Runtime |
| Docker Daemon | MUXI Server |

**Current Status**: ✅ **Runtime foundation is 100% complete** with all core components functional including:
- **Task #1 Completed**: OneLLM integration with comprehensive multi-modal support
- **Task #2 Completed**: FAISSx integration with local/remote mode support for distributed vector operations
- **Task #3 Completed**: Knowledge handler enhancement with directory support and YAML configuration
- **Task #4 Completed**: A2A Message Routing - External agent-to-agent communication across formations
- **Directory Structure**: Clean organization with proper test separation
- **Import Resolution**: All module imports working correctly
- **Next**: Formation YAML configuration integration for FAISSx and knowledge capabilities

## Recent Updates

### ✅ Task #4 - A2A Message Routing (COMPLETED) 🎉
- **External Agent Communication**: Full agent-to-agent communication across different formations
- **Registry-Based Discovery**: Agents can discover and communicate with external agents via A2A registry
- **Formation Server Integration**: Complete A2A protocol implementation in formation servers
- **Cross-Formation Testing**: Validated agent collaboration between Formation A (port 8080) and Formation B (port 8081)
- **Protocol Compliance**: Fixed A2A response format to return clean strings for protocol compatibility
- **Port Resolution**: Fixed agent registration to use actual running ports instead of configured ports
- **Duplicate Registration Prevention**: Resolved timing issues that caused agents to register multiple times
- **Production Ready**: All 6/6 tests passing consistently with robust error handling

### ✅ Task #1 - OneLLM Integration (COMPLETED)
- **Multi-Modal Support**: Added comprehensive file handling for images, audio, video, documents
- **FileProcessor Class**: Robust file processing with security validation
- **Enhanced Chat Method**: Multi-modal content support with proper error handling
- **Test Coverage**: Complete test suite for all new functionality

### ✅ Task #2 - FAISSx Integration (COMPLETED)
- **Local/Remote Modes**: Support for both local and remote FAISSx vector operations
- **BufferMemory Enhancement**: FAISSx integration with mode switching capabilities
- **KnowledgeHandler Enhancement**: FAISSx support for knowledge base vector search
- **Real Server Testing**: Validated with actual FAISSx server deployment
- **Backward Compatibility**: All existing functionality preserved

### ✅ Task #3 - Knowledge Handler Enhancement (COMPLETED)
- **Directory Support**: FileKnowledge now supports both files and directories with recursive scanning
- **YAML Configuration**: New schema with `enabled` flag and `sources` array for flexible configuration
- **Performance Optimizations**: File limits, size restrictions, and aggressive performance controls
- **Multiple Path Support**: Configure multiple knowledge sources with individual settings
- **Production Ready**: Comprehensive error handling, UTF-8 encoding, and sub-second test execution

### ✅ Directory Structure Reorganization (COMPLETED)
- **Test Separation**: Moved test files from production modules to `runtime/tests/`
- **Module Restructuring**: Organized `llm_service` to `llm` for cleaner architecture
- **Import Fixes**: Resolved 25+ import path issues across the codebase
- **Clean Architecture**: Proper separation between production and test code

## License

Elastic License 2.0

