# MUXI Runtime

> The computational engine that powers formation execution in the MUXI AI Server and enables direct deployment in embedded systems.

## Overview

MUXI Runtime is the foundational execution engine of the MUXI Framework, serving as the computational core that runs AI agent formations. It provides a comprehensive set of abstractions and utilities for building, deploying, and managing complex AI agent systems both within the MUXI Server and as a standalone embedded runtime.

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
- **Knowledge Integration**: Built-in knowledge base capabilities
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

- **MUXI Runtime**: The computational engine executing formations (this repository) - **95% Complete**
- **MUXI Server**: Formation management server with REST/SSE/WebRTC/MCP/Webhook APIs - **In Development**
- **OneLLM**: Provider-agnostic LLM interface (OpenAI implemented, others planned)
- **FAISSx**: Distributed FAISS vector database for memory systems
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

**Current Status**: Runtime foundation is 95% complete with all core components functional. The remaining 5% includes A2A communication protocol completion and performance optimizations.

## License

Elastic License 2.0

