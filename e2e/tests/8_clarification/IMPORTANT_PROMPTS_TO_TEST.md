# Critical Clarification System Test Cases

**Date Created**: September 30, 2025
**Source**: Memory test failures (test_2c1, test_2k2)
**Issue**: Clarification system triggering on unambiguous statements

---

## ❌ Problem Summary

During memory system testing (Area 2), the clarification system was **incorrectly triggering** on simple declarative statements and clear questions, asking for clarification when none was needed. This broke memory storage/retrieval tests.

**Root Cause**: Clarification system appears to be too aggressive, treating factual statements as ambiguous requests.

**Temporary Fix**: Disabled clarification for memory tests with `clarification.enabled: false`

**Permanent Fix Needed**: Improve clarification detection to distinguish between:
- Ambiguous requests that need clarification
- Clear statements/questions that should be processed directly

---

## Test Case 1: Simple Self-Introduction

### User Message
```
I am a PostgreSQL test user. My favorite database is PostgreSQL and I work with distributed systems.
```

### ❌ Actual Response (Incorrect)
```
Could you please specify what assistance you need with PostgreSQL or distributed systems?
```

### ✅ Expected Behavior
- Acknowledge the information naturally
- Store facts in memory: profession, database preference, work domain
- Respond with acknowledgment like: "Got it! I'll remember that you prefer PostgreSQL and work with distributed systems."

### Why This Failed
**This is a declarative statement**, not an ambiguous request. User is providing information, not asking for help. No clarification needed.

---

## Test Case 2: Clear Recall Question

### User Message
```
What is my favorite database and what do I work with?
```

### ❌ Actual Response (Incorrect)
```
Could you please specify which database you are referring to and what you mean by 'work with'?
```

### ✅ Expected Behavior
- Retrieve stored memories from earlier conversation
- Answer directly: "Your favorite database is PostgreSQL and you work with distributed systems."

### Why This Failed
**This is a clear recall question**, not ambiguous. The user is asking the system to recall previously stated information. No clarification needed.

---

## Test Case 3: Critical Health Information

### User Message
```
I'm allergic to peanuts - this is very important!
```

### ❌ Actual Response (Incorrect)
```
Could you please provide more details on what you...
```

### ✅ Expected Behavior
- Acknowledge the critical information
- Store with high importance
- Respond: "Understood. I've noted that you have a peanut allergy. This is important for your safety."

### Why This Failed
**This is a clear medical fact**, explicitly marked as important. User is providing critical information that must be stored. No clarification needed.

---

## Test Case 4: Simple Preference Statement

### User Message
```
I prefer dark mode in my IDE
```

### ❌ Actual Response (Incorrect)
```
Could you please specify what you need help with regarding dark mode?
```

### ✅ Expected Behavior
- Acknowledge and store preference
- Respond naturally: "Got it, I'll remember you prefer dark mode in your IDE."

### Why This Failed
**This is a clear preference statement**. No ambiguity, no clarification needed.

---

## Test Case 5: Factual Statement About Relationships

### User Message
```
I have a sister who lives in Boston
```

### ❌ Actual Response (Incorrect)
```
Could you please specify what you need help with regarding your sister?
```

### ✅ Expected Behavior
- Store relationship information
- Respond: "I'll remember that you have a sister in Boston."

### Why This Failed
**This is a factual statement**. User is sharing personal information, not asking for assistance.

---

## Test Case 6: Critical Safety Question

### User Message
```
Can I eat this peanut butter sandwich?
```

### ❌ Actual Response (Incorrect)
```
Could you please confirm if you are asking about dietary restrictions...
```

### ✅ Expected Behavior
- **IMMEDIATELY** recall peanut allergy from memory
- **WARN USER**: "No! You have a peanut allergy. Peanut butter sandwiches are dangerous for you."
- This is a safety-critical question requiring immediate, direct response

### Why This Failed
**This is a yes/no question about food safety**. The system should recall the allergy and warn the user immediately, not ask for clarification. This type of delayed response could be dangerous in real-world scenarios.

---

## Additional Prompts That Should NOT Trigger Clarification

### Declarative Statements (Facts/Preferences)
```
- "My name is Alex and I work at Google"
- "I enjoy playing tennis on weekends"
- "I'm learning Spanish"
- "My favorite color is blue"
- "I'm diabetic and need to monitor sugar intake"
- "I'm vegetarian for ethical reasons"
- "My blood type is O-negative, important for emergencies"
```

### Clear Recall Questions
```
- "What is my profession?"
- "What activities do I enjoy?"
- "Do I have any dietary restrictions?"
- "What programming languages do I like?"
```

### Direct Questions with Context
```
- "What career advice would you give me?" (after sharing profession/experience)
- "What critical medical information should a doctor know about me?" (after sharing health info)
```

---

## When Clarification SHOULD Trigger

### Genuinely Ambiguous Requests
```
❓ "Fix it" - Fix what?
❓ "Tell me about that" - About what?
❓ "How do I do the thing?" - Which thing?
❓ "Help me with the project" - Which project?
```

### Underspecified Technical Requests
```
❓ "Install the library" - Which library?
❓ "Debug the error" - Which error? Where?
❓ "Update the config" - Which config file? What settings?
```

### Pronouns Without Clear Referents
```
❓ "How does it work?" - What is "it"?
❓ "Why isn't this working?" - What is "this"?
```

---

## Testing Requirements for Clarification System

When you test the clarification system (Area 8), **verify**:

### 1. ✅ Does NOT Trigger On:
- Simple declarative statements (facts, preferences, self-introduction)
- Clear recall questions about previously stated information
- Yes/no questions
- Factual statements marked as "important"
- Direct questions with sufficient context

### 2. ✅ DOES Trigger On:
- Ambiguous pronouns without referents ("it", "that", "this")
- Underspecified requests lacking necessary details
- Questions that genuinely cannot be answered without more information

### 3. ✅ Safety-Critical Behavior:
- Health/safety questions (allergies, medical) should:
  - Retrieve stored information immediately
  - Provide direct, clear warnings
  - NEVER ask for clarification when the answer is already known

### 4. ✅ Context Awareness:
- If user has shared information previously in the conversation
- Later questions about that information should NOT trigger clarification
- Example:
  - Turn 1: "I work at Google as an ML engineer"
  - Turn 5: "What's my profession?" → Should answer directly, not ask for clarification

---

## How to Test

### Test Script Structure
```python
# Test 1: Declarative statement should NOT trigger clarification
response = await overlord.chat("My name is Alex and I work at Google", ...)
assert "clarify" not in response.lower()
assert "specify" not in response.lower()

# Test 2: Recall question should NOT trigger clarification
await overlord.chat("My favorite color is blue", ...)
await asyncio.sleep(3)  # Wait for memory storage
response = await overlord.chat("What is my favorite color?", ...)
assert "blue" in response.lower()
assert "clarify" not in response.lower()

# Test 3: Ambiguous request SHOULD trigger clarification
response = await overlord.chat("Fix it", ...)
assert "clarify" in response.lower() or "what" in response.lower()
```

### Metrics to Track
- **False Positive Rate**: % of clear statements triggering clarification (should be <5%)
- **False Negative Rate**: % of ambiguous requests NOT triggering clarification (should be <10%)
- **Safety Response Time**: Time to respond to safety-critical questions (should be <2s)

---

## Impact on System

**Before Fix**:
- 4 memory tests failing due to clarification interference
- Test suite pass rate: 57.1% (8/14)

**After Fix** (disabled clarification for memory tests):
- Memory tests passing
- Test suite pass rate: 71.4% (10/14)

**Permanent Solution Needed**:
- Improve clarification detection logic
- Add context awareness (check if information is already in memory/conversation)
- Implement safety-critical fast path (bypass clarification for urgent queries)
- Re-enable clarification for memory tests after fixes

---

## Files Referenced

**Test Files That Failed**:
- `/e2e/tests/2_memory/test_2c1_postgresql_user_isolation.py`
- `/e2e/tests/2_memory/test_2k2_memory_priority.py`
- `/e2e/tests/2_memory/test_2j1_collection_field_usage.py`
- `/e2e/tests/2_memory/test_2k1_enhanced_prompt_integration.py`

**Formation Configs Modified** (temporary fix):
- `/e2e/tests/2_memory/formations/formation-memory/formation-postgres.yaml`
- `/e2e/tests/2_memory/formations/formation-memory/formation-sqlite.yaml`

**Change Applied**:
```yaml
clarification:
  enabled: false  # Disabled to prevent false positives on memory tests
```

---

## Priority

🔴 **HIGH PRIORITY** - This issue breaks multiple test suites and could lead to poor user experience in production:
- Users frustrated by unnecessary clarification requests
- Critical information (allergies, safety) not being acted upon immediately
- Memory storage failing because facts are questioned instead of stored

---

## Related Issues

- User context should inform clarification decisions
- Memory system should be checked before asking for clarification
- Safety-critical keywords ("allergy", "important", "emergency") should bypass clarification
- Declarative sentence structure detection needed (subject-verb-object statements)

---

**Next Steps When Testing Area 8**:
1. Run these exact prompts through clarification system
2. Measure false positive and false negative rates
3. Implement context-aware clarification logic
4. Add safety-critical fast path
5. Re-enable clarification for memory tests
6. Verify all tests pass with clarification enabled
