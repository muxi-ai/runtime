# MUXI Runtime

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-3.9+-green.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-Elastic-purple.svg" alt="License">
  <img src="https://img.shields.io/badge/tests-passing-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-85%25-green.svg" alt="Coverage">
</p>

<h3 align="center">
  The container runtime for AI agents
</h3>

<p align="center">
  <strong>Core execution engine that powers the MUXI AI Server</strong><br>
  Like containers for Docker, but for intelligent multi-agent systems
</p>

---

## 📖 What is MUXI Runtime?

MUXI Runtime is the low-level execution engine that powers AI agent formations inside the [MUXI AI Server](https://github.com/muxi-ai/server). It's the foundational layer that transforms declarative YAML configurations into living, breathing AI systems.

**For end users**: Install [MUXI AI Server](https://github.com/muxi-ai/server) for the complete platform experience.

**For contributors**: This repository contains the core runtime that makes AI agents actually work.

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

## 🚀 Quick Start for Contributors

### Development Setup

```bash
# Clone the repository
git clone https://github.com/muxi-ai/runtime
cd runtime

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run specific test suites
pytest tests/day_1/  # Foundation tests
pytest tests/day_2/  # Memory systems
pytest tests/day_3/  # Multimodal processing
```

### Your First Formation

Create a simple AI system to see the runtime in action:

```yaml
# my-assistant.yaml
schema: "1.0.0"
id: "dev-assistant"
description: "Development helper AI"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"

agents:
  - id: "coder"
    name: "Code Assistant"
    system_message: "You are an expert programmer who writes clean, efficient code."

memory:
  buffer:
    size: 20
    vector_search: true
```

Run it directly:

```python
from muxi import Formation
import asyncio

async def main():
    # Load formation
    formation = Formation()
    await formation.load("my-assistant.yaml")

    # Start runtime
    overlord = await formation.start_overlord()

    # Test it
    response = await overlord.chat(
        "Write a Python function to calculate fibonacci numbers",
        user_id="dev123"
    )
    print(response)

asyncio.run(main())
```

## 🔬 Real-World Examples

### Multi-Agent Customer Support

```yaml
# support-system.yaml
schema: "1.0.0"
id: "enterprise-support"
description: "Multi-agent customer support system"

agents:
  - id: "router"
    name: "Support Router"
    description: "Routes customer queries to appropriate specialists"
    system_message: "Route customer queries to the right specialist"

  - id: "billing"
    name: "Billing Expert"
    description: "Handles billing and payment inquiries"
    specialties: ["payments", "invoices", "subscriptions"]

  - id: "technical"
    name: "Tech Specialist"
    description: "Provides technical support and troubleshooting"
    specialties: ["bugs", "setup", "integration"]

memory:
  persistent:
    connection_string: "postgresql://localhost/support_memory"

mcp:
  servers:
    - id: "zendesk"
      description: "Zendesk integration for ticket management"
      type: "http"
      endpoint: "https://api.zendesk.com/mcp"
```

### AI Development Team

```yaml
# dev-team.yaml
schema: "1.0.0"
id: "ai-dev-team"
description: "AI development team with specialized roles"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
    anthropic: "${{ secrets.ANTHROPIC_API_KEY }}"

agents:
  - id: "architect"
    name: "System Architect"
    description: "Designs scalable system architectures"
    system_message: "Design scalable system architectures"
    llm_models:
      - text: "anthropic/claude-3-opus"

  - id: "developer"
    name: "Senior Developer"
    description: "Implements production-ready code"
    system_message: "Implement clean, efficient code"
    llm_models:
      - text: "openai/gpt-4o"

  - id: "reviewer"
    name: "Code Reviewer"
    description: "Reviews code quality and suggests improvements"
    system_message: "Review code for bugs and improvements"

runtime:
  built_in_mcps:
    - file-generation  # Create actual code files

# Standard Operating Procedures (SOPs) in sops/ directory
# sops/code-review.yaml
id: code-review-v1
title: Code Review Process
description: Standard process for reviewing pull requests
steps:
  - step: Check code style and formatting
    description: Verify code follows project conventions
  - step: Review logic and algorithms
    description: Analyze implementation correctness
  - step: Test coverage assessment
    description: Ensure adequate test coverage
  - step: Security audit
    description: Check for security vulnerabilities
  - step: Performance review
    description: Identify performance bottlenecks
outcomes:
  success:
    - Code approved for merge
    - Feedback documented
```

## 🧪 Testing Philosophy

**No mocks allowed** - We test against real services to ensure production reliability:

```python
# Example test pattern
async def test_multi_agent_routing():
    # Load real formation
    formation = Formation()
    await formation.load("test-formations/multi-agent.yaml")
    overlord = await formation.start_overlord()

    # Test with real LLM
    response = await overlord.chat("Calculate 2+2")
    assert "4" in response

    # Test routing logic
    response = await overlord.chat("I have a billing question")
    # Should route to billing specialist
```

## 📂 Project Structure

```
src/muxi/
├── formation.py         # Formation loader and lifecycle manager
├── overlord.py         # Central orchestration engine
├── agents/             # Agent implementations
│   ├── base.py        # Base agent class
│   └── registry.py    # Agent discovery and registration
├── memory/             # Memory subsystems
│   ├── buffer.py      # Working FIFO + vector memory
│   ├── persistent.py  # Long-term PostgreSQL/SQLite storage
│   └── vector.py      # FAISSx integration
├── services/           # Core services
│   ├── mcp/          # Model Context Protocol implementation
│   ├── scheduler/    # Task scheduling system
│   ├── multimodal/   # File processing (images, audio, video)
│   └── a2a/          # Agent-to-agent communication
└── utils/             # Shared utilities
```

## 🔧 Core Components Deep Dive

### Formation Engine
The heart of the runtime - loads YAML and creates live AI systems:

```python
from muxi import Formation

# Load formation (like docker load)
formation = Formation()
await formation.load("path/to/formation.yaml")

# Validate configuration
await formation.validate()

# Start runtime (like docker run)
overlord = await formation.start_overlord()

# Hot reload for development
await formation.reload()
```

### Overlord Orchestrator
Intelligent message routing and agent coordination with SOP guidance:

```python
class Overlord:
    async def chat(self, message: str, user_id: str):
        # 1. Intent detection
        intent = await self.intent_detector.analyze(message)

        # 2. SOP matching (NEW)
        relevant_sops = await self.sop_coordinator.search(message)

        # 3. Agent selection (enhanced with SOPs)
        if relevant_sops:
            # Use SOP to guide task decomposition
            agents = self.select_agents_for_sop(relevant_sops[0])
        else:
            agent = self.select_agent(intent, self.agents)

        # 4. Memory context
        context = await self.memory.get_context(user_id)

        # 5. Tool discovery
        tools = await self.mcp_manager.get_tools_for_agent(agent)

        # 6. Execute with agent(s)
        if relevant_sops:
            # Follow SOP steps with appropriate agents
            response = await self.execute_sop(
                relevant_sops[0],
                agents,
                message,
                context,
                tools
            )
        else:
            response = await agent.process(
                message,
                context=context,
                tools=tools
            )

        return response
```

### Memory Systems

**Three-tier architecture for perfect recall:**

```python
# Buffer Memory - Recent context with vector similarity
from muxi.memory import WorkingMemory

# Note: WorkingMemory configuration is typically done in formation.yaml
# This is just showing the internal API for contributors
memory = WorkingMemory(
    buffer_size=20,
    buffer_multiplier=10,
    vector_search_enabled=True
)

# Persistent Memory - Long-term storage
from muxi.memory import LongTermMemory

memory = LongTermMemory("postgresql://localhost/muxi")
await memory.store_user_preference("theme", "dark", user_id="123")

# Vector Memory - Semantic search
results = await memory.search(
    "previous discussion about API design",
    user_id="123",
    top_k=5
)
```

## 🚀 Advanced Features

### Natural Language Task Scheduling
```python
# Users can schedule tasks conversationally
response = await overlord.chat(
    "Check my GitHub PRs every morning and summarize them",
    user_id="dev123"
)
# Creates recurring job automatically
```

### Intelligent Tool Chaining
```python
# Agents automatically recover from errors
response = await overlord.chat(
    "Create the report in /reports/2024/q4/analysis.pdf"
)
# Agent will create directories if needed, handle permissions, etc.
```

### User Credential Management
```python
# Each user has isolated credentials
response = await overlord.chat(
    "Create a PR on my GitHub repo",
    user_id="alice"  # Uses Alice's GitHub token
)
```

### Multimodal Processing
```python
# Handle any file type
response = await overlord.chat(
    "Analyze this presentation and extract key points",
    files=[{"filename": "deck.pdf", "content": pdf_bytes}]
)
```

## 📚 Documentation

### Core Documentation
- [Workflow System](docs/workflow/) - Complete workflow documentation
  - [Orchestration](docs/workflow/orchestration.md) - Task decomposition and multi-agent coordination
  - [Resilience](docs/workflow/resilience_integration.md) - Error recovery and graceful degradation
  - [Technical Guide](docs/workflow/technical_guide.md) - Implementation details
  - [Quick Reference](docs/workflow/quick_reference.md) - Common patterns
- [Memory Systems](docs/memory-systems.md) - Three-tier memory architecture
- [MCP Integration](docs/mcp/README.md) - Model Context Protocol for tools
- [Agent Collaboration](docs/agent-collaboration.md) - Multi-agent patterns
- [Observability](docs/observability.md) - Monitoring and event streaming

### Technical Guides
- [Type Safety Guide](docs/type-safety-guide.md) - Pydantic v2 patterns
- [Multi-User Architecture](docs/multi-user-architecture.md) - Tenant isolation
- [Configuration Guide](docs/configuration/) - Formation YAML reference
- [API Documentation](docs/formation-api-server.md) - REST API endpoints

## 📊 Performance Characteristics

- **Response Time**: < 2s for simple queries
- **Complex Workflows**: < 30s with streaming updates
- **Memory Usage**: < 100MB per 100 conversations
- **Concurrent Users**: 1,000+ per instance
- **Database Performance**: 3x improvement with async SQLAlchemy
- **Cost Optimization**: 70% reduction through intelligent caching

## 🛠️ Contributing

### Prerequisites

- Python 3.10+
- SQLite (for single-user persistent memory)
- PostgreSQL (for multi-user persistent memory)
- FAISSx server (optional, for distributed vector memory)
- Real API keys for testing (OpenAI, Anthropic, etc.)

### Development Workflow

1. **Fork** the repository
2. **Create** feature branch: `git checkout -b feature/amazing-feature`
3. **Write** tests first (TDD)
4. **Implement** your feature
5. **Run** tests: `pytest`
6. **Submit** pull request

### Code Standards

- **Style**: Black formatter, 120 char lines
- **Types**: Type hints for all public APIs
- **Docs**: Docstrings for public methods
- **Async**: All I/O must be async
- **Tests**: Real services only, no mocks

## 🔌 Integration Points

### For MUXI Server

```python
# The runtime exposes these interfaces
formation = Formation()
await formation.load(config_path)
overlord = await formation.start_overlord()

# Handle requests
response = await overlord.chat(
    message="User input",
    user_id="user123",
    session_id="session456",
    stream=False
)

# Lifecycle management
await overlord.stop()
await formation.cleanup()
```

### For Tool Developers

```yaml
# Add tools via MCP in formation.yaml
mcp:
  servers:
    - id: "custom-tools"
      description: "Custom tool server for specialized operations"
      type: "http"
      endpoint: "http://localhost:3000/mcp"
      auth:
        type: "bearer"
        token: "${{ secrets.TOOL_API_KEY }}"
```

### Standard Operating Procedures (SOPs)

SOPs provide overlord-level procedural guidance for consistent task execution. They're automatically discovered from the `sops/` directory in your formation.

#### SOP Format

SOPs are Markdown files with YAML front matter:

```markdown
---
type: sop  # Required to identify as SOP
name: Production Incident Response
description: Handle production incidents from detection to resolution
mode: template  # "template" (default) or "guide" for flexible approach
tags: critical, production, ops  # Comma-separated for discovery
---

# Production Incident Response

## Steps

1. **Assess severity** [agent:monitoring-specialist]
   - Check dashboards for scope
   - Review [file:references/severity-matrix.png] for classification
   - Use [mcp:datadog] to pull metrics from last hour

2. **Notify stakeholders** [agent:communications]
   - Use [file:contacts/escalation-tree.md] for contact info
   - Page on-call via [mcp:pagerduty]
   - Create ticket using [mcp:linear/create_issue]

3. **Document incident** [agent:writer]
   - Use [file:templates/incident-report.md] as template
   - Upload to Confluence using [mcp:confluence]
```

#### Directive Types

SOPs support three types of directives for guiding execution:

- **`[agent:name]`** - Route step to specific agent
- **`[mcp:tool]`** - Use specific MCP tool or server
- **`[file:path]`** - Reference any file in the sops/ directory

#### Execution Modes

1. **Template Mode** (`mode: template` - default)
   - Steps directly convert to workflow tasks
   - Fast, predictable execution
   - Best for rigid procedures

2. **Guide Mode** (`mode: guide`)
   - SOP included as guidance for LLM
   - Flexible interpretation based on context
   - Best for guidelines and best practices

#### Directory Structure

```
formation/
└── sops/
    ├── incident-response.md       # type: sop
    ├── customer-onboarding.md     # type: sop
    ├── code-review-guidelines.md  # type: sop, mode: guide
    ├── templates/                 # Referenced files
    │   ├── incident-report.md
    │   └── postmortem.docx
    └── references/                # Any organization you prefer
        └── severity-matrix.png
```

SOPs enhance the runtime by:
- Providing consistent execution patterns
- Reducing prompt duplication across agents
- Enabling organizational best practices
- Supporting both rigid procedures and flexible guidelines

## 🐛 Debugging Tips

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Or via environment
export MUXI_LOG_LEVEL=DEBUG

# Common issues:
# 1. Formation validation: Check YAML against schema
# 2. Memory errors: Verify PostgreSQL/SQLite connections
# 3. MCP errors: Ensure tool servers are running
# 4. Async errors: Check for proper await usage
```

## 📚 Resources

- [Formation Schema](https://github.com/muxi-ai/schemas) - YAML configuration reference
- [Architecture Guide](docs/architecture.md) - Deep dive into design
- [Testing Guide](docs/testing.md) - How to write runtime tests
- [Memory Systems](docs/memory.md) - Buffer, persistent, vector details
- [MCP Integration](docs/mcp.md) - Tool development guide
- [Artifacts System](docs/artifacts.md) - File generation, tracking, and management

## 🤝 Community

- **Issues**: [GitHub Issues](https://github.com/muxi-ai/runtime/issues)
- **Discussions**: [GitHub Discussions](https://github.com/muxi-ai/community/discussions)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

## 📦 Related Projects

- [muxi-ai/server](https://github.com/muxi-ai/server) - API server that hosts this runtime
- [muxi-ai/cli](https://github.com/muxi-ai/cli) - Command-line management tool
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
