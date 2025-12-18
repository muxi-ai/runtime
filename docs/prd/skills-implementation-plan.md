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
allowed-tools: Bash Read      # Optional/Experimental: pre-approved tools
---

# Instructions (markdown body)
```

### Progressive Disclosure

1. **Discovery** (~100 tokens): Load only name + description at startup
2. **Activation** (<5000 tokens): Load full SKILL.md when matched
3. **Execution** (as needed): Load scripts/references/assets on demand

## Design Proposal

### Architecture Overview

```
Formation YAML
     │
     ▼
┌─────────────────┐
│  SkillManager   │  ← New component
├─────────────────┤
│ - discovery     │  Scan directories for SKILL.md files
│ - indexing      │  Store embeddings in WorkingMemory
│ - activation    │  Load full skill on match
│ - execution     │  Handle script execution (sandboxed)
└────────┬────────┘
         │
    ┌────┴────┬──────────────┐
    ▼         ▼              ▼
Knowledge   SOPs          Skills
Handler    System        (new)
    │         │              │
    └─────────┴──────────────┘
              │
              ▼
      WorkingMemory/FAISS
      (unified search)
```

### Phase 1: Core Skill Support

**Goal**: Basic skill discovery, activation, and injection into agent context.

#### 1.1 SkillManager Component

Location: `src/muxi/formation/skills/`

```python
# skill_manager.py
class SkillManager:
    """
    Manages skill discovery, indexing, and activation.
    
    Follows progressive disclosure pattern:
    1. At startup: load only metadata (name, description)
    2. On match: load full SKILL.md content
    3. On demand: load scripts/references/assets
    """
    
    def __init__(
        self,
        skills_dirs: List[Path],           # Configured skill directories
        working_memory: WorkingMemory,      # For vector storage
        formation_path: Optional[Path] = None,
    ):
        self.skills_dirs = skills_dirs
        self.working_memory = working_memory
        self.formation_path = formation_path
        
        # Metadata-only index (loaded at startup)
        self.skills_metadata: Dict[str, SkillMetadata] = {}
        
        # Full content cache (loaded on activation)
        self._content_cache: Dict[str, SkillContent] = {}
        
        # MD5 hashes for change detection
        self._file_hashes: Dict[str, str] = {}
    
    async def discover_skills(self) -> int:
        """Scan directories and index skill metadata."""
        
    async def search_skills(
        self,
        query: str,
        top_k: int = 3,
        threshold: float = 0.7,
    ) -> List[SkillMetadata]:
        """Semantic search for relevant skills."""
        
    async def activate_skill(self, skill_name: str) -> SkillContent:
        """Load full skill content for agent context."""
        
    async def get_file_content(
        self,
        skill_name: str,
        relative_path: str,
    ) -> str:
        """Load a specific file from skill directory."""


@dataclass
class SkillMetadata:
    """Lightweight skill info (~100 tokens)."""
    name: str
    description: str
    path: Path
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)


@dataclass
class SkillContent:
    """Full skill content for agent context."""
    metadata: SkillMetadata
    instructions: str  # Markdown body
    scripts: List[str]  # Available script paths
    references: List[str]  # Available reference paths
    assets: List[str]  # Available asset paths
```

#### 1.2 Formation Configuration

```yaml
# formation.yaml
skills:
  enabled: true
  
  # Skill directories (searched in order)
  directories:
    - path: ./skills              # Relative to formation
    - path: ~/.muxi/skills        # User skills
    - path: /opt/muxi/skills      # System skills
  
  # Discovery settings
  discovery:
    recursive: true               # Scan subdirectories
    max_skills: 100               # Limit total skills loaded
  
  # Activation settings
  activation:
    auto_activate: true           # Auto-activate on query match
    threshold: 0.75               # Semantic similarity threshold
    max_active: 3                 # Max concurrent activated skills
  
  # Security settings
  execution:
    allow_scripts: false          # Disable script execution by default
    sandbox: true                 # Run scripts in sandbox (when enabled)
    allowed_tools: []             # Override allowed-tools from skills
    timeout_seconds: 30           # Script execution timeout
```

#### 1.3 Integration with Overlord

```python
# In overlord.py

async def _route_message(self, message: str, user_id: str) -> str:
    # 1. Search for relevant skills
    if self.skill_manager and self.skill_manager.enabled:
        matching_skills = await self.skill_manager.search_skills(
            query=message,
            top_k=3,
            threshold=0.75,
        )
        
        if matching_skills:
            # 2. Activate best matching skill
            skill = await self.skill_manager.activate_skill(
                matching_skills[0].name
            )
            
            # 3. Inject skill into context
            context_enhancement = self._format_skill_context(skill)
            # ... continue with enhanced context
```

### Phase 2: Script Execution (Future)

**Goal**: Safe execution of skill scripts with sandboxing.

#### 2.1 Script Executor

```python
class SkillScriptExecutor:
    """Execute skill scripts with security controls."""
    
    async def execute(
        self,
        script_path: Path,
        args: Dict[str, Any],
        timeout: float = 30.0,
    ) -> ExecutionResult:
        """Execute a skill script in sandboxed environment."""
```

#### 2.2 Security Considerations

- **Sandboxing**: Container/subprocess isolation
- **Allowlisting**: Only approved tools/commands
- **Confirmation**: User approval for sensitive operations
- **Logging**: Full audit trail of executions
- **Resource limits**: CPU, memory, network constraints

### Phase 3: Ecosystem Integration (Future)

**Goal**: Skill marketplace, versioning, and distribution.

- Skill validation CLI (`muxi skills validate`)
- Skill packaging and distribution
- Version management and updates
- Community skill repository

## Implementation Roadmap

### Sprint 1: Foundation (Week 1-2)

1. Create `src/muxi/formation/skills/` module structure
2. Implement `SkillMetadata` and `SkillContent` dataclasses
3. Implement SKILL.md parsing (frontmatter + body)
4. Basic skill discovery from directories

### Sprint 2: Integration (Week 3-4)

1. WorkingMemory integration for skill embeddings
2. Semantic search for skill matching
3. Formation configuration schema
4. Overlord integration for context injection

### Sprint 3: Polish (Week 5-6)

1. Caching with MD5 change detection
2. Progressive disclosure optimization
3. E2E tests for skill workflows
4. Documentation and examples

### Future Sprints

- Script execution with sandboxing
- Tool integration (MCP connection)
- Skill validation CLI
- Skill marketplace integration

## Relationship to Existing Systems

### Knowledge vs Skills

| Aspect | Knowledge | Skills |
|--------|-----------|--------|
| Purpose | Reference information | Executable procedures |
| Content | Documents, PDFs, etc. | Instructions + scripts |
| Discovery | Semantic search | Semantic search |
| Execution | Read-only | May execute scripts |
| Scope | Per-agent | Formation-wide |

### SOPs vs Skills

| Aspect | SOPs | Skills |
|--------|------|--------|
| Format | Custom YAML frontmatter | Agent Skills spec |
| Portability | MUXI-specific | Cross-platform |
| Scripts | Template-based | Full script support |
| Discovery | Semantic search | Semantic search |
| Ecosystem | Internal | Community-driven |

### Unification Opportunity

Consider a future "Capability" abstraction that unifies:
- Knowledge sources (reference docs)
- SOPs (internal procedures)
- Skills (portable capabilities)

## Open Questions

1. **Script execution**: Should we support script execution in v1, or defer to Phase 2?

2. **Tool integration**: How do skills interact with MCP tools? Should `allowed-tools` map to MCP tool names?

3. **Agent scope**: Should skills be formation-wide or per-agent? The spec doesn't specify.

4. **SOP migration**: Should we provide a migration path from SOPs to Skills format?

5. **Priority**: When both an SOP and a Skill match a query, which takes precedence?

## Success Metrics

1. **Discovery latency**: <100ms for skill search
2. **Context efficiency**: <500 tokens average for activated skill
3. **Developer adoption**: 10+ skills created within 3 months
4. **Compatibility**: Pass `skills-ref validate` for all bundled skills

## References

- [Agent Skills Specification](https://agentskills.io/specification)
- [Integration Guide](https://agentskills.io/integrate-skills)
- [skills-ref Reference Library](https://github.com/agentskills/agentskills/tree/main/skills-ref)
- [Anthropic Skills Examples](https://github.com/anthropics/skills)
