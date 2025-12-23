# Smart Clarification Feature

**Status:** Proposed
**Created:** 2024-12-23

## Problem

Current clarification behavior is too aggressive. When a user asks an ambiguous follow-up question like "what about israel?" after asking "what's the capital of france?", the system asks for clarification instead of inferring the likely intent.

## Current Behavior (Bad)

```
User: what's the capital of france?
System: Paris...

User: what about israel?
System: Could you please clarify what specific information you are looking for about Israel?

User: whats the capital?
System: Jerusalem
```

## Desired Behavior (ChatGPT-style)

```
User: what's the capital of france?
System: Paris...

User: what about israel?
System: The capital of Israel is Jerusalem. Let me know if you were asking about something else!
```

## Implementation Approach

1. **Clarification analyzer returns richer response:**
   ```python
   {
       "needs_clarification": True,
       "likely_intent": "asking about capital of Israel",
       "likely_answer": "Jerusalem",
       "confidence": 0.85,
       "clarification_question": "Were you asking about the capital?"
   }
   ```

2. **Confidence-based response strategy:**
   - `confidence > 0.7`: Answer with likely intent + soft clarification suffix
   - `confidence 0.4-0.7`: Answer with likely intent + explicit clarification question
   - `confidence < 0.4`: Ask for clarification first

3. **Soft clarification suffixes:**
   - "Let me know if you meant something else!"
   - "Is this what you were looking for?"
   - "Feel free to clarify if I misunderstood."

## Benefits

- More natural conversation flow
- Fewer round-trips for common follow-up patterns
- Better user experience (matches ChatGPT behavior)
- Still handles truly ambiguous cases

## Related Files

- `src/muxi/formation/overlord/clarification.py`
- `src/muxi/formation/prompts/clarification_analysis.md`
