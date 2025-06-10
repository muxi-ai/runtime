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
- **Memory Systems**: Sophisticated memory management with buffer and long-term storage, including FIFO cleanup and automatic memory management
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


## License

Elastic License 2.0

