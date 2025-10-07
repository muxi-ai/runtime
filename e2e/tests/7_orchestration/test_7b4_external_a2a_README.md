# Test 7B4 & 7B5: External A2A Communication

## Overview

These tests validate cross-formation agent-to-agent (A2A) communication where agents from different formations communicate with each other.

## Test Components

### Test 7B4: Provider Formation (test_7b4_external_a2a_provider.py)
- Acts as the service provider
- Provides IT Support and Project Manager agents  
- Listens on port 8181 for A2A requests
- Must be started FIRST and kept running

### Test 7B5: Requester Formation (test_7b5_external_a2a_requester.py)
- Acts as the service requester
- Sends requests that require Formation 2's agents
- Tests cross-formation discovery and communication
- Must be started SECOND (after provider is running)

## Running the Tests

These tests require two terminal windows:

### Terminal 1 - Start Provider (Formation 2)
```bash
cd e2e/tests/7_orchestration
python test_7b4_external_a2a_provider.py
```

Wait for message: "✅ Formation 2 is running and listening for A2A requests..."

### Terminal 2 - Run Requester (Formation 1)
```bash
cd e2e/tests/7_orchestration
python test_7b5_external_a2a_requester.py
```

## What Gets Tested

1. **Agent Discovery**: Formation 1 discovers agents in Formation 2
2. **Cross-Formation Routing**: Requests routed to appropriate formation
3. **Service Invocation**: Formation 1 calls Formation 2's agents
4. **Response Handling**: Results flow back through A2A channels
5. **Authentication**: Secure communication between formations

## Expected Behavior

### Provider (Formation 2)
- Starts and registers agents with A2A registry
- Listens for incoming A2A requests
- Processes requests from Formation 1
- Returns results via A2A protocol

### Requester (Formation 1)
- Discovers Formation 2's agents
- Sends request: "Create a Linear issue with system information"
- Receives and displays the response
- Verifies Linear issue was created with system info

## Prerequisites

1. **A2A Registry**: May require external registry service
2. **Network Access**: Formations must be able to communicate on localhost:8181
3. **MCP Tools**: Linear and system info tools must be configured
4. **API Keys**: Linear API key in environment

## Configuration

### Formation 1 (Requester)
- Location: `formations/formation-a2a/formation1/`
- Agents: Researcher, Writer, IT Support
- A2A: Configured to discover external agents

### Formation 2 (Provider)
- Location: `formations/formation-a2a/formation2/`
- Agents: Researcher, Writer, Project Manager
- A2A: Listens on port 8181

## Troubleshooting

### "Registry requirements not met"
- Start the registry server or change `startup_policy` to 'lenient'
- Check A2A configuration in formation YAML files

### "Connection refused" errors
- Ensure Formation 2 is started before Formation 1
- Check that port 8181 is not blocked by firewall

### "Agent not found" errors
- Wait for Formation 2 to fully initialize before starting Formation 1
- Check agent registration in Formation 2 logs

## Success Criteria

- ✓ Formation 2 starts and registers agents
- ✓ Formation 1 discovers Formation 2's agents
- ✓ Request successfully routed across formations
- ✓ Linear issue created with system information
- ✓ Response contains Linear issue ID
- ✓ No authentication errors
- ✓ Clean shutdown of both formations

## Notes

- These tests may be marked as `@slow` or `@very_slow` due to setup time
- They may require `@serial` marker to avoid port conflicts
- They may be marked as `@requires_a2a` for conditional execution
- External registry dependency may make them fragile in CI/CD
