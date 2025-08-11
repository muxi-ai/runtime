# Area 8: Intelligent Clarification Tests

This directory contains tests for Area 8 of the MUXI Runtime Comprehensive Test Plan, focusing on intelligent clarification capabilities.

## Overview

Area 8 tests validate the system's ability to:
1. Detect ambiguous requests and ask for clarification
2. Use clarification for multi-agent routing decisions
3. Handle credential selection when multiple options exist
4. Maintain context through clarification flows

## Test Structure

### Part 1: Base Clarification (8A) - Current Capabilities

#### Test 8A1: Ambiguous Request Clarification
- **File**: `test_8a1_ambiguous_request.py`
- **Purpose**: Tests detection of unclear requests
- **Scenarios**:
  - Ambiguous general request ("I need help with a scraper")
  - Ambiguous technical request ("Fix the bug")
  - Clear requests that don't need clarification

#### Test 8A2: Multi-Agent Clarification
- **File**: `test_8a2_multi_agent_clarification.py`
- **Purpose**: Tests clarification for agent routing
- **Scenarios**:
  - Ambiguous project help request
  - Agent specialty clarification
  - Direct agent requests (no clarification needed)

#### Test 8A3: Credential Clarification
- **Status**: Removed - Already tested in Area 4
- **Reason**: Credential clarification is comprehensively covered in Area 4 tests

### Part 2: Information Flow (8B) - ✅ IMPLEMENTED

#### Test 8B1: Context Propagation
- **File**: `test_8b1_context_propagation.py`
- **Purpose**: Tests context preservation across conversation turns
- **Scenarios**:
  - Context carries across multiple messages
  - User isolation (separate contexts per user)
  - Topic continuity in conversations

#### Test 8B2: Information Extraction
- **File**: `test_8b2_information_extraction.py`
- **Purpose**: Tests extraction of key information from messages
- **Scenarios**:
  - Budget and timeline extraction
  - Requirements gathering
  - Constraint tracking across conversation

#### Test 8B3: Multi-turn Context Management
- **File**: `test_8b3_multi_turn_context.py`
- **Purpose**: Tests handling of multi-turn conversations
- **Scenarios**:
  - Topic switching with context retention
  - Long conversation management
  - Context relevance over multiple turns

### Part 3: Multiple Clarification Sequences (8C) - ✅ IMPLEMENTED

#### Test 8C1: Credential Rejection Flow
- **File**: `test_8c1_credential_rejection_flow.py`
- **Purpose**: Tests credential rejection and re-selection
- **Scenarios**:
  - Account rejection and re-selection
  - Multiple credential management
  - State preservation during rejection

#### Test 8C2: Multi-step Clarification
- **File**: `test_8c2_multi_step_clarification.py`
- **Purpose**: Tests nested and branching clarifications
- **Scenarios**:
  - Nested clarification sequences
  - Branching clarification paths
  - State management across clarifications

#### Test 8C3: Complex Parameter Collection
- **File**: `test_8c3_complex_parameter_collection.py`
- **Purpose**: Tests collection of multiple parameters
- **Scenarios**:
  - Multi-parameter collection workflows
  - Parameter validation and correction
  - Complex workflow clarification

### Part 4: Clarification Stack Management (8D) - 🔲 TODO

#### Test 8D1: Stack Depth Handling
- **File**: `test_8d1_stack_depth_handling.py`
- **Purpose**: Tests deep nested clarification stacks
- **Scenarios**:
  - 3-level deep clarification chains
  - Context preservation across stack levels
  - Stack unwinding and resolution

#### Test 8D2: Parallel Clarification Branches
- **File**: `test_8d2_parallel_clarification.py`
- **Purpose**: Tests handling multiple parallel clarifications
- **Scenarios**:
  - Clarifications for multiple data sources
  - Branch merging and context combination
  - Independent branch resolution

#### Test 8D3: Clarification Timeout
- **File**: `test_8d3_clarification_timeout.py`
- **Purpose**: Tests timeout and session management
- **Scenarios**:
  - Clarification timeout detection
  - Abandoned clarification cleanup
  - New conversation vs continuation detection

#### Implementation Details
The system now properly handles multiple clarification sequences through:
- `_handle_clarification_response` method in `overlord.py`
- State tracking via `clarification_context` field
- Context preservation throughout the clarification process
- Production-ready error handling and state management

## Running the Tests

### Run All Tests
```bash
python tests/e2e/8_clarification/run_area8_tests.py
```

### Run Individual Test Groups
```bash
# Test ambiguous requests
python tests/e2e/8_clarification/test_8a1_ambiguous_request.py

# Test multi-agent clarification
python tests/e2e/8_clarification/test_8a2_multi_agent_clarification.py

# Test context propagation
python tests/e2e/8_clarification/test_8b1_context_propagation.py

# Test information extraction
python tests/e2e/8_clarification/test_8b2_information_extraction.py

# Test multi-turn context
python tests/e2e/8_clarification/test_8b3_multi_turn_context.py

# Test credential rejection flow
python tests/e2e/8_clarification/test_8c1_credential_rejection_flow.py

# Test multi-step clarification
python tests/e2e/8_clarification/test_8c2_multi_step_clarification.py

# Test complex parameter collection
python tests/e2e/8_clarification/test_8c3_complex_parameter_collection.py
```

### Using pytest
```bash
# Run all Area 8 tests
pytest tests/e2e/8_clarification/ -v

# Run specific test file
pytest tests/e2e/8_clarification/test_8a1_ambiguous_request.py -v
```

## Formation Requirements

The tests use these formations:

1. **formation-clarification**: Single agent for basic clarification
2. **formation-multi-agent**: Multiple specialized agents for routing tests

## Expected Behavior

### Clarification Detection
The system should detect ambiguous requests based on:
- Lack of specific details
- Multiple possible interpretations
- Missing required information

### Clarification Questions
The system should ask natural, conversational questions:
- "What kind of help do you need?"
- "Which account would you like to use?"
- "Can you provide more details about...?"

### Context Retention
After clarification:
- Original intent is preserved
- Clarification response is used to enhance processing
- Appropriate agent/tool is selected

## Success Criteria

✅ **Part 1 (8A) Complete** when:
- Both test groups (8A1-8A2) pass
- Ambiguous requests trigger appropriate clarifications
- Context flows correctly through clarification
- Clear requests bypass clarification
- Note: Credential clarification (8A3) already validated in Area 4

✅ **Part 2 (8B) Complete** when:
- All three information flow tests pass (8B1-8B3)
- Context propagates across conversation turns
- Information is extracted and tracked correctly
- Multi-turn conversations maintain coherence

✅ **Part 3 (8C) Complete** when:
- All three sequence tests pass (8C1-8C3)
- Multiple clarification sequences work correctly
- Complex parameter collection functions properly
- State tracking across multiple clarification rounds

🔲 **Part 4 (8D) TODO** when:
- All three stack management tests pass (8D1-8D3)
- Deep clarification stacks (3+ levels) work correctly
- Parallel clarification branches handled properly
- Clarification timeouts managed appropriately
- Stack overflow protection in place

## Notes

- Tests use real LLM calls - no mocks
- Each test creates its own session for isolation
- Tests validate both positive (needs clarification) and negative (no clarification) cases
- Credential clarification testing moved to Area 4 to avoid duplication

## Related Documentation

- [Test Mapping](TEST_MAPPING.md) - Detailed test organization
- [Comprehensive Test Plan](../../MUXI_Runtime_Comprehensive_Test_Plan.md) - Overall testing strategy
- [Clarification System Docs](../../docs/clarification.md) - Technical documentation (if exists)
