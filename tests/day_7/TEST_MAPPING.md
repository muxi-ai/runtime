# Day 7B: A2A Communication Patterns - Test Mapping

## Overview
This document maps the test requirements from the comprehensive test plan to the actual test implementations for Day 7B: A2A (Agent-to-Agent) Communication Patterns.

## Test Coverage

### Test 7B1: Internal A2A Communication (within formation)
**Requirement**: Test agents communicating within the same formation to collaborate on multi-specialty tasks.

**Implementation File**: `test_internal_a2a_communication.py` (formerly test_a2a_overlord_chat.py)

**Test Scenarios**:
1. **Multi-Specialty Request**: User asks for help with both Python programming and database design
   - Expected: Agents recognize they need each other's expertise and communicate internally
   - Validation: Response includes contributions from both specialists

2. **Tool Sharing**: Agent needs a tool that only another agent has access to
   - Expected: Agent requests help from colleague with required tool access
   - Validation: Tool execution happens through A2A communication

3. **Knowledge Consultation**: Agent consults another for domain expertise
   - Expected: Agents share knowledge through consultation messages
   - Validation: Response quality improves with consultation

**Key Methods Tested**:
- `agent.send_a2a_message()`
- `agent.request_consultation()`
- `agent.share_information()`
- `a2a_coordinator.get_available_agents_for_a2a()`

### Test 7B2: External A2A Communication (cross-formation)
**Requirement**: Test agents communicating across different formations for specialized expertise.

**Implementation File**: `test_external_a2a_communication.py`

**Test Scenarios**:
1. **External Specialist Request**: Main formation needs legal expertise from external formation
   - Expected: Formation discovers and communicates with external legal specialist
   - Validation: Response includes input from external formation

2. **Multi-Formation Collaboration**: Complex task requiring agents from multiple formations
   - Expected: Formations coordinate through A2A server endpoints
   - Validation: All formations contribute to final response

3. **Service Discovery**: Agent discovers available external formations
   - Expected: External registry provides formation discovery
   - Validation: Correct formations are discovered based on capability

**Key Components Tested**:
- A2A server initialization and endpoints
- External registry registration/discovery
- Cross-formation message routing
- Authentication and security

## Configuration Requirements

### Formation Configuration
```yaml
# Disable or set high threshold for workflow orchestration
overlord:
  config:
    auto_decomposition: false  # Or use high complexity_threshold
    
# Enable A2A settings
a2a:
  internal:
    enabled: true
  server:
    enabled: true
    host: "0.0.0.0"
    port: 8100
  external_registry:
    enabled: true
    url: "http://localhost:8000/registry"
```

### Agent Configuration
```yaml
agents:
  - id: "python-expert"
    a2a_internal: true  # Participates in internal A2A
    # Exclusive MCP access to force collaboration
    mcp:
      servers:
        - github  # Only this agent has GitHub access
        
  - id: "database-expert"
    a2a_internal: true
    mcp:
      servers:
        - postgres  # Only this agent has database access
```

## Test Environment Setup

1. **Single Formation Tests (7B1)**:
   - Load formation with multiple agents having distributed capabilities
   - Ensure workflow orchestration is disabled/limited
   - Verify agents have complementary, not overlapping, tool access

2. **Multi-Formation Tests (7B2)**:
   - Start multiple formations on different ports
   - Initialize external registry service
   - Ensure formations can discover each other
   - Test with both local and remote formations

## Success Criteria

### For Test 7B1 (Internal A2A):
- [ ] Agents successfully discover each other's capabilities
- [ ] A2A messages are sent and received within formation
- [ ] Consultations result in improved task completion
- [ ] Tool sharing works through A2A communication
- [ ] No workflow orchestration interference

### For Test 7B2 (External A2A):
- [ ] Formations register with external registry
- [ ] Cross-formation discovery works correctly
- [ ] Messages route between formations successfully
- [ ] Security and authentication function properly
- [ ] External consultations improve response quality

## Testing Approach

1. **No Mocks**: Use real services and actual A2A communication
2. **Workflow Control**: Test with workflow both enabled and disabled to ensure A2A works in both modes
3. **Prompt Design**: Use prompts that naturally require multi-agent collaboration
4. **Distributed Capabilities**: Ensure agents genuinely need each other's tools/expertise

## Related Documentation
- [A2A Coordinator Implementation](../../src/muxi/formation/overlord/a2a_coordinator.py)
- [Agent A2A Methods](../../src/muxi/formation/agents/agent.py)
- [A2A Server Implementation](../../src/muxi/formation/a2a/)
- [Formation Schema](../../schemas/formation/README.md)