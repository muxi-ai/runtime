# Area 7 Tests: Workflow Orchestration & A2A Communication

This directory contains tests for Area 7 - covering both 7A (Workflow Orchestration) and 7B (A2A Communication).

## Test Overview

**Status**: ✅ COMPLETED & PRODUCTION READY  
**Test Groups**: 
- **7A** - Workflow Orchestration & Task Decomposition
- **7B** - A2A (Agent-to-Agent) Communication
**Reports**: 
- `tests/reports/7a.md` - Workflow orchestration results
- `tests/reports/7b.md` - A2A communication results

## 7A Tests: Workflow Orchestration

### test_7a_task_decomposition.py
**Purpose**: Main workflow orchestration test
- Tests complexity analysis and task decomposition
- Validates multi-agent coordination
- Tests intelligent task routing based on capabilities

### test_7a1_workflow_with_approval.py  
**Purpose**: Workflow with user approval
- Tests workflows that require user confirmation
- Validates plan approval threshold functionality

### test_workflow_resilience_integration.py
**Purpose**: Resilient workflow execution
- Tests error handling and recovery
- Validates user-friendly error messages

## 7B Tests: A2A Communication

### Test 7B1: test_internal_a2a_communication.py
**Purpose**: Internal A2A communication (within same formation)
- Single file test
- Tests A2A messaging between agents in the same formation
- Validates workflow decomposition with A2A
- Verifies observability event tracking

### Test 7B2: External A2A Communication (Cross-Formation)
**Purpose**: External A2A communication between different formations
- **Two files that must be run together:**

1. **test_formation2_provider.py** (Run First)
   - Acts as the service provider formation
   - Provides IT Support and Project Manager agents
   - Listens on port 8181 for A2A requests
   - Keeps running to handle incoming requests

2. **test_formation1_requester.py** (Run Second)
   - Acts as the service requester formation
   - Sends: "Create a Linear issue with system information like CPU, memory, etc."
   - Tests cross-formation discovery and communication
   - Verifies the complete external A2A flow

## Running the Tests

### 7A Tests (Workflow)
```bash
# Run individually
python test_7a_task_decomposition.py
python test_7a1_workflow_with_approval.py
python test_workflow_resilience_integration.py
```

### 7B Tests (A2A)
```bash
# Test 7B1 - Internal A2A (single formation)
python test_internal_a2a_communication.py

# Test 7B2 - External A2A (requires two terminals)
# Terminal 1 - Start Formation 2 (Provider):
python test_formation2_provider.py

# Terminal 2 - Run Formation 1 (Requester):
python test_formation1_requester.py
```

## Key Features Validated

### Workflow Orchestration (7A)
✅ Intelligent request analysis with complexity scoring  
✅ Dynamic task decomposition into subtasks  
✅ Multi-agent coordination with capability-based routing  
✅ Resilient execution with error recovery  
✅ User approval flows for complex workflows  

### A2A Communication (7B)
✅ **Internal A2A** (7B1) - Direct agent messaging within formation  
✅ **External A2A** (7B2) - Cross-formation agent collaboration  
✅ Agent discovery through registries  
✅ Secure authentication for external communication  
✅ Complete observability and event tracking  

## Configuration

Tests use formations from `test-formations/` directory:

- **7A Tests**: Use `formation-multi-agent/` with workflow settings
- **7B1 Test**: Uses `formation-multi-agent-segregated/` with A2A enabled
- **7B2 Tests**: Use `formation-a2a/formation1/` and `formation-a2a/formation2/`

## Production Status

🚀 **All Area 7 features are PRODUCTION READY**

Both workflow orchestration and A2A communication have been thoroughly tested and validated for production use.