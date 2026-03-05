# MUXI Runtime

[![License](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](LICENSE)  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

The execution engine for AI agent formations.

> **For most users:** Install [MUXI CLI](https://github.com/muxi-ai/cli) for the complete experience.
> This repo is for contributors and developers embedding the runtime directly.

> [!IMPORTANT]
> ## MUXI Ecosystem
>
> This repository is part of the larger MUXI ecosystem.
>
> **📋 Complete architectural overview:** See [muxi/ARCHITECTURE.md](https://github.com/muxi-ai/muxi/blob/main/ARCHITECTURE.md) - explains how core repositories fit together, dependencies, status, and roadmap.

## What is MUXI Runtime?

MUXI Runtime transforms declarative YAML configurations into running AI systems. It's the core engine that powers the [MUXI Server](https://github.com/muxi-ai/server).

**Core responsibilities:**
- Formation execution - Loads and runs agent configurations from YAML
- Overlord orchestration - Routes requests, manages clarifications, coordinates workflows
- Memory systems - Three-tier memory (buffer, persistent, vector)
- Tool integration - MCP protocol support for external tools
- Multi-tenant isolation - User and session management

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  MUXI Server (Go) - Formation lifecycle management  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  MUXI Runtime (Python) ◄── THIS REPO                │
│  ┌───────────────────────────────────────────────┐  │
│  │  Formation Engine (YAML loader & validator)   │  │
│  ├───────────────────────────────────────────────┤  │
│  │  Overlord │ Agents │ Workflow │ Background    │  │
│  ├───────────────────────────────────────────────┤  │
│  │  Memory │ MCP │ A2A │ LLM │ Observability     │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  External Services (LLM APIs, MCP Servers, DBs)     │
└─────────────────────────────────────────────────────┘
```

## Package Structure

The runtime uses `src/muxi/runtime/` to share the `muxi` namespace with the [Python SDK](https://github.com/muxi-ai/sdks):

```
src/muxi/runtime/
├── formation/          # Formation engine
│   ├── overlord/       # Central orchestration
│   ├── agents/         # Agent implementations
│   ├── workflow/       # Task decomposition, SOPs
│   ├── server/         # Formation API (FastAPI)
│   └── background/     # Webhooks, scheduling, async
├── services/           # Runtime services
│   ├── memory/         # Memory systems
│   ├── mcp/            # MCP client
│   ├── a2a/            # Agent-to-agent
│   └── llm/            # LLM abstraction
└── datatypes/          # Type definitions
```

## Quick Start

### Using with MUXI Server (recommended)

```bash
# Install MUXI CLI
curl -fsSL https://muxi.ai/install | sh

# Create and run a formation
muxi new my-assistant
cd my-assistant
muxi dev
```

### Embedding directly

```bash
pip install muxi-runtime
```

```python
from muxi.runtime import Formation
import asyncio

async def main():
    formation = Formation()
    await formation.load("formation.afs")
    overlord = await formation.start_overlord()

    response = await overlord.chat(
        "Hello!",
        user_id="user123"
    )
    print(response)

asyncio.run(main())
```

## Development

```bash
git clone https://github.com/muxi-ai/runtime
cd runtime
pip install -e ".[dev]"

# Run tests
pytest tests/unit -v
pytest tests/integration -v
pytest e2e/tests -v
```

See [contributing/README.md](contributing/README.md) for contributor documentation.

## Related Repositories

| Repo | Description |
|------|-------------|
| [muxi-ai/muxi](https://github.com/muxi-ai/muxi) | Main repo with architecture docs |
| [muxi-ai/server](https://github.com/muxi-ai/server) | Go server that hosts this runtime |
| [muxi-ai/cli](https://github.com/muxi-ai/cli) | Command-line tool |
| [muxi-ai/sdks](https://github.com/muxi-ai/sdks) | Python, TypeScript, Go SDKs |
| [muxi-ai/schemas](https://github.com/muxi-ai/schemas) | API schemas |

## Documentation

- **User docs:** [docs.muxi.ai](https://docs.muxi.ai)
- **Contributor docs:** [contributing/README.md](contributing/README.md)
- **Formation spec:** [agentformation.org](https://agentformation.org)

## License

[Elastic License 2.0](LICENSE) - Free to use, modify, and embed in products. Cannot be offered as a hosted service.
