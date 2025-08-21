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

**Important**: When using the test-runner agent, instruct it to use:
```bash
bash .claude/scripts/test-and-log.sh path/to/test.py
```
This ensures proper logging and test result capture.

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

**Clarification State Coordination**:
- Overlord tracks pending clarifications: `_pending_clarification[session_id]` → returns `request_id`
- UnifiedClarificationSystem stores state: `clarification:{request_id}` → clarification state
- This two-level lookup is intentional and correct - DO NOT attempt to "fix" this coordination

This hierarchy ensures proper isolation, context preservation, and multi-turn clarification support.

## Testing Philosophy

**No mocks allowed** - Test against real services only:
- Actual LLM providers (OpenAI, Anthropic)
- Real database instances
- Live MCP servers
- Actual embeddings for vector search

**Test Focus**: When testing specific features (e.g., clarification), focus on testing that feature, not unrelated capabilities:
- Clarification tests should validate clarification flow, not tool availability
- If a test fails due to missing tools but the tested feature works, update the test to handle this expected scenario
- Tests should pass when the feature being tested works correctly, regardless of other system limitations

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

## Tone and Behavior

- Criticism is welcome. Please tell me when I am wrong or mistaken, or even when you think I might be wrong or mistaken.
- Please tell me if there is a better approach than the one I am taking.
- Please tell me if there is a relevant standard or convention that I appear to be unaware of.
- Be skeptical.
- Be concise.
- Short summaries are OK, but don't give an extended breakdown unless we are working through the details of a plan.
- Do not flatter, and do not give compliments unless I am specifically asking for your judgement.
- Occasional pleasantries are fine.
- Feel free to ask many questions. If you are in doubt of my intent, don't guess. Ask.

## ABSOLUTE RULES:

- NO PARTIAL IMPLEMENTATION
- NO SIMPLIFICATION : no "//This is simplified shit for now, complete implementation would blablabla"
- NO CODE DUPLICATION : check existing codebase to reuse functions and constants Read files before writing new functions. Use common sense function name to find them easily.
- NO DEAD CODE : either use or delete from codebase completely
- IMPLEMENT TEST FOR EVERY FUNCTIONS
- NO CHEATER TESTS : test must be accurate, reflect real usage and be designed to reveal flaws. No useless tests! Design tests to be verbose so we can use them for debuging.
- NO INCONSISTENT NAMING - read existing codebase naming patterns.
- NO OVER-ENGINEERING - Don't add unnecessary abstractions, factory patterns, or middleware when simple functions would work. Don't think "enterprise" when you need "working"
- NO MIXED CONCERNS - Don't put validation logic inside API handlers, database queries inside UI components, etc. instead of proper separation
- NO RESOURCE LEAKS - Don't forget to close database connections, clear timeouts, remove event listeners, or clean up file handles
- READ THE DAMN CODEBASE FIRST - actually examine existing patterns, utilities, and architecture before writing new code

## Reflections for Self-Improvment

### Objective:
Offer opportunities to continuously improve CLAUDE.md based on user interactions and feedback.

### Trigger:
After any task that involved insightful user feedback, or involved multiple non-trivial steps (e.g., multiple file edits, complex logic generation).

### Process:

- Offer Reflection: Ask the user: "Would you like me to reflect on our interaction and suggest potential improvements to the active CLAUDE.md file?"
- Await User Confirmation: Proceed to attempt_completion immediately if the user declines or doesn't respond affirmatively.
- If User Confirms:
  - a. Review Interaction: Synthesize all feedback provided by the user throughout the entire conversation history for the task. Analyze how this feedback relates to the active CLAUDE.md and identify areas where modified instructions could have improved the outcome or better aligned with user preferences.
  - b. Identify Active Rules: List the specific global and workspace CLAUDE.md files active during the task.
  - c. Formulate & Propose Improvements: Generate specific, actionable suggestions for improving the content of the relevant active rule files. Prioritize suggestions directly addressing user feedback. Use replace_in_file diff blocks when practical, otherwise describe changes clearly.
  - d. Await User Action on Suggestions: Ask the user if they agree with the proposed improvements and if they'd like me to apply them now using the appropriate tool (replace_in_file or write_to_file). Apply changes if approved, then proceed to attempt_completion.

<example>
User: "I think you should use the file-analyzer sub-agent more often."
Claude: "Would you like me to reflect on our interaction and suggest potential improvements to the active CLAUDE.md file?"
User: "Yes"
Claude: "I will now review our interaction and suggest potential improvements to the active CLAUDE.md file."
</example>
