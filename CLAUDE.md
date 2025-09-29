# MUXI Runtime Development Guide

Critical development context for the MUXI Runtime execution engine.

## Quick Reference
**See AGENTS.md for the operational playbook and TL;DR checklist.**
Use AGENTS.md for routine tasks, this file for architectural context and complex debugging.

## Core Architecture Principles

### Formation-First Architecture
Everything starts with a formation YAML that defines the entire AI system. The runtime transforms these declarative configurations into living AI systems.

### System Components
```
Formation Engine → Overlord Orchestrator → Agent Pool
       ↓                    ↓                  ↓
   Validation          Coordination       Execution
       ↓                    ↓                  ↓
Memory Systems ← Services Layer → Tool Integration
```

### Critical Patterns
1. **Provider-Agnostic Design**: OneLLM abstracts all LLM providers
2. **SOP-Enhanced Orchestration**: Standard Operating Procedures guide complex workflows
3. **Three-Tier Memory**: Buffer (FIFO+vector) → Persistent (DB) → Vector (FAISSx)
4. **Unified Services**: MCP, A2A, Multimodal, Scheduler, Observability
5. **Multi-User Isolation**: Memobase partitioning for user contexts

## Project Structure
See `context/project-structure.md` for details.

## Development Standards
See AGENTS.md sections:
- Development Standards
- Testing Discipline
- Workflow Basics
- Hard Rules Checklist

## Sub-Agent Usage
**See AGENTS.md "Sub-Agent Protocol" for when and how to use sub-agents.**

## Code Review
Use CodeRabbit CLI for continuous code review - see AGENTS.md for protocol.

## Recent Architectural Changes

### August 2025: Clarification System Improvements

**Impact**: Fixed critical context preservation bug and improved context switch detection.

1. **Context Preservation Fix**:
   - Fixed bug in overlord.py line 5610 that was replacing enhanced message after clarification
   - Ensured buffer memory context is preserved throughout clarification flow

2. **Context Switch Detection**:
   - UnifiedClarificationSystem now tracks `last_question` asked
   - Enables accurate detection of whether user is answering clarification vs making new request
   - Prevents misinterpretation of answers like "REST API endpoint" as new requests

### August 2025: SOP System Refactoring

**Impact**: SOPs moved from orchestration to workflow layer for better separation of concerns.

- Moved `src/muxi/formation/overlord/sops.py` → `src/muxi/formation/workflow/sops.py`
- SOPs are workflow concerns, not orchestration concerns
- Fixed resource_map population for [file:] reference resolution
- Updated all imports in overlord and tests

### July 2025: Resilience Integration

**Impact**: Production-ready error recovery with user-friendly messages.

1. **ResilientWorkflowExecutor Integration**:
   - Wraps WorkflowExecutor with intelligent error handling
   - Classifies errors: timeout, rate limit, network, auth
   - Progressive error messages with recovery strategies
   - Circuit breaker protection against cascading failures

2. **Configuration Schema**:
   ```yaml
   resilience:
     enable_workflow_resilience: true
     circuit_breaker:
       failure_threshold: 3
       timeout: 60
   ```

### July 2025: Enhanced Workflow Configuration

**Impact**: Advanced workflow execution with configurable strategies.

1. **Configuration System** (`src/muxi/formation/workflow/config.py`):
   - ComplexityMethod: heuristic, llm, custom, hybrid
   - TaskRoutingStrategy: capability_based, load_balanced, round_robin
   - ErrorRecoveryStrategy: retry_with_backoff, fail_fast, skip_and_continue
   - Workflow-specific overrides with pattern matching

2. **Enhanced Execution**:
   - Agent affinity tracking for optimal task assignment
   - Adaptive timeouts based on task complexity
   - Resource limits and parallel execution control
   - Detailed metrics collection and reporting

### July 2025: Workflow Integration

**Impact**: Automatic task decomposition for complex requests.

- Enhanced `_process_sync_chat` with workflow analysis
- Complexity scoring triggers automatic decomposition
- Approval workflows for high-stakes operations (complexity >= 7)
- Routes to `_process_with_workflow()` for complex tasks

Configuration:
- `auto_decomposition`: Enable automatic workflow decomposition (default: True)
- `complexity_threshold`: Threshold for triggering workflows (default: 7.0)

## Critical System Requirements

### LLM Configuration (REQUIRED)
```yaml
llm:
  models:
    - text: "openai/gpt-4o-mini"  # REQUIRED - No fallback!
```
See AGENTS.md "System Requirements & Guarantees" for full requirements.

### Formation Loading Order (Critical)
1. Observability → 2. LLM Configuration → 3. Memory Systems → 4. Document Processing → 5. Background Services → 6. Agents

### Error Handling Philosophy
- Fail fast for critical configuration
- Log and continue for optional features
- Graceful degradation when external services unavailable
- User-friendly messages through resilience layer

### Multilingual Support Philosophy
Always use LLM over pattern matching for any user-facing text processing.
See AGENTS.md for examples.

## Runtime Behavior Notes

### ID Hierarchy and Roles

```
user_id (user isolation)
  └── session_id (chat grouping)
      └── request_id (single interaction with all clarifications)
```

**request_id**: Tracks ONE complete interaction including all clarifications. Used as key for `clarification:{request_id}`.

**session_id**: Groups multiple requests into a conversation. Used for buffer memory filtering.

**user_id**: User isolation in multi-user mode. Normalized to lowercase, "0" for single-user mode.

**Clarification State Coordination**:
- Overlord: `_pending_clarification[session_id]` → returns `request_id`
- UnifiedClarificationSystem: `clarification:{request_id}` → clarification state
- **DO NOT attempt to "fix" this two-level lookup - it's intentional and correct**

## Testing Philosophy
See AGENTS.md "Testing Philosophy" section.

## Common Issues & Troubleshooting
See AGENTS.md "Troubleshooting Cheatsheet" section.

## Development Patterns
See AGENTS.md "Development Patterns" section.

## Critical Files
- `src/muxi/formation/formation.py` - Formation loading and lifecycle
- `src/muxi/formation/overlord/overlord.py` - Central orchestration
- `src/muxi/formation/workflow/` - Workflow execution and SOPs
- `src/muxi/formation/resilience/` - Error recovery layer
- `src/muxi/services/` - All runtime services
- `schemas/formation/formation.yaml` - Configuration schema

## Tone and Behavior
- Be skeptical and concise
- Criticism is welcome
- No flattery or compliments unless asked
- Ask questions instead of guessing intent
- See AGENTS.md "Collaboration Norms" for full guidelines

## Absolute Rules
See AGENTS.md "Hard Rules Checklist" - these are non-negotiable.

## Reflection Protocol
See AGENTS.md "Reflection Protocol" section for the self-improvement process.

## Operational Notes
- Always run e2e tests using: `bash .claude/scripts/test-and-log.sh tests/e2e/path/to/test.py`
- MUXI uses `secrets.env` files beside formation YAMLs (never environment variables)
- See AGENTS.md "Operational Notes" for more details
- We do not use environment variables. Everything we need is/should be confined to secrets