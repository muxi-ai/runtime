# MUXI Engine

> The computational heart of the MUXI AI Server, providing powerful agent orchestration, memory management, and execution capabilities.

## Overview

MUXI Engine is the central component of the MUXI Framework, serving as the computational core that powers the AI Server. It provides a comprehensive set of abstractions and utilities for building, deploying, and managing complex AI agent systems.

Think of MUXI Engine as analogous to the Docker Engine - it's the powerful runtime that executes agent capabilities while the MUXI Server acts as the "Docker daemon" handling HTTP, routing, and authentication.

## Features

- **Overlord Orchestration**: Central orchestration system for managing multiple agents
- **Agent Framework**: Flexible agent implementation with specialized capabilities
- **Memory Systems**: Sophisticated memory management with buffer and long-term storage
- **MCP Protocol**: Model Context Protocol implementation for tool integration
- **Knowledge Integration**: Built-in knowledge base capabilities
- **Security Layer**: Role-based access control and permission management
- **A2A Communication**: Agent-to-Agent protocol for complex agent collaboration

## Installation

```bash
# From PyPI
pip install muxi-engine

# Development installation
git clone https://github.com/muxi-ai/engine.git
cd engine
pip install -e .
```

## Usage

```python
from muxi.engine import Overlord, Agent

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

MUXI Engine consists of several key components:

```
muxi/engine/
├── agent.py        # Agent implementation
├── overlord.py     # Overlord orchestration
├── config/         # Configuration components
├── memory/         # Memory systems
│   ├── buffer.py   # Buffer memory
│   ├── long_term.py # Long-term memory
│   └── extractor.py # Information extraction
├── mcp/            # Model Context Protocol
│   ├── service.py  # Centralized MCP service
│   └── transport/  # Transport implementations
└── knowledge/      # Knowledge base integration
```

## Engine in the MUXI Ecosystem

MUXI Engine is part of the broader MUXI Framework ecosystem:

- **MUXI Engine**: The computational heart powering agent capabilities (this repository)
- **MUXI Server**: HTTP server with REST API, WebSocket, and MCP endpoints
- **MUXI LLM**: Standardized interface for LLM providers
- **MUXI Schemas**: Configuration schemas for consistent definition

## License

MIT License

