# MUXI Runtime - Contributor Documentation

Documentation for contributors working on the MUXI Runtime.

> **Start here:** Read the [MUXI Architecture](https://github.com/muxi-ai/muxi/blob/main/ARCHITECTURE.md) to understand how all MUXI components fit together.

## Before Contributing

Please review these documents in the main MUXI repository:

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](https://github.com/muxi-ai/muxi/blob/main/ARCHITECTURE.md) | How all MUXI components fit together |
| [CONTRIBUTING.md](https://github.com/muxi-ai/muxi/blob/main/CONTRIBUTING.md) | Contribution guidelines |
| [CODE_OF_CONDUCT.md](https://github.com/muxi-ai/muxi/blob/main/CODE_OF_CONDUCT.md) | Community standards |
| [CONTRIBUTOR_LICENSE_AGREEMENT.md](https://github.com/muxi-ai/muxi/blob/main/CONTRIBUTOR_LICENSE_AGREEMENT.md) | CLA for contributions |
| [GIT-WORKFLOW.md](https://github.com/muxi-ai/muxi/blob/main/GIT-WORKFLOW.md) | Branch strategy (develop → rc → main) |
| [VERSIONING.md](https://github.com/muxi-ai/muxi/blob/main/VERSIONING.md) | ScalVer versioning scheme |
| [REPOSITORIES.md](https://github.com/muxi-ai/muxi/blob/main/REPOSITORIES.md) | All MUXI repositories |
| [SECURITY.md](https://github.com/muxi-ai/muxi/blob/main/SECURITY.md) | Security policy & vulnerability reporting |
| [AI-POLICY.md](https://github.com/muxi-ai/muxi/blob/main/AI-POLICY.md) | AI-assisted development policy |

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

## Runtime-Specific Docs

### Build & Release

| Document | Description |
|----------|-------------|
| [building.md](building.md) | Building Docker, SIF, and PyPI packages |
| [pypi-distribution.md](pypi-distribution.md) | PyPI distribution details |
| [docker-compose-guide.md](docker-compose-guide.md) | Running with Docker Compose |
| [docker-secrets-guide.md](docker-secrets-guide.md) | Secrets management in Docker |
| [docker-testing.md](docker-testing.md) | Testing Docker builds |

### Architecture & Internals

| Document | Description |
|----------|-------------|
| [security-architecture.md](security-architecture.md) | LLM-based security layers |
| [server-integration.md](server-integration.md) | How Server integrates with Runtime |
| [prompt-management.md](prompt-management.md) | Centralized prompt loader system |
| [id-conventions.md](id-conventions.md) | ID format conventions (prefixes, nanoid) |
| [type-safety-guide.md](type-safety-guide.md) | TypedDict conventions |

## Key Concepts for Contributors

### Formation Loading

Formations are loaded from YAML files (`.afs`, `.yaml`, `.yml`) and validated against the [Agent Formation Spec](https://agentformation.org).

### Overlord

The Overlord is the central orchestrator that:
- Routes messages to appropriate agents
- Manages clarification flows
- Coordinates workflow decomposition
- Handles async operations

### Memory Systems

Three-tier memory architecture:

- **Working Memory**: Shared vector storage (always enabled)
- **Buffer Memory**: Recent conversation context (always enabled)
- **Persistent Memory**: Long-term SQLite/PostgreSQL storage

**Default Persistent Memory**: When `memory.persistent` is omitted from a formation, SQLite is automatically enabled with `memory.db` created in the formation directory. To disable:

```yaml
memory:
  persistent: false  # Explicitly disable
```

Or to disable while preserving config for later:

```yaml
memory:
  persistent:
    enabled: false
    connection_string: "postgresql://..."  # Preserved for later use
```

### Services

All runtime services (memory, MCP, A2A, LLM) are initialized during formation loading and available to agents.

## User Documentation

For user-facing documentation, see [docs.muxi.ai](https://docs.muxi.ai).
