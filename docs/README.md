# MUXI Runtime - Contributor Documentation

Documentation for contributors working on the MUXI Runtime.

## What is MUXI Runtime?

MUXI Runtime is the **execution engine** for AI agent formations. It's the core component that:

- Loads and validates formation YAML configurations
- Orchestrates multi-agent systems via the Overlord
- Manages LLM providers, memory systems, and tool integrations (MCP)
- Exposes the Formation API for agent interactions
- Handles async operations, webhooks, and scheduling

### Role in the MUXI Stack

```
┌────────────────────────────────────────────────────────┐
│  User Applications (Chat UIs, APIs, Automations)       │
└────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────┐
│  MUXI Server (Go)                                      │
│  - Formation lifecycle management                      │
│  - Multi-tenant orchestration                          │
│  - Runtime version management                          │
└────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────┐
│  MUXI Runtime (Python) ◄── YOU ARE HERE                │
│  - Formation execution engine                          │
│  - Overlord orchestration                              │
│  - Agent, memory, MCP, A2A services                    │
└────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────┐
│  External Services (LLM APIs, MCP Servers, Databases)  │
└────────────────────────────────────────────────────────┘
```

## Getting Started

### Prerequisites

- Python 3.10+
- OpenAI API key (or other LLM provider)

### Development Setup

```bash
git clone https://github.com/muxi-ai/runtime.git
cd runtime
pip install -e ".[dev]"
```

### Running Tests

```bash
# Unit tests
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# E2E tests (requires API keys)
pytest e2e/tests -v
```

## Project Structure

```
runtime/
├── src/muxi/runtime/
│   ├── formation/          # Formation engine
│   │   ├── overlord/       # Central orchestration
│   │   ├── agents/         # Agent implementations
│   │   ├── workflow/       # Task decomposition, SOPs
│   │   ├── server/         # Formation API (FastAPI)
│   │   └── background/     # Webhooks, scheduling, async
│   ├── services/           # Runtime services
│   │   ├── memory/         # Memory systems
│   │   ├── mcp/            # MCP client
│   │   ├── a2a/            # Agent-to-agent
│   │   └── llm/            # LLM abstraction
│   └── datatypes/          # Type definitions
├── tests/                  # Unit & integration tests
├── e2e/                    # End-to-end tests
├── formations/             # Example formations
└── docs/                   # Contributor docs (you are here)
```

## Contributor Guides

| Document | Description |
|----------|-------------|
| [AGENTS.md](../AGENTS.md) | Development playbook and conventions |
| [CLAUDE.md](../CLAUDE.md) | AI-assisted development context |

### MUXI-Wide Guides (apply to all repos)

| Topic | Link |
|-------|------|
| Git Workflow | [github.com/muxi-ai/muxi/GIT-WORKFLOW.md](https://github.com/muxi-ai/muxi/blob/main/GIT-WORKFLOW.md) |
| Versioning | [github.com/muxi-ai/muxi/VERSIONING.md](https://github.com/muxi-ai/muxi/blob/main/VERSIONING.md) |
| Contributing | [github.com/muxi-ai/muxi/CONTRIBUTING.md](https://github.com/muxi-ai/muxi/blob/main/CONTRIBUTING.md) |
| Security Policy | [github.com/muxi-ai/muxi/SECURITY.md](https://github.com/muxi-ai/muxi/blob/main/SECURITY.md) |

## Runtime-Specific Docs

### Build & Release

| Document | Description |
|----------|-------------|
| [pypi-distribution.md](pypi-distribution.md) | Building and publishing to PyPI |
| [docker-compose-guide.md](docker-compose-guide.md) | Docker Compose development setup |
| [docker-secrets-guide.md](docker-secrets-guide.md) | Secrets management in Docker |
| [docker-testing.md](docker-testing.md) | Testing Docker builds |

### Architecture & Internals

| Document | Description |
|----------|-------------|
| [security-architecture.md](security-architecture.md) | LLM-based security layers |
| [server-integration.md](server-integration.md) | How Server integrates with Runtime |
| [runtime-versioning.md](runtime-versioning.md) | Runtime version management for Server |
| [prompt-management.md](prompt-management.md) | Centralized prompt loader system |
| [id-conventions.md](id-conventions.md) | ID format conventions (prefixes, nanoid) |
| [type-safety-guide.md](type-safety-guide.md) | TypedDict conventions |
| [licensing.md](licensing.md) | ELv2 license explanation |

## Key Concepts for Contributors

### Formation Loading

Formations are loaded from YAML files (`.afs`, `.yaml`, `.yml`) and validated against the [Agent Formation Spec](https://agentformation.org).

### Overlord

The Overlord is the central orchestrator that:
- Routes messages to appropriate agents
- Manages clarification flows
- Coordinates workflow decomposition
- Handles async operations

### Services

All runtime services (memory, MCP, A2A, LLM) are initialized during formation loading and available to agents.

## User Documentation

For user-facing documentation, see [docs.muxi.ai](https://docs.muxi.ai).
