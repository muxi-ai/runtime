# CLAUDE.md - MUXI Runtime Development Guide

Critical development context for the MUXI Runtime execution engine.

> Think carefully and implement the most concise solution that changes as little code as possible.

## Core Architecture Principles

### Formation-First Architecture
Everything starts with a formation YAML that defines the entire AI system. The runtime transforms these declarative configurations into living AI systems with sophisticated orchestration, memory management, and tool integration.

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

## MUXI Runtime Project Structure

MUXI Runtime is organized as a Python package with comprehensive test coverage and documentation:

```
runtime/
├── src/muxi/runtime/      # Core runtime engine
├── tests/                 # Comprehensive test suite
├── docs/                  # Documentation
├── test-formations/       # Example formations
├── schemas/               # YAML schema definitions
├── examples/              # Usage examples
└── migrations/            # Database migrations
```

You can find more information about the project structure in the `context/project-structure.md` file.

## USE SUB-AGENTS FOR CONTEXT OPTIMIZATION

### 1. Always use the file-analyzer sub-agent when asked to read files.
The file-analyzer agent is an expert in extracting and summarizing critical information from files, particularly log files and verbose outputs. It provides concise, actionable summaries that preserve essential information while dramatically reducing context usage.

### 2. Always use the code-analyzer sub-agent when asked to search code, analyze code, research bugs, or trace logic flow.

The code-analyzer agent is an expert in code analysis, logic tracing, and vulnerability detection. It provides concise, actionable summaries that preserve essential information while dramatically reducing context usage.

### 3. Always use the test-runner sub-agent to run tests and analyze the test results.

Using the test-runner agent ensures:

- Full test output is captured for debugging
- Main conversation stays clean and focused
- Context usage is optimized
- All issues are properly surfaced
- No approval dialogs interrupt the workflow

#### Note about e2e tests

Ensure every test ends up with a summary and the correspondence between the user and the overlord.

After all the logs are printed, add:

```
========================================

### Test Result:
  🎉 SUCCESS: ...
  ✓ ...
  ✓ ...
  ✓ ...

========================================

### Chat transcript:

User: ...
System: ...
User: ...
System: ...
```

## Recent Architectural Changes

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

The formation MUST have a text model configured:
```yaml
llm:
  models:
    - text: "openai/gpt-4o-mini"  # REQUIRED - No fallback!
    - vision: "..."                # Optional, falls back to text
    - audio: "..."                 # Optional, falls back to text
```

**No default models** - System fails fast if text model is missing.

### Formation Loading Order (Critical)

1. **Observability** - Must be first for logging
2. **LLM Configuration** - Validated before anything else
3. **Memory Systems** - Three-tier initialization
4. **Document Processing** - Multimodal setup
5. **Background Services** - Async operations
6. **Agents** - Loaded last with full context

### Error Handling Philosophy

- **Fail fast** for critical configuration (missing text model)
- **Log and continue** for optional features (extraction model)
- **Graceful degradation** when external services unavailable
- **User-friendly messages** through resilience layer

### Multilingual Support Philosophy

**Always use LLM over pattern matching** for any user-facing text processing:
- **Avoid regex/patterns** - They only work for English
- **Use LLM for parsing** - Understands intent in any language
- **No hardcoded strings** - Use LLM to detect patterns/commands
- **Intent over syntax** - Focus on what user means, not exact words

Example: Instead of `if re.match(r'^(help|assist)', message)`, use LLM to detect help intent in any language.

## Runtime Behavior Notes

### SOP Execution Flow
```python
user_request → SOP search (FAISS) → Pass SOP to decomposer → Execute workflow
```
- SOPs discovered through semantic similarity
- Full SOP content passed to task decomposer
- Mode-specific execution (template vs guide)

### Intent-Based Routing
```python
async def chat(self, message: str, user_id: str):
    # 1. Detect intent
    intent = await self.intent_detector.analyze(message)

    # 2. Find relevant SOPs
    sops = await self.sop_coordinator.search(message)

    # 3. Select agent(s) based on SOPs or intent
    if sops:
        agents = self.select_agents_for_sop(sops[0])
    else:
        agent = self.select_agent(intent)

    # 4. Execute with memory context
    context = await self.memory.get_context(user_id)
    response = await agent.process(message, context)
```

### Memory Architecture

- **Working Memory**: Always enabled, configurable size
- **Buffer Memory**: FIFO with vector search for recent context
- **Persistent Memory**: PostgreSQL/SQLite for long-term storage
- **Vector Memory**: FAISSx integration for semantic search
- **Multi-user**: Isolated contexts via Memobase partitioning

### ID Hierarchy and Roles

The system uses a three-level ID hierarchy for request tracking and user isolation:

```
user_id (user isolation)
  └── session_id (chat grouping)
      └── request_id (single interaction with all clarifications)
```

**request_id**:
- Tracks ONE complete interaction from initial request to final response
- Includes all clarification turns within that interaction
- Used as key for UnifiedClarificationSystem state: `clarification:{request_id}`
- Must remain constant throughout entire clarification flow
- Example: "Build it" → clarify → "a website" → clarify → "with React" = ONE request_id

**session_id**:
- Groups multiple requests into a chat conversation
- Used for buffer memory filtering: `{"user_id": user_id, "session_id": session_id}`
- Provides conversation context across multiple requests
- Developer-supplied identifier for chat continuity
- Enables request_id reuse for multi-turn clarification

**user_id**:
- Provides user isolation in multi-user mode
- Top-level filter for all memory operations
- Normalized to lowercase, "0" for single-user mode
- Ensures users only see their own data

This hierarchy ensures proper isolation, context preservation, and multi-turn clarification support.

## Testing Philosophy

**No mocks allowed** - Test against real services only:
- Actual LLM providers (OpenAI, Anthropic)
- Real database instances
- Live MCP servers
- Actual embeddings for vector search

Test organization by feature day:
- Day 1-3: Foundation, Memory, Multimodal
- Day 4-6: MCP, File Generation, Knowledge
- Day 7-12: Advanced features (workflow, resilience, etc.)


## Common Issues

### "Missing required LLM capability 'text'"
Formation must include:
```yaml
llm:
  models:
    - text: "provider/model-name"
```

### Intent detection failing
- Check formation has valid text model
- Verify API keys are configured
- Ensure model has sufficient capabilities

### Workflow not triggering
- Verify `auto_decomposition: true`
- Check complexity threshold (default: 7.0)
- Ensure no specific agent is requested

## Development Patterns

### Adding New Services
1. Create in `src/muxi/services/`
2. Initialize in formation loading
3. Add to overlord's service registry
4. Update formation schema if configurable

### Modifying Orchestration
1. Changes go in overlord.py
2. Update workflow integration if needed
3. Ensure SOP compatibility
4. Test with real formations

### Memory System Changes
1. Update appropriate tier (buffer/persistent/vector)
2. Maintain multi-user isolation
3. Test with Memobase partitioning
4. Verify extraction still works

## Critical Files

- `src/muxi/formation/formation.py` - Formation loading and lifecycle
- `src/muxi/formation/overlord/overlord.py` - Central orchestration
- `src/muxi/formation/workflow/` - Workflow execution and SOPs
- `src/muxi/formation/resilience/` - Error recovery layer
- `src/muxi/services/` - All runtime services
- `schemas/formation/formation.yaml` - Configuration schema

## Future Considerations

1. **Model capabilities validation** - Verify models support assigned capabilities
2. **Performance optimization** - Cache model instances
3. **Enhanced fallback strategies** - Sophisticated chains for capabilities
4. **Configuration migration** - Tools for format upgrades
