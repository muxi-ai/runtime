# Smart Clarification v2 - Educated Guess with Soft Clarification

**Status:** Planned
**Created:** 2024-12-23

## Problem

When context inference isn't 100% certain, the system should make an educated guess and answer while offering a soft clarification, rather than blocking with a clarification question.

## Current Behavior (v1 - Implemented)

Context inference either:
- Succeeds (high confidence) → Answer directly
- Fails (low confidence) → Ask for clarification

```
User: what's the capital of france?
System: Paris.

User: what about israel?
System: [If confident] The capital of Israel is Jerusalem.
System: [If not confident] Could you clarify what you'd like to know about Israel?
```

## Desired Behavior (v2 - Planned)

Make an educated guess AND provide soft clarification suffix:

```
User: what's the capital of france?
System: Paris.

User: what about israel?
System: The capital of Israel is Jerusalem. Let me know if you meant something else!
```

## Implementation Approach

### 1. Enhanced Clarification Analyzer Response

```python
{
    "needs_clarification": True,
    "likely_intent": "asking about capital of Israel",
    "likely_answer": "Jerusalem",
    "confidence": 0.85,
    "clarification_question": "Were you asking about the capital?"
}
```

### 2. Confidence-Based Response Strategy

| Confidence | Action |
|------------|--------|
| `> 0.7` | Answer with likely intent + soft clarification suffix |
| `0.4 - 0.7` | Answer with likely intent + explicit clarification question |
| `< 0.4` | Ask for clarification first (current behavior) |

### 3. Soft Clarification Suffixes

Randomly selected for variety:
- "Let me know if you meant something else!"
- "Is this what you were looking for?"
- "Feel free to clarify if I misunderstood."
- "Was this what you had in mind?"

### 4. Implementation Location

Modify `UnifiedClarificationSystem.needs_clarification()` to:

```python
async def needs_clarification(self, message, request_id, session_id, context):
    analysis = await self._analyze_request_with_guess(message, context)
    
    if not analysis["needs_clarification"]:
        return ClarificationResult(action="execute", request=message)
    
    confidence = analysis.get("confidence", 0.0)
    likely_answer = analysis.get("likely_answer")
    
    if confidence > 0.7 and likely_answer:
        # High confidence: answer with soft suffix
        suffix = random.choice(SOFT_CLARIFICATION_SUFFIXES)
        return ClarificationResult(
            action="execute_with_soft_clarification",
            request=message,
            likely_answer=likely_answer,
            soft_suffix=suffix
        )
    elif confidence > 0.4 and likely_answer:
        # Medium confidence: answer with explicit question
        return ClarificationResult(
            action="execute_with_clarification",
            request=message,
            likely_answer=likely_answer,
            follow_up_question=analysis["clarification_question"]
        )
    else:
        # Low confidence: ask for clarification first
        return ClarificationResult(
            action="clarify",
            question=analysis["clarification_question"]
        )
```

### 5. Prompt Changes

Update `clarification_analysis.md` to request:
- `likely_intent`: What the user probably means
- `likely_answer`: Best guess answer if intent is clear enough
- `confidence`: 0.0-1.0 score for the guess
- `clarification_question`: Fallback question if needed

## Benefits

- More natural conversation flow
- Fewer round-trips for common follow-up patterns
- Better user experience (matches ChatGPT behavior)
- Still handles truly ambiguous cases
- User can correct if guess was wrong

## Examples

### High Confidence (> 0.7)
```
User: what's the capital of france?
System: The capital of France is Paris.

User: and germany?
System: The capital of Germany is Berlin. Let me know if you meant something else!
```

### Medium Confidence (0.4-0.7)
```
User: tell me about python
System: I can help with Python programming or the snake species.

User: the snake
System: Python snakes are non-venomous constrictors found in Africa, Asia, and Australia. Were you looking for specific information about their habitat, diet, or behavior?
```

### Low Confidence (< 0.4)
```
User: help me with the thing
System: I'd be happy to help! Could you tell me more about what you're working on?
```

## Related Files

- `src/muxi/formation/overlord/clarification.py` - Main implementation
- `src/muxi/formation/prompts/clarification_analysis.md` - Prompt template
- `docs/features/smart-clarification.md` - v1 implementation docs

## Migration Path

1. Update clarification prompt to return confidence and likely_answer
2. Add new ClarificationResult action types
3. Handle new actions in overlord
4. Add soft suffix to persona stage
5. Test with various confidence levels
