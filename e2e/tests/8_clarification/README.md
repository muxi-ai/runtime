# Area 8: Clarification System Tests

## Overview

Area 8 tests the MUXI Unified Clarification System - an intelligent component that resolves ambiguous or incomplete user requests before processing. The system uses LLM-based analysis (no pattern matching) and supports five specialized clarification modes.

## Test Organization

### Area 8A: Core Clarification Behavior
Tests fundamental clarification detection and false positive prevention.

- **test_8a1_ambiguous_request.py** - Ambiguous requests trigger clarification
- **test_8a2_no_false_clarification.py** - Clear statements DON'T trigger clarification (critical!)

### Area 8B: Multi-Turn & Context Management
Tests clarification conversations and context handling.

- **test_8b1_multi_turn_clarification.py** - Multi-turn clarification flows
- **test_8b2_context_switch.py** - Context switch detection during clarification

### Area 8C: Clarification Modes
Tests the five specialized clarification modes.

- **test_8c1_clarification_modes.py** - Direct, Brainstorm, Planning, Execution, Credential modes

### Area 8D: Safety & Critical Scenarios
Tests safety-critical behavior and edge cases.

- **test_8d1_safety_critical.py** - Safety-critical questions (allergies, health) get immediate responses

## Key Concepts

### The Five Clarification Modes

1. **Direct Mode** (max_depth: 3)
   - Quick disambiguation of simple ambiguities
   - Example: "List files" → "Which directory?"

2. **Brainstorm Mode** (max_depth: 10)
   - Creative exploration and idea development
   - Example: "Help me design an app" → Open-ended discussion

3. **Planning Mode** (max_depth: 7)
   - Structured requirements gathering
   - Example: "Build an e-commerce system" → Product, payment, auth questions

4. **Execution Mode** (max_depth: 3)
   - Parameter clarification for well-defined tasks
   - Example: "Generate a report" → Format? Time range?

5. **Credential Mode** (max_depth: 2)
   - Credential selection when multiple accounts available
   - Triggered by `AmbiguousCredentialError`

### ID Hierarchy

```
user_id (user isolation)
  └── session_id (chat grouping)
      └── request_id (single interaction with all clarifications)
```

- **request_id**: Tracks ONE complete interaction including all clarification turns
- **session_id**: Groups multiple requests into a conversation
- **user_id**: User isolation in multi-user mode

### Request Flow

```
Incoming Request
    ↓
Is session_id in pending clarifications?
    ├─ Yes → Process clarification response (reuse request_id)
    └─ No → Check if clarification needed
         ↓
    Skip clarification? (workflow tasks only)
         ├─ Yes → Continue to processing
         └─ No → Call UnifiedClarificationSystem.needs_clarification()
                 ├─ Need clarification? → Store pending → Return question
                 └─ No → Continue to processing
```

## Critical Requirements

### ❌ False Positive Prevention (Test 8A2)

The clarification system MUST NOT trigger on:

- **Declarative statements**: "I am a PostgreSQL user"
- **Preference statements**: "I prefer dark mode"
- **Clear recall questions**: "What is my favorite database?"
- **Critical health info**: "I'm allergic to peanuts"
- **Factual statements**: "I have a sister in Boston"

### ✅ Should Trigger On

- **Ambiguous requests**: "Build it", "Fix the issue"
- **Underspecified technical requests**: "Install the library"
- **Pronouns without referents**: "How does it work?"

### 🚨 Safety-Critical Behavior (Test 8D1)

Health/safety questions MUST:
- Retrieve stored information immediately
- Provide direct, clear warnings
- NEVER ask for clarification when answer is known

Example:
```
User: "I'm allergic to peanuts"  → Store immediately
User: "Can I eat this peanut butter sandwich?"  → "NO! You're allergic!"
```

## Running Tests

### Individual Tests
```bash
# Run specific test
python e2e/tests/8_clarification/test_8a1_ambiguous_request.py

# Using test runner
bash .claude/scripts/test-and-log.sh e2e/tests/8_clarification/test_8a1_ambiguous_request.py
```

### All Area 8 Tests
```bash
# Run all clarification tests
pytest e2e/tests/8_clarification/ -v

# Run with coverage
pytest e2e/tests/8_clarification/ -v --cov=muxi.formation.clarification
```

## Test Patterns

### Standard Test Structure

```python
async def test_something():
    """Test description."""
    print("\n" + "=" * 80)
    print("Test 8X: Test Name")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        # 1. Load formation
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        # 2. Run test scenarios
        response = await overlord.chat(...)
        
        # 3. Validate responses
        if validation_passes:
            checks_passed.append("Description of what passed")
        else:
            all_passed = False
        
        # 4. Cleanup
        await formation.stop_overlord()
        formation.stop()

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        all_passed = False

    # Print results
    print("\n" + "=" * 80)
    print(f"Test Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    print("=" * 80)

    return 0 if all_passed else 1
```

## Formation Configuration

Tests use the shared formation at `formations/formation-clarification/`:

```yaml
overlord:
  clarification:
    style: conversational          # Question style
    persist_learned_info: false    # Privacy control
    timeout_seconds: 300           # 5 minutes
    max_rounds:
      direct: 3
      brainstorm: 10
      planning: 7
      execution: 3
      credential: 2

  response:
    format: "markdown"
    streaming: false
```

## Common Issues

### Issue: False Positives (Test Failures in 8A2)

**Symptom**: Clear statements trigger clarification
**Cause**: Clarification system too aggressive
**Fix**: Check LLM prompts in `UnifiedClarificationSystem._analyze_request()`

### Issue: Context Not Preserved (Test Failures in 8B1)

**Symptom**: Multi-turn clarification loses information
**Cause**: Buffer memory not persisting state correctly
**Fix**: Verify `request_id` consistency across turns

### Issue: Safety Questions Delayed (Test Failures in 8D1)

**Symptom**: System asks for clarification on safety questions
**Cause**: Not checking memory before clarification
**Fix**: Add memory check in `needs_clarification()` for critical keywords

## Related Documentation

- **`docs/clarification-system.md`** - Comprehensive system documentation
- **`IMPORTANT_PROMPTS_TO_TEST.md`** - Critical test cases and requirements
- **`src/muxi/formation/clarification/unified.py`** - Implementation

## Test Status

| Test | Status | Description |
|------|--------|-------------|
| 8A1 | ✅ Ready | Ambiguous request detection |
| 8A2 | 🔴 Critical | False positive prevention |
| 8B1 | ✅ Ready | Multi-turn clarification |
| 8B2 | ✅ Ready | Context switch detection |
| 8C1 | ✅ Ready | Clarification modes |
| 8D1 | 🔴 Critical | Safety-critical responses |

**Legend**:
- ✅ Ready - Test implemented and should pass
- 🔴 Critical - Test addresses critical system requirement
- ⚠️ Known Issues - Test may expose known problems

## Success Criteria

Area 8 tests pass when:

1. ✅ Ambiguous requests trigger clarification (8A1)
2. ✅ Clear statements do NOT trigger clarification (8A2)
3. ✅ Multi-turn clarification preserves context (8B1)
4. ✅ Context switches are handled (8B2)
5. ✅ Different modes work appropriately (8C1)
6. ✅ Safety-critical questions get immediate responses (8D1)

## Notes

- **LLM-Based**: All clarification decisions made by LLM (no pattern matching)
- **Buffer Memory**: State stored in buffer memory with `request_id` as key
- **Auto-Cleanup**: States cleaned up on completion, timeout, or circuit breaker
- **Multi-Language**: LLM approach works across languages automatically

## Priority Testing

**High Priority** (Run First):
1. test_8a2_no_false_clarification.py (addresses production bug)
2. test_8d1_safety_critical.py (safety requirement)
3. test_8a1_ambiguous_request.py (core functionality)

**Medium Priority**:
4. test_8b1_multi_turn_clarification.py (common use case)
5. test_8b2_context_switch.py (edge case handling)
6. test_8c1_clarification_modes.py (feature validation)

---

**Last Updated**: October 2025
**Area Owner**: Clarification System Team
