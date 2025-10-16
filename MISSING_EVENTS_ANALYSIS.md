# Analysis of 54 Missing Events

## Issue #1: Enum Category Mismatches (NOT actually missing!)

These events **exist in the enum** but code is using the **wrong enum category**:

### WORKFLOW Events
- `WORKFLOW_ANALYSIS_FAILED` - Exists in **ConversationEvents**, code uses **SystemEvents** ❌
  - Location: `src/muxi/formation/workflow/analyzer.py:324`
  - Fix: Change `SystemEvents.WORKFLOW_ANALYSIS_FAILED` → `ConversationEvents.WORKFLOW_ANALYSIS_FAILED`

- `WORKFLOW_DECOMPOSITION_FAILED` - Exists in **ConversationEvents**, code uses **SystemEvents** ❌
  - Location: `src/muxi/formation/workflow/decomposer.py:298`
  - Fix: Change `SystemEvents.WORKFLOW_DECOMPOSITION_FAILED` → `ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED`

## Issue #2: Init vs Runtime Events

### INIT Events (Non-Fatal)
These happen during initialization but are **non-fatal** (log warning and continue):

- `AGENT_INITIALIZATION_ERROR` - Agent knowledge init fails, agent continues without knowledge
  - Location: `src/muxi/formation/agents/agent.py:300`
  - **Not fail-fast**: Agent loads successfully, just without knowledge handler
  - **Recommendation**: Add to ErrorEvents (it's a recoverable error)

- `AGENT_FAILED` - MUXI default agent file load fails
  - Location: `src/muxi/formation/overlord/overlord.py:1561`
  - **Not fail-fast**: Skips the broken default agent, continues with others
  - **Recommendation**: Add to ErrorEvents

- `BUILTIN_MCP_INITIALIZATION_FAILED` - Built-in MCP init fails
  - Location: `src/muxi/formation/overlord/overlord.py:9650`
  - **Not fail-fast**: Skips broken MCP, continues with others
  - **Recommendation**: Add to ErrorEvents

- `BUILTIN_MCP_PROMPT_LOAD_FAILED` - MCP prompt file load fails
  - Location: `src/muxi/formation/overlord/overlord.py:9634`
  - **Not fail-fast**: Uses default prompts instead
  - **Recommendation**: Add to ErrorEvents

- `COMPONENT_INITIALIZATION_FAILED` - A2A filtering init fails due to missing deps
  - Location: `src/muxi/formation/overlord/a2a_coordinator.py:77`
  - **Not fail-fast**: Disables filtering, continues without it
  - **Recommendation**: Add to ErrorEvents

### RUNTIME Events (API/Operations)
These happen **after formation loads**, during normal operations:

- `AGENT_CREATION_FAILED` - Dynamic agent creation via API fails
  - Location: `src/muxi/formation/overlord/overlord.py:3128`
  - **Context**: Called from `POST /api/admin/agents` endpoint
  - **Recommendation**: Add to ErrorEvents

- `AGENT_REGISTRATION_FAILED` - Agent expertise registration fails
  - Location: `src/muxi/formation/agents/agent.py:4125`
  - **Context**: Runtime capability registration
  - **Recommendation**: Add to ErrorEvents

- `AGENT_DEREGISTRATION_COMPLETED` - Agent removed from overlord
  - Location: `src/muxi/formation/overlord/overlord.py:3296`
  - **Context**: Agent deletion via API
  - **Recommendation**: Add to SystemEvents (lifecycle event)

### RUNTIME Events (External A2A Registry)
These happen during **async A2A operations** with external registries:

- `A2A_AGENT_REGISTRATION_FAILED` (2x) - External registry registration fails
  - Locations: `a2a_coordinator.py:374`, `a2a_coordinator.py:458`
  - **Context**: Async background task registering with external A2A registry
  - **Non-blocking**: Formation loads successfully, registration retries in background
  - **Recommendation**: Add to ErrorEvents

- `A2A_AGENT_REGISTRATIONS_COMPLETED` - Bulk registration completes
  - Location: `src/muxi/formation/overlord/a2a_coordinator.py:366`
  - **Context**: After all agents registered with external registry
  - **Recommendation**: Add to SystemEvents

- `A2A_REGISTRATION_COMPLETED` - Single agent registration completes
  - Location: `src/muxi/services/a2a/discovery.py:263`
  - **Context**: Individual agent registration success
  - **Recommendation**: Add to SystemEvents

- `A2A_DEREGISTRATION_STARTED` - Agent deregistration begins
  - Location: `src/muxi/services/a2a/discovery.py:292`
  - **Context**: Cleanup when agent removed
  - **Recommendation**: Add to SystemEvents

- `A2A_CREDENTIAL_REMOVED` - Credentials removed for agent
  - Location: `src/muxi/services/a2a/auth/outbound.py:774`
  - **Context**: Credential cleanup
  - **Recommendation**: Add to SystemEvents

- `A2A_MESSAGE_PARSING` - Message format fallback
  - Location: `src/muxi/services/a2a/server.py:239`
  - **Context**: Legacy message format handling
  - **Recommendation**: Add to SystemEvents (operational detail)

## Issue #3: Error Events Using Wrong Names

These are using non-existent error event names instead of standard ones:

- `GENERIC_ERROR`, `PROCESSING_ERROR`, `OVERLORD_PROCESSING_ERROR`, `SERVICE_ERROR`, `RESOURCE_ERROR`
  - **Should use**: `ErrorEvents.INTERNAL_ERROR`
  
- `FILE_OPERATION_FAILED`, `MEMORY_BUFFER_UPDATE_FAILED`
  - **Should use**: `ErrorEvents.INTERNAL_ERROR` or add specific events

## Issue #4: Operational Events (Low Priority)

These are internal operational details, mostly debug/info logging:

### MCP Operations
- `MCP_REQUEST_CANCELLED`, `MCP_MESSAGE_CANCELLED`, `MCP_ALL_REQUESTS_CANCELLED`, etc.
  - **Recommendation**: Map to `SystemEvents.OPERATION_COMPLETED` with appropriate level

### Scheduler Operations
- `SCHEDULER_CACHE_CLEANUP`, `SCHEDULER_CIRCUIT_BREAKER_ACTIVATED`, etc.
  - **Recommendation**: Map to `SystemEvents.SERVICE_STARTED` (generic operational event)

### Clarification
- `CLARIFICATION_REQUEST_GENERATED`, `CLARIFICATION_SKIPPED`
  - **Recommendation**: Add to ConversationEvents (user-facing flow)

### Other
- `CREDENTIAL_CONFIGURED`, `CREDENTIAL_UPDATE`, `CRON_EXPRESSION_FIXED`, etc.
  - **Recommendation**: Map to existing events or add if important

## Recommended Fixes

### Priority 1: Fix Enum Mismatches (2 events)
```bash
# Quick sed replacement
sed -i '' 's/SystemEvents\.WORKFLOW_ANALYSIS_FAILED/ConversationEvents.WORKFLOW_ANALYSIS_FAILED/g' src/muxi/formation/workflow/analyzer.py
sed -i '' 's/SystemEvents\.WORKFLOW_DECOMPOSITION_FAILED/ConversationEvents.WORKFLOW_DECOMPOSITION_FAILED/g' src/muxi/formation/workflow/decomposer.py
```

### Priority 2: Add Important Runtime Events (15 events)

**Add to ErrorEvents:**
- `AGENT_INITIALIZATION_ERROR`
- `AGENT_CREATION_FAILED`
- `AGENT_REGISTRATION_FAILED`
- `AGENT_FAILED`
- `A2A_AGENT_REGISTRATION_FAILED`
- `BUILTIN_MCP_INITIALIZATION_FAILED`
- `BUILTIN_MCP_PROMPT_LOAD_FAILED`
- `COMPONENT_INITIALIZATION_FAILED`

**Add to SystemEvents:**
- `A2A_AGENT_REGISTRATIONS_COMPLETED`
- `A2A_REGISTRATION_COMPLETED`
- `A2A_DEREGISTRATION_STARTED`
- `A2A_CREDENTIAL_REMOVED`
- `A2A_MESSAGE_PARSING`
- `AGENT_DEREGISTRATION_COMPLETED`

**Add to ConversationEvents:**
- `CLARIFICATION_REQUEST_GENERATED`
- `CLARIFICATION_SKIPPED`

### Priority 3: Map Low-Priority Events (37 events)

Most of these can be mapped to existing events like:
- Error events → `ErrorEvents.INTERNAL_ERROR`
- Operational events → `SystemEvents.SERVICE_STARTED` or `OPERATION_COMPLETED`
- Cancel events → `SystemEvents.OPERATION_COMPLETED` with appropriate level

## Summary

- **2 events**: Simple enum category fix
- **17 events**: Should be added to enum (important for debugging/operations)
- **35 events**: Can be mapped to existing events
- **Total**: 54 → 2 fixed + 17 added + 35 mapped = **100% validation**
