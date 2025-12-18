---
title: Agent Skills Implementation Plan
type: prd
status: draft
created: 2025-12-18
author: MUXI Team
---

# Agent Skills Implementation Plan

## Executive Summary

This document outlines the plan for implementing Agent Skills support in MUXI Runtime, following the open [Agent Skills specification](https://agentskills.io/specification). Skills represent a "knowledge++" capability - extending beyond static reference documents to include executable scripts, templates, and structured workflows.

---

## Design Decisions

### Skill Location

Skills live in a fixed, explicit location within the formation directory:

```
formation/
├── formation.yaml
├── skills/
│   ├── pdf-processing/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── references/
│   ├── data-analysis/
│   │   └── SKILL.md
│   └── ticket-handling/
│       └── SKILL.md
└── agents/
    └── ...
```

### Explicit Loading (No Auto-Discovery)

Unlike MCP tools and agents, skills are **not** auto-loaded. They must be explicitly declared:

```yaml
# formation.yaml

# Formation-level skills - "public", available to all agents
skills:
  - pdf-processing
  - data-analysis

agents:
  - name: support-agent
    description: "Handles customer support tickets"
    # Agent-specific skills - belongs to this agent only
    skills:
      - ticket-handling
```

### Skill Scoping

| Scope | Declaration | Availability |
|-------|-------------|--------------|
| **Public** | Formation-level `skills:` | All agents can use |
| **Private** | Agent-level `skills:` | Only that agent |

### Overlord Routing Enhancement

Skill descriptions are injected into agent specialties to improve routing decisions:

```python
# During formation loading, agent metadata is enhanced:

support_agent.specialties = [
    "Handles customer support tickets",       # from agent description
    "Handle support tickets and escalations", # from ticket-handling skill description
]

# Overlord knows which skills each agent has:
support_agent.skills = {
    "private": ["ticket-handling"],
    "public": ["pdf-processing", "data-analysis"],
}
```

This allows Overlord to make smarter routing decisions:
- "User needs PDF extraction" -> route to agent with `pdf-processing` skill
- "User has a support ticket" -> route to `support-agent` (has `ticket-handling`)

---

## Agent Skills Specification Summary

### Core Concepts

```
skill-name/
├── SKILL.md          # Required: YAML frontmatter + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: additional documentation
└── assets/           # Optional: templates, resources
```

### SKILL.md Format

```yaml
---
name: pdf-processing           # Required: 1-64 chars, lowercase + hyphens
description: Extract text...   # Required: 1-1024 chars
license: Apache-2.0            # Optional
compatibility: Claude Code     # Optional: environment requirements
metadata:                      # Optional: arbitrary key-value
  author: example-org
  version: "1.0"
allowed-tools: Bash Read       # Optional/Experimental: pre-approved tools
---

# Instructions (markdown body)
```

### Progressive Disclosure

1. **Discovery** (~100 tokens): Load only name + description at startup
2. **Activation** (<5000 tokens): Load full SKILL.md when matched
3. **Execution** (as needed): Load scripts/references/assets on demand

---

## Current State Analysis

### Existing Systems

MUXI currently has two related systems that handle similar concerns:

1. **Knowledge System** (`src/muxi/formation/agents/knowledge/`)
   - FileKnowledge for loading local files and directories
   - Vector embeddings via FAISS for semantic search
   - Document chunking with DocumentChunkManager
   - MD5-based caching for smart reindexing
   - Supports markitdown for diverse file formats (PDF, DOCX, etc.)

2. **SOP System** (`src/muxi/formation/workflow/sops.py`)
   - YAML frontmatter metadata parsing
   - Semantic search for procedure discovery
   - Template and guide execution modes
   - File reference resolution (`[file:path]`)
   - WorkingMemory/FAISS integration

### Key Patterns to Leverage

- Progressive disclosure (metadata at startup, full content on activation)
- Semantic search for discovery
- MD5 hash caching for change detection
- WorkingMemory integration for vector storage
- YAML frontmatter conventions

---

## Architecture

### Component Overview

```
Formation YAML
     │
     ├── skills: [pdf-processing, data-analysis]  (public)
     │
     └── agents:
           └── support-agent:
                 └── skills: [ticket-handling]    (private)
     │
     ▼
┌─────────────────┐
│  SkillLoader    │  <- Formation loading
├─────────────────┤
│ - parse config  │  Read skills: arrays
│ - load metadata │  Parse SKILL.md frontmatter only
│ - validate      │  Check skill exists in skills/
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SkillManager   │  <- Runtime component
├─────────────────┤
│ - indexing      │  Store embeddings in WorkingMemory
│ - activation    │  Load full SKILL.md on demand
│ - routing info  │  Provide skill metadata to Overlord
└────────┬────────┘
         │
         ▼
   WorkingMemory/FAISS
   (semantic search)
```

### SkillManager Component

Location: `src/muxi/formation/skills/`

```python
@dataclass
class SkillMetadata:
    """Lightweight skill info (~100 tokens) - loaded at startup."""
    name: str
    description: str
    path: Path
    scope: Literal["public", "private"]
    owner_agent: Optional[str] = None  # Agent name if private
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)


@dataclass
class SkillContent:
    """Full skill content - loaded on activation."""
    metadata: SkillMetadata
    instructions: str  # Markdown body
    scripts: List[str]  # Available script paths
    references: List[str]  # Available reference paths
    assets: List[str]  # Available asset paths


class SkillManager:
    """
    Manages skill loading, indexing, and activation.
    
    Skills are explicitly loaded based on formation config,
    NOT auto-discovered from the skills/ directory.
    """
    
    def __init__(
        self,
        formation_path: Path,
        working_memory: WorkingMemory,
    ):
        self.formation_path = formation_path
        self.skills_dir = formation_path / "skills"
        self.working_memory = working_memory
        
        # Loaded skill metadata (keyed by skill name)
        self.skills: Dict[str, SkillMetadata] = {}
        
        # Skill-to-agent mapping
        self.public_skills: List[str] = []
        self.agent_skills: Dict[str, List[str]] = {}  # agent_name -> [skill_names]
        
        # Full content cache (loaded on activation)
        self._content_cache: Dict[str, SkillContent] = {}
        
        # MD5 hashes for change detection
        self._file_hashes: Dict[str, str] = {}
    
    def load_public_skills(self, skill_names: List[str]) -> None:
        """Load formation-level (public) skills."""
        for name in skill_names:
            self._load_skill(name, scope="public")
            self.public_skills.append(name)
    
    def load_agent_skills(self, agent_name: str, skill_names: List[str]) -> None:
        """Load agent-specific (private) skills."""
        self.agent_skills[agent_name] = []
        for name in skill_names:
            self._load_skill(name, scope="private", owner_agent=agent_name)
            self.agent_skills[agent_name].append(name)
    
    def get_agent_skill_descriptions(self, agent_name: str) -> List[str]:
        """Get skill descriptions for agent specialty enhancement."""
        descriptions = []
        # Add private skills
        for skill_name in self.agent_skills.get(agent_name, []):
            if skill_name in self.skills:
                descriptions.append(self.skills[skill_name].description)
        # Add public skills
        for skill_name in self.public_skills:
            if skill_name in self.skills:
                descriptions.append(self.skills[skill_name].description)
        return descriptions
    
    def get_available_skills(self, agent_name: str) -> List[str]:
        """Get all skills available to an agent (private + public)."""
        private = self.agent_skills.get(agent_name, [])
        return private + self.public_skills
    
    async def search_skills(
        self,
        query: str,
        agent_name: Optional[str] = None,
        top_k: int = 3,
    ) -> List[SkillMetadata]:
        """Semantic search for relevant skills (scoped to agent if provided)."""
        
    async def activate_skill(self, skill_name: str) -> SkillContent:
        """Load full skill content for agent context."""
        
    async def get_file_content(
        self,
        skill_name: str,
        relative_path: str,
    ) -> str:
        """Load a specific file from skill directory."""
```

### Formation Loading Integration

```python
# In formation_loader.py

async def _load_skills(self, config: Dict[str, Any]) -> None:
    """Load skills based on explicit configuration."""
    
    # Initialize SkillManager
    self.skill_manager = SkillManager(
        formation_path=self.formation_path,
        working_memory=self.working_memory,
    )
    
    # Load public (formation-level) skills
    public_skills = config.get("skills", [])
    if public_skills:
        self.skill_manager.load_public_skills(public_skills)
    
    # Load private (agent-level) skills
    for agent_config in config.get("agents", []):
        agent_name = agent_config.get("name")
        agent_skills = agent_config.get("skills", [])
        if agent_skills:
            self.skill_manager.load_agent_skills(agent_name, agent_skills)
```

### Overlord Integration

```python
# In overlord.py - during agent initialization

def _enhance_agent_specialties(self, agent: Agent) -> None:
    """Enhance agent specialties with skill descriptions."""
    if self.skill_manager:
        skill_descriptions = self.skill_manager.get_agent_skill_descriptions(
            agent.name
        )
        agent.specialties.extend(skill_descriptions)


# In overlord.py - during message routing

async def _route_with_skills(self, message: str, agent: Agent) -> str:
    """Check for relevant skills and inject into context."""
    if self.skill_manager:
        available_skills = self.skill_manager.get_available_skills(agent.name)
        matching_skills = await self.skill_manager.search_skills(
            query=message,
            agent_name=agent.name,
            top_k=2,
        )
        
        if matching_skills:
            # Activate and inject best match
            skill = await self.skill_manager.activate_skill(
                matching_skills[0].name
            )
            context_enhancement = self._format_skill_context(skill)
            # ... inject into agent context
```

---

## Script Execution

### Spec Analysis

The Agent Skills specification is **intentionally agnostic** about script execution. Looking at Anthropic's reference skills (e.g., `pdf`, `docx`):

1. **Scripts are standalone CLI tools** - Standard executables accepting command-line arguments
2. **No async/callback standard** - Execution model depends on the "Skill Client" (runtime)
3. **Simple I/O contract**:
   - Input: command-line arguments, stdin, environment variables
   - Output: stdout, stderr, exit codes, generated files
4. **SKILL.md documents usage** - Instructions tell the agent how to invoke scripts

Example from `pdf` skill:
```
scripts/
├── check_fillable_fields.py      # python check_fillable_fields.py input.pdf
├── extract_form_field_info.py    # python extract_form_field_info.py --output fields.json input.pdf
├── fill_pdf_form_with_annotations.py
└── convert_pdf_to_images.py
```

**Implication**: Pre-existing skills are portable to MUXI as long as we support standard CLI execution.

### MUXI Executor Container

**Architecture:**

```
┌─────────────────────────────────────────────────────┐
│  MUXI Runtime                                       │
│  ├── SkillManager                                   │
│  ├── Future: RCE, custom tools                      │
│  └── ExecutorClient (ZeroMQ)                        │
└──────────────────┬──────────────────────────────────┘
                   │ ZeroMQ (REQ/REP)
                   ▼
┌─────────────────────────────────────────────────────┐
│  muxi/executor container                            │
│  ├── ZeroMQ server (configurable port)              │
│  ├── Python 3.11+, Node 20+, Bash, common libs      │
│  ├── /skills (mounted read-only from formation)     │
│  └── Process isolation per execution                │
└─────────────────────────────────────────────────────┘
```

**Lifecycle:**
1. Runtime starts -> spawn `muxi/executor` container
2. Mount `{formation}/skills/` to `/skills` (read-only)
3. Container runs ZeroMQ server, awaits requests
4. Monitor restarts container on crash

**Message Protocol:**

```python
# Request
{
    "id": "req-123",
    "type": "execute",
    "command": "python",
    "args": ["/skills/pdf-processing/scripts/extract.py", "/tmp/input.pdf"],
    "cwd": "/tmp",
    "timeout": 30,
    "env": {}  # optional
}

# Response
{
    "id": "req-123",
    "status": "success" | "error" | "timeout",
    "stdout": "...",
    "stderr": "...",
    "exit_code": 0,
    "duration_ms": 1234
}
```

**Key Design Points:**

1. **Standard CLI execution** - Matches spec pattern, enables skill portability
2. **Replaceable Dockerfile** - Ship default, developers can customize
3. **ZeroMQ REQ/REP** - Matches FAISSx pattern, async-friendly
4. **Process isolation** - Each script in subprocess within container
5. **Mounted skills/** - Read-only, scripts can access sibling files
6. **Monitor/restart** - Ephemeral execution, container restarts on crash

**Default Container Contents:**

```dockerfile
FROM python:3.11-slim

# Common tools
RUN apt-get update && apt-get install -y \
    nodejs npm \
    poppler-utils \
    qpdf \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Common Python libraries (from Anthropic skills)
RUN pip install --no-cache-dir \
    pypdf pdfplumber reportlab \
    python-docx openpyxl python-pptx \
    pillow pytesseract pdf2image \
    pandas numpy \
    pyzmq

# ZeroMQ executor server
COPY executor_server.py /app/
CMD ["python", "/app/executor_server.py"]
```

**Configuration:**

```yaml
# formation.yaml
executor:
  enabled: true
  image: muxi/executor:latest  # or custom image
  port: 5560
  timeout_default: 30
  restart_policy: always
  resource_limits:
    memory: 2g
    cpu: 1.0
```

### Reusability

The executor container is a general-purpose component that can serve:
- **Skill script execution** (first consumer)
- **RCE for ad-hoc code** (future)
- **Custom tool execution** (future)
- **Sandbox for persistent agents** (future, see rce-sandboxing.md)

---

## Implementation Roadmap

### Phase 1: Core Skill Support (Weeks 1-3)

1. Create `src/muxi/formation/skills/` module structure
2. Implement `SkillMetadata` and `SkillContent` dataclasses
3. Implement SKILL.md parsing (frontmatter + body)
4. Explicit skill loading from formation config
5. Public vs private skill scoping
6. Agent specialty enhancement with skill descriptions

### Phase 2: Semantic Search (Weeks 4-5)

1. WorkingMemory integration for skill embeddings
2. Semantic search scoped to available skills
3. Skill activation and context injection
4. MD5 caching for change detection

### Phase 3: Executor Container (Weeks 6-8)

1. Create `muxi/executor` Docker image
2. Implement ZeroMQ executor server
3. Implement `ExecutorClient` in runtime
4. Container lifecycle management (spawn, monitor, restart)
5. Integration with SkillManager for script execution
6. Configuration schema for executor settings

### Phase 4: Polish (Weeks 9-10)

1. E2E tests for skill workflows
2. E2E tests for script execution
3. Documentation and examples
4. Validation CLI (`muxi skills validate`)
5. Pre-built skills bundle (pdf, docx, etc.)

---

## Relationship to Existing Systems

### Knowledge vs Skills

| Aspect | Knowledge | Skills |
|--------|-----------|--------|
| Purpose | Reference information | Executable procedures |
| Content | Documents, PDFs, etc. | Instructions + scripts |
| Loading | Auto-discovered | Explicit declaration |
| Scope | Per-agent only | Public or per-agent |
| Execution | Read-only | May execute scripts |

### SOPs vs Skills

| Aspect | SOPs | Skills |
|--------|------|--------|
| Format | Custom YAML frontmatter | Agent Skills spec |
| Loading | Auto-discovered from sops/ | Explicit declaration |
| Portability | MUXI-specific | Cross-platform |
| Scripts | Template-based | Full script support |
| Ecosystem | Internal | Community-driven |

---

## Success Metrics

1. **Loading time**: <50ms per skill metadata load
2. **Search latency**: <100ms for skill search
3. **Context efficiency**: <500 tokens average for activated skill
4. **Developer adoption**: 10+ skills created within 3 months
5. **Compatibility**: Pass `skills-ref validate` for all bundled skills

---

## Skill Portability

**Goal**: Enable developers to use pre-existing skills from the community without modification.

**Requirements for portability:**

1. Standard CLI execution pattern (command + args)
2. Common libraries pre-installed in executor container
3. Read-only access to skill directory (`/skills/{skill-name}/`)
4. Standard I/O (stdout, stderr, exit codes)

**Testing portability:**

```bash
# Validate skill structure
muxi skills validate ./skills/pdf-processing

# Test script execution
muxi skills exec pdf-processing scripts/extract.py --input test.pdf
```

**Bundling community skills:**

```yaml
# formation.yaml
skills:
  - pdf           # from skills/ directory
  - docx
  - xlsx
```

Developers can copy skills from [anthropics/skills](https://github.com/anthropics/skills) directly into their formation's `skills/` directory.

---

## References

- [Agent Skills Specification](https://agentskills.io/specification)
- [Integration Guide](https://agentskills.io/integrate-skills)
- [skills-ref Reference Library](https://github.com/agentskills/agentskills/tree/main/skills-ref)
- [Anthropic Skills Examples](https://github.com/anthropics/skills)
- [MUXI RCE Sandboxing PRD](./rce-sandboxing.md)
