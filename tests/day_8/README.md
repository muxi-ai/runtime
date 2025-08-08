# Day 8: Intelligent Clarification Tests

This directory contains tests for Day 8 of the MUXI Runtime Comprehensive Test Plan, focusing on intelligent clarification capabilities.

## Overview

Day 8 tests validate the system's ability to:
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
- **Status**: Removed - Already tested in Day 4
- **Reason**: Credential clarification is comprehensively covered in Day 4 tests

### Part 2: Enhanced Clarification (8B-8D) - Future Implementation

Not yet implemented. Will require:
- Clarification stack architecture
- Multi-turn clarification support
- Intent preservation across sub-clarifications

## Running the Tests

### Run All Tests
```bash
python tests/day_8/run_tests.py
```

### Run Individual Test Groups
```bash
# Test ambiguous requests
python tests/day_8/test_8a1_ambiguous_request.py

# Test multi-agent clarification
python tests/day_8/test_8a2_multi_agent_clarification.py
```

### Using pytest
```bash
# Run all Day 8 tests
pytest tests/day_8/ -v

# Run specific test file
pytest tests/day_8/test_8a1_ambiguous_request.py -v
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

✅ **Part 1 Complete** when:
- Both test groups (8A1-8A2) pass
- Ambiguous requests trigger appropriate clarifications
- Context flows correctly through clarification
- Clear requests bypass clarification
- Note: Credential clarification (8A3) already validated in Day 4

⏳ **Part 2 Pending** implementation of:
- Multiple clarification sequences
- Clarification stack management
- Sub-clarification handling

## Notes

- Tests use real LLM calls - no mocks
- Each test creates its own session for isolation
- Tests validate both positive (needs clarification) and negative (no clarification) cases
- Credential clarification testing moved to Day 4 to avoid duplication

## Related Documentation

- [Test Mapping](TEST_MAPPING.md) - Detailed test organization
- [Comprehensive Test Plan](../../MUXI_Runtime_Comprehensive_Test_Plan.md) - Overall testing strategy
- [Clarification System Docs](../../docs/clarification.md) - Technical documentation (if exists)