# MUXI Runtime

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10+-green.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-Elastic-purple.svg" alt="License">
  <img src="https://img.shields.io/badge/tests-passing-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-85%25-green.svg" alt="Coverage">
</p>

### The container runtime for AI agents

**Core execution engine that powers the MUXI AI Server**
> _“Like containers for Docker, but for intelligent multi-agent systems”_

---

## 📖 What is MUXI Runtime?

MUXI Runtime is the low-level execution engine that powers AI agent formations inside the [MUXI AI Server](https://github.com/muxi-ai/server). It's the foundational layer that transforms declarative YAML configurations into living, breathing AI systems.

> [!NOTE]
> This repository is for contributors and the for developers who want to embed MUXI Runtime in their own applications. **For 90% of users, we recommend installing [MUXI AI Server](https://github.com/muxi-ai/server) for the complete platform experience.**

### Core Responsibilities

- **Formation Execution** - Loads and runs AI agent configurations from YAML
- **Agent Lifecycle** - Manages agent creation, orchestration, and teardown
- **Memory Management** - Three-tier memory system (buffer, persistent, vector)
- **Tool Integration** - MCP protocol support for 1,000+ external tools
- **Resource Isolation** - Multi-tenant support with credential management

## 🌟 Features

- **Formation Execution**: Direct execution of formation YAML configurations as live AI systems
- **Hot Agent Deployment**: Add/remove agents during runtime with zero downtime
- **Formation-Overlord Architecture**: Clean separation between operations (Formation) and intelligence (Overlord)
- **Overlord Orchestration**: Central orchestration system for managing multiple agents
- **Agent Framework**: Flexible agent implementation with specialized capabilities
- **Unified Services Architecture**: Consolidated multimodal, memory, MCP, A2A, and observability services
- **Memory Systems**: Sophisticated memory management with buffer and long-term storage, including FIFO cleanup and automatic memory management with async database operations for 3x performance improvement
- **MCP Protocol**: Model Context Protocol implementation for tool integration
- **Built-in MCP Servers**: File Generation MCP for secure creation of charts, documents, spreadsheets, images, and presentations through sandboxed Python execution
- **Artifacts System**: Comprehensive file generation, tracking, and management with secure sandboxed execution, intelligent metadata extraction, session-based storage, and nanoid-based unique identifiers
- **Knowledge Integration**: Enhanced knowledge base with directory/multi-path support and YAML configuration
- **Standard Operating Procedures (SOPs)**: Overlord-level procedural guidance with template/guide modes, supporting [agent:], [mcp:], and [file:] directives for consistent task execution
- **Security Layer**: Role-based access control and permission management
- **A2A Communication**: Agent-to-Agent protocol for complex agent collaboration
- **Multi-Modal Support**: Handle text, image, audio, video, and document content through unified services
- **OneLLM Integration**: Provider-agnostic LLM interface with multiple model support
- **Async Orchestration**: Production-ready async request-response patterns for long-running agentic tasks with intelligent routing, webhook notifications, background processing, and session tracking
- **Streaming Responses**: Real-time streaming chat responses with AsyncGenerator support for ChatGPT-like streaming behavior
- **Intelligent Clarification**: Advanced parameter collection system that automatically detects incomplete requests and asks natural clarifying questions with multilingual support
- **Unified Response Format**: Standardized response structure across all communication modes (sync, async, webhooks) with consistent error handling, metadata, and session management
- **Workflow Orchestration**: Intelligent task decomposition for complex requests with configurable complexity analysis, multi-agent coordination, parallel task execution, and approval workflows for high-stakes operations
- **Dynamic Async Decision Making**: Approval-aware async pattern that intelligently defers async execution when user approval is needed, maintaining synchronous flow for interactive workflows while automatically switching to async after approval for optimal performance
- **Intelligent Agent Filtering**: LLM-based agent selection for formations with 10+ agents, featuring aggressive caching (97% cache hit rate), configurable relevance thresholds, and smart routing that ensures the most capable agent handles each task
- **Resilience Layer**: Production-ready error recovery with automatic retry (exponential backoff), user-friendly error messages, graceful degradation strategies, and circuit breakers to prevent cascading failures
- **Observability & Monitoring**: Comprehensive event streaming system with 4 transport types (stdout, file, stream, trail), 10 event formatters (jsonl, text, msgpack, protobuf, datadog, splunk, elastic, grafana, newrelic, opentelemetry), health monitoring, and distributed tracing
- **MCP Code Quality Enhancement**: Comprehensive code quality improvements including elimination of 150+ lines of duplicated code, enhanced error handling with logging, performance optimizations with caching, type safety improvements, JSON-RPC compliance, and proper subprocess safety patterns
- **Task Scheduling System**: Natural language task scheduling for both recurring jobs ("check email every hour") and one-time tasks ("remind me tomorrow at 2pm") with intelligent detection, unified database architecture, proactive AI capabilities, security hardening, and enterprise features including audit trails and Formation API exposure

## 🏗️ Architecture Overview

```
┌────────────────────────────────────┐
│           MUXI AI Server           │  ← User-facing API server
├────────────────────────────────────┤
│             MUXI Runtime           │  ← This repository
│  ┌──────────────────────────────┐  │
│  │      Formation Engine        │  │  ← YAML loader & validator
│  ├──────────────────────────────┤  │
│  │    Overlord   │  Agent Pool  │  │  ← Orchestration layer
│  ├──────────────────────────────┤  │
│  │   Memory │ Services │ Tools  │  │  ← Core subsystems
│  ├──────────────────────────────┤  │
│  │  SOPs │ Knowledge │ Security │  │  ← Guidance systems
│  └──────────────────────────────┘  │
├────────────────────────────────────┤
│       LLM Providers (OneLLM)       │  ← External integrations
└────────────────────────────────────┘
```

📚 **Full Documentation**: [muxi.org/docs](https://muxi.org/docs)

---

## 🚀 Quick Start

The easiest way to get started is to install the MUXI Server + CLI and create a new project:

```bash
# Install MUXI Server + CLI
curl -fsSL https://muxi.org/install | sh

# Create a new AI project
muxi new my-ai-assistant
cd my-ai-assistant

# Start developing
muxi dev
```

### 📚 Documentation
- [Quick Start Guide](https://muxi.org/docs/quickstart) - Get started with MUXI
- [Formation Guide](https://muxi.org/docs/formations) - Creating AI systems
- [API Reference](https://muxi.org/docs/api) - Server API documentation

---

## 🔧 Embedding MUXI Runtime

The MUXI Runtime can be used directly as a Python framework:

```python
from muxi import Formation
import asyncio

async def main():
    # Load a formation
    formation = Formation()
    await formation.load("formation.yaml")

    # Start the runtime
    overlord = await formation.start_overlord()

    # Interact with your AI system
    response = await overlord.chat(
        "Hello! What can you help me with?",
        user_id="user123"
    )
    print(response)

asyncio.run(main())
```

**Example formation.yaml:**
```yaml
schema: "1.0.0"
id: "my-assistant"
description: "A helpful AI assistant"

llm:
  models:
    - text: "openai/gpt-4o-mini"
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"

agents:
  - id: "assistant"
    name: "General Assistant"
    system_message: "You are a helpful AI assistant."

memory:
  buffer:
    size: 20
    vector_search: true
```

### 📚 Documentation

- [Python SDK](https://muxi.org/docs/sdk/python) - Using MUXI as a library
- [Formation Schema](https://muxi.org/docs/schema) - Complete YAML reference
- [Advanced Patterns](https://muxi.org/docs/patterns) - Complex use cases

---

## 👨🏼‍💻 Contributing

We welcome contributions! MUXI Runtime is open source and community-driven.

**Quick start for contributors:**
```bash
git clone https://github.com/muxi-ai/runtime
cd runtime
pip install -e .[dev]
pytest
```

📚 **See our [Contributing Guide](CONTRIBUTING.md)** for:
- Development setup and prerequisites
- Testing philosophy (real services, no mocks)
- Code style and architecture principles
- Pull request process
- Community guidelines

## 🤝 Community & Support

- **Issues**: [GitHub Issues](https://github.com/muxi-ai/runtime/issues)
- **Discussions**: [GitHub Discussions](https://github.com/muxi-ai/community/discussions)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

## 📦 Related Projects

- [muxi-ai/server](https://github.com/muxi-ai/server) - API server that hosts this runtime
- [muxi-ai/cli](https://github.com/muxi-ai/cli) - Command-line management tool
- [muxi-ai/sdks](https://github.com/muxi-ai/sdks) - SDKs in multiple languages for MUXI
- [muxi-ai/onellm](https://github.com/muxi-ai/onellm) - Unified LLM interface
- [muxi-ai/faissx](https://github.com/muxi-ai/faissx) - Distributed vector store

## 📄 License

MUXI Runtime (and MUXI Server) are licensed under the **Elastic License 2.0** (ELv2).

This means that you're allowed to freely use, modify, and redistribute the software – **including in commercial products** – as long as you do not provide it as a hosted or managed service to third parties.

In other words:

- ✅ Use MUXI for internal projects, personal use, research, or embedded inside your own applications.
- ✅ Sell products that include MUXI, as long as you’re not offering MUXI itself as a service.
- ❌ You may not offer a “hosted” or “managed” MUXI to others (e.g., MUXI-as-a-service, cloud API).


See the [LICENSE](LICENSE) file for the complete license text and [licensing details](docs/licensing.md) for more information.

---

**Building the future of AI infrastructure, one runtime at a time**
[Report Bug](https://github.com/muxi-ai/runtime/issues) • [Submit PR](https://github.com/muxi-ai/runtime/pulls) • [Join Discussions](https://github.com/muxi-ai/community/discussions)
