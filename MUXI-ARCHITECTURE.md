# MUXI Project Architecture

**Complete architectural overview of the MUXI ecosystem**

Version: 2.0.0  
Last Updated: 2025-12-24

---

## Table of Contents

1. [Overview](#overview)
2. [Strategic Context](#strategic-context)
3. [Repository Map](#repository-map)
4. [Core Components](#core-components)
5. [Supporting Infrastructure](#supporting-infrastructure)
6. [Go-to-Market Strategy](#go-to-market-strategy)
7. [Development Workflow](#development-workflow)
8. [Status & Roadmap](#status--roadmap)
9. [How It All Works Together](#how-it-all-works-together)

---

## Overview

**MUXI is a complete infrastructure platform for deploying and managing AI agents in production.**

Think of it as:
- **Server**: Like PM2 + Nginx for agents (orchestration)
- **Runtime**: Like Docker images for agents (execution environment)
- **Registry**: Like Docker Hub for agents (distribution)
- **CLI**: Like kubectl for agents (management)

**Philosophy:** Agents deserve infrastructure as native primitives, not hacked together with workflow tools.

**Key Positioning:** "We're infrastructure, not an agency. We built the runtime, not a service."

---

## Strategic Context

### The 5-Layer Moat

MUXI's competitive advantage is not a single feature but **concentric rings of defense**:

```
┌─────────────────────────────────────────────────────┐
│  Ring 5: Data Moat (Auto-Extend Learning)           │
├─────────────────────────────────────────────────────┤
│  Ring 4: Network Effects (Registry/Marketplace)     │
├─────────────────────────────────────────────────────┤
│  Ring 3: Standards Capture (Linux Foundation)       │
├─────────────────────────────────────────────────────┤
│  Ring 2: Ecosystem Compatibility (Skills, MCP, A2A) │
├─────────────────────────────────────────────────────┤
│  Ring 1: Technical Foundation (114k lines)          │
└─────────────────────────────────────────────────────┘
```

### Standards Play

The Formation specification (`schemas/`) is being donated to the **Agentic AI Foundation** under the Linux Foundation. This is the Docker/OCI playbook: define the standard, become the reference implementation.

### Enterprise Differentiator

MUXI is the **only AI agent platform with enterprise RBAC** (group-based permissions). This is delivered as a separate `muxi-enterprise` package that patches the runtime dynamically.

For detailed moat analysis, see: `runtime/MUXI_TECHNICAL_MOAT_ANALYSIS.md`

---

## Repository Map

```
muxi-ai/
│
├── server/              ✅ PRODUCTION READY
│   └── The orchestration platform (Go)
│       • Manages formation lifecycle
│       • HTTP reverse proxy
│       • HMAC authentication
│       • Port allocation & process management
│       • 91.2% test coverage
│
├── runtime/             ✅ PRODUCTION READY
│   └── Formation execution environment (Python)
│       • FastAPI-based Python runtime
│       • Packaged as SIF container
│       • 114,000+ lines of production code
│       • 215+ e2e tests across 12 areas
│
├── runtime-runner/      ✅ PRODUCTION READY
│   └── Runtime executor/wrapper (Go)
│       • Spawns and manages runtime containers
│       • Bridges server ↔ runtime
│       • Platform-specific execution
│
├── cli/                 ✅ COMPLETED
│   └── Command-line management tool (Go)
│       • muxi formation deploy/list/logs
│       • Server profile management
│       • Auto-detects local server
│
├── schemas/             ✅ FINALIZED → Linux Foundation
│   └── Formation YAML schemas
│       • Formation configuration spec
│       • API contracts (finalized)
│       • Being donated to Agentic AI Foundation
│
├── install/             ✅ COMPLETED
│   └── One-command installers
│       • curl | bash (Unix/Linux/macOS)
│       • PowerShell (Windows)
│       • Hosted at muxi.org/install
│
├── homebrew-tap/        ✅ COMPLETED
│   └── Homebrew package formulae
│       • muxi-server.rb
│       • muxi-cli.rb
│
├── registry/            ✅ COMPLETED
│   └── Formation distribution hub
│       • Like Docker Hub for formations
│       • Push/pull formations
│       • Version management
│       • Access control
│
└── sdks/                🏗️ IN PROGRESS
    └── Client SDKs for various languages
        • Python SDK
        • JavaScript/TypeScript SDK
        • Go SDK
```

---

## Core Components

### 1. **server/** - The Orchestration Platform ✅

**What it does:**
- Deploys and manages formations
- HTTP reverse proxy (formations bind to localhost, exposed via `/api/{id}/`)
- Process management with auto-restart
- Port allocation (8000-9000 pool)
- Version management (current/previous, rollback support)
- HMAC authentication for management API

**Technology:**
- Go (single binary, zero dependencies)
- Port 7890 (official "MUXI Port")
- Works on Linux, macOS, Windows

**Status:** Production-ready, 91.2% test coverage

---

### 2. **runtime/** - The Formation Execution Environment ✅

**What it does:**
- The actual environment where formations run
- FastAPI-based Python runtime
- Defines the formation API contract
- Packaged as Singularity SIF container

**Technology:**
- Python 3.10+ with async-first design
- FastAPI + Uvicorn
- Packaged as SIF (Singularity Image Format)
- Self-contained with all dependencies

**Key Capabilities:**
- Overlord orchestration engine (~9,800 lines)
- 3-tier memory architecture (Buffer → Persistent → Vector)
- 349 typed observability events across 5 categories
- MCP protocol integration (1,000+ tools)
- Agent Skills (SKILL.md) support
- Multi-user isolation via Memobase

**API Contract:**

```python
# Every formation implements:
GET  /health       # Health check
POST /chat         # Main interaction endpoint
GET  /info         # Formation metadata
```

**Status:** API finalized. Target public launch: January 2026

---

### 3. **runtime-runner/** - Runtime Executor ✅

**What it does:**
- Bridges the server and runtime
- Spawns runtime containers (SIF execution)
- Platform-specific process management
- Handles stdin/stdout/stderr

**Technology:**
- Go (matches server language)
- Executes Singularity containers

**Relationship:**

```
server → runtime-runner → runtime (SIF)
```

**Status:** Operational

---

### 4. **cli/** - Command-Line Tool ✅

**What it does:**
- Remote formation management
- Server profile management
- Auto-detects local server installation
- Deploy, list, logs, restart, delete formations

**Technology:**
- Go (matches server)
- HMAC request signing
- Auto-reads server credentials

**Usage:**

```bash
# Profile management
muxi server add production --url https://muxi.company.com

# Formation management
muxi formation deploy bundle.tar.gz
muxi formation list
muxi formation logs my-formation --follow
```

**Status:** Implemented

---

### 5. **schemas/** - Formation Schemas ✅

**What it does:**
- Defines formation YAML structure
- JSON Schema validation
- API contracts (finalized)
- Used by server, CLI, SDKs

**Strategic Importance:**
- Being donated to **Agentic AI Foundation** (Linux Foundation)
- Will become industry standard for AI agent definitions
- MUXI becomes the reference implementation

**Status:** Finalized, preparing for Linux Foundation donation

---

## Supporting Infrastructure

### 6. **install/** - Magic Installers ✅

**Scripts:**

```bash
# Unix/Linux/macOS
curl -sSL https://muxi.org/install | sudo bash

# Windows
irm https://muxi.org/install/windows.ps1 | iex
```

**Status:** Complete

---

### 7. **homebrew-tap/** - Package Manager ✅

**Formulae:**

```bash
brew install muxi-ai/tap/muxi-server
brew install muxi-ai/tap/muxi-cli
brew install muxi-ai/tap/muxi  # Meta-package
```

**Status:** Complete

---

### 8. **registry/** - Formation Distribution Hub ✅

**What it does:**
- Like Docker Hub for formations
- Push/pull formation bundles
- Version management
- Access control (public/private)
- Discoverability

**Usage:**

```bash
# Publishing
muxi formation publish my-agent:1.0.0

# Installing
muxi formation install community/sentiment-analyzer

# Searching
muxi registry search "customer support"
```

**Status:** Complete

---

### 9. **sdks/** - Client SDKs 🏗️

**Planned SDKs:**

```python
# Python SDK
from muxi import Client

client = Client(profile="production")
response = client.formation("my-agent").chat("Hello!")
```

```javascript
// JavaScript/TypeScript SDK
import { MuxiClient } from '@muxi/sdk';

const client = new MuxiClient({ profile: 'production' });
const response = await client.formation('my-agent').chat('Hello!');
```

```go
// Go SDK
import "github.com/muxi-ai/sdk-go"

client := muxi.NewClient("production")
resp, _ := client.Formation("my-agent").Chat("Hello!")
```

**Status:** In progress

---

## Go-to-Market Strategy

### OSS-First Approach

MUXI prioritizes **open-source adoption + professional support services** over traditional SaaS hosting. Cloud offering is deferred 12+ months to build community first.

### Revenue Model

```
OSS (Free)              → Community growth, ecosystem adoption
Priority Support        → $1K/mo, group Slack, expert guidance (GitHub Sponsors)
Private Support         → $2.5K/mo, private channel, monthly calls, faster SLA
Deployment Pilot        → $25K total, white-glove 3-month engagement
Enterprise              → $10-15K/mo, RBAC + ongoing support (annual)
Strategic Partner       → $20-25K/mo, dedicated engineer, product influence (annual)
Trail (Future, ~6mo)    → Observability SaaS dashboard
Cloud (Future, ~12mo+)  → Hosted platform (deferred)
```

### Key Differentiators

1. **Infrastructure, not agency** - "We built the runtime, not a service"
2. **Open source + expert support** - Transparent codebase, self-hosted
3. **Book authority** - "Production Agentic AI" by founder
4. **Enterprise RBAC** - Only AI agent platform with group-based permissions
5. **Standards capture** - Formation spec → Linux Foundation

---

## Development Workflow

### Phase 1: Foundation ✅ COMPLETE
1. Server - Built, tested, production-ready
2. Install scripts - Complete
3. Homebrew tap - Complete
4. Runtime - API finalized

### Phase 2: Tooling ✅ COMPLETE
1. CLI - Implemented
2. Schemas - Finalized
3. Registry - Complete

### Phase 3: Launch (Current - Target Jan 2026)
1. Runtime - Final testing, documentation
2. SDKs - In progress
3. Community - Building

### Phase 4: Growth (2026)
1. Trail - Observability SaaS (~6 months)
2. Enterprise - RBAC package
3. Auto-Extend - Self-evolving formations
4. Cloud - Hosted platform (12+ months)

---

## Status & Roadmap

| Repository | Status | Notes |
|------------|--------|-------|
| **server** | ✅ Production | 91.2% test coverage |
| **runtime** | ✅ API Finalized | Target: Jan 2026 launch |
| **runtime-runner** | ✅ Operational | - |
| **cli** | ✅ Implemented | - |
| **schemas** | ✅ Finalized | → Linux Foundation |
| **install** | ✅ Complete | muxi.org/install |
| **homebrew-tap** | ✅ Complete | - |
| **registry** | ✅ Complete | - |
| **sdks** | 🏗️ In Progress | Python, JS, Go |

### Upcoming Features (Q1 2026)

- **Agent Skills (SKILL.md)** - Open specification implementation
- **Enterprise Permissions** - Group-based RBAC (`muxi-enterprise` package)
- **Trail** - Observability SaaS dashboard

### Future (2026+)

- **Auto-Extend** - Self-evolving formations
- **Cloud Platform** - Hosted offering

---

## How It All Works Together

### User Installs MUXI

```bash
# Option 1: One-command (from install/)
curl -sSL https://muxi.org/install | sudo bash

# Option 2: Homebrew (from homebrew-tap/)
brew install muxi-ai/tap/muxi-server
```

---

### User Deploys Formation

```bash
# Via CLI (from cli/)
muxi formation deploy my-agent.tar.gz

# CLI talks to server/ API
# Server extracts bundle, validates against schemas/
# Server calls runtime-runner/ to spawn process
# runtime-runner/ executes runtime/ SIF container
```

---

### Formation Runs

```
User Request
    ↓
Server (:7890) - HTTP reverse proxy
    ↓
Formation Proxy (/api/my-agent/chat)
    ↓
Runtime (localhost:8001) - FastAPI app
    ↓
Formation Code - Your agent logic
```

---

### Distribution via Registry

```bash
# User publishes (via registry/)
muxi formation publish my-agent:1.0.0

# Other users install
muxi formation install community/sentiment-analyzer

# Registry serves formation bundles
# Server deploys from registry
```

---

## Key Design Decisions

### 1. Go + Python Split

| Component | Language | Why |
|-----------|----------|-----|
| Server | Go | Single binary, excellent concurrency, low memory |
| Runtime | Python | ML ecosystem, developer ergonomics |
| CLI | Go | Fast startup, easy distribution |
| SDKs | Multi | Meet developers where they are |

Go handles the hot path (orchestration, routing, auth). Python handles the AI workload (where async I/O is sufficient for LLM-bound operations).

### 2. Runtime as SIF

- No Python pollution on server
- Single-file distribution
- Container isolation
- HPC-friendly (Singularity native)

### 3. Separate Repos

- Server can evolve without breaking installers
- CLI can evolve independently
- Each repo has focused responsibility

### 4. Standards First

- Formation spec → Linux Foundation
- Agent Skills spec adoption (Anthropic)
- MCP protocol integration
- A2A protocol support

---

## Repository Dependencies

```
                    ┌─────────────┐
                    │   schemas   │ (Formation definitions → Linux Foundation)
                    └──────┬──────┘
                           │
              ┬────────────┼────────────┬
              │            │            │
              ↓            ↓            ↓
      ┌────────────┐  ┌────────────┐  ┌────────────┐
      │   server   │  │    cli     │  │    sdks    │
      └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
            │               │               │
            │               └───────┬───────┘
            ↓                       ↓
    ┌───────────────┐      Server API (HMAC)
    │ runtime-runner│
    └───────┬───────┘
            ↓
    ┌────────────┐
    │  runtime   │ (SIF container)
    └────────────┘

Distribution:
    ┌────────────┐
    │  registry  │ (Formation marketplace)
    └────────────┘

Installation:
    ┌────────────┐       ┌──────────────┐
    │  install   │       │ homebrew-tap │
    └────────────┘       └──────────────┘
```

---

## Quick Reference

### Installation
- **Scripts:** `muxi-ai/install`
- **Homebrew:** `muxi-ai/homebrew-tap`
- **Hosted at:** muxi.org/install

### Core Platform
- **Server:** `muxi-ai/server` (orchestration)
- **Runtime:** `muxi-ai/runtime` (execution environment)
- **Runner:** `muxi-ai/runtime-runner` (executor)

### Tooling
- **CLI:** `muxi-ai/cli` (management tool)
- **Schemas:** `muxi-ai/schemas` (validation → Linux Foundation)

### Distribution
- **Registry:** `muxi-ai/registry` (marketplace)
- **SDKs:** `muxi-ai/sdks` (client libraries)

---

## Contributing

Each repository has its own:
- `CONTRIBUTING.md` - Contribution guidelines
- `README.md` - Repository-specific docs
- Issue tracker - Repository-specific issues

**Start here:**
- Server work → `muxi-ai/server`
- Installation improvements → `muxi-ai/install`
- Formation schemas → `muxi-ai/schemas`
- Runtime development → `muxi-ai/runtime`

---

## License

All MUXI repositories use the **Elastic License 2.0** unless otherwise specified.

See individual repository LICENSE files for details.

---

## Links

- **Documentation:** https://muxi.org/docs
- **Website:** https://muxi.org
- **GitHub Org:** https://github.com/muxi-ai
- **Installation:** https://muxi.org/install

---

**Last Updated:** 2025-12-24  
**Version:** 2.0.0  
**Maintainer:** MUXI Core Team
