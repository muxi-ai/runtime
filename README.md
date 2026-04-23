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
│     MUXI Server - Formation lifecycle management    │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│           MUXI Runtime ◄── THIS REPO                │
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
│   External Services (LLM APIs, MCP Servers, DBs)    │
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

## Docker Images

MUXI Runtime ships three image variants. All support `linux/amd64` and `linux/arm64` (except CUDA).

**Most users should use the base variant.** The PyTorch and CUDA variants exist for specific embedding workloads described below.

| Variant | SIF size | Description | Status |
|---------|----------|-------------|--------|
| `default` (base) | ~600 MB | Lean runtime — covers the vast majority of use cases | Stable |
| `pytorch` | larger | Adds CPU-only PyTorch for local embedding models that lack ONNX exports | Stable |
| `cuda` | largest | GPU-accelerated: ONNX and PyTorch local models + FAISS-GPU for faster vector ops | **Experimental** |

**When to use each variant:**

- **`default`** — the right choice for almost everyone. Uses ONNX-based local embedding models (fast, lightweight) and CPU FAISS.
- **`pytorch`** — only needed when you want to run a local embedding model that does not have an ONNX export and therefore requires the full PyTorch runtime.
- **`cuda`** — recommended for production workloads running on servers with NVIDIA GPUs. Supports both ONNX and PyTorch local models, and ships with FAISS-GPU for significantly faster vector similarity operations.

```bash
# Build the default (base) variant
./scripts/build/runtime.sh

# Build the PyTorch variant (requires default built first)
./scripts/build/runtime.sh --variant pytorch

# Build the CUDA variant (experimental, linux/amd64 + NVIDIA tooling required)
./scripts/build/runtime.sh --variant cuda

# Cross-compile for a specific platform
./scripts/build/runtime.sh --platform linux/amd64 --variant pytorch
```

### SIF (Singularity/Apptainer)

Each variant can be converted to a `.sif` artifact for use with MUXI Server:

```bash
./scripts/build/sif.sh                        # default
./scripts/build/sif.sh --variant pytorch
./scripts/build/sif.sh --variant cuda         # experimental
./scripts/build/sif.sh --arch amd64           # force architecture
```

> **Note:** On macOS and Windows the correct SIF architecture is always `linux-amd64`, regardless of host CPU. `linux-arm64` SIFs only apply on native arm64 Linux hosts (e.g. AWS Graviton).
>
> **CUDA variant is experimental.** It has not been end-to-end validated against live GPUs in CI and only builds on `linux/amd64` hosts with NVIDIA tooling.

## Development

```bash
git clone https://github.com/muxi-ai/runtime
cd runtime
pip install -e ".[dev]"

# Unit and integration tests
pytest tests/unit -v
pytest tests/integration -v

# E2E tests (standalone scripts, not pytest)
cd e2e && python run_all_tests.py          # full suite
cd e2e && python run_random_tests.py 10    # random sample
cd e2e/tests/<area> && python test_<name>.py  # single test
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
