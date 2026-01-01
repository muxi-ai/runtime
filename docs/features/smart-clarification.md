# Smart Clarification Feature

**Status:** Implemented
**Created:** 2024-12-23
**Updated:** 2025-12-23

## Overview

Smart clarification provides intelligent context inference for follow-up questions, reducing unnecessary clarification requests while maintaining accuracy for truly ambiguous queries.

## Features

### 1. Context Inference for Follow-ups

When a user asks a follow-up question like "what about israel?" after "what's the capital of france?", the system infers the likely intent from conversation context instead of asking for clarification.

**Example:**
```
User: what's the capital of france?
System: The capital of France is Paris.

User: what about israel?
System: The capital of Israel is Jerusalem.
```

### 2. Repeated Question Acknowledgment

When users ask the same question multiple times, the system acknowledges it was already answered while providing varied phrasing:

**Example:**
```
User: what's the capital of france?
System: The capital of France is Paris.

User: what's the capital of france?
System: Just to confirm what I mentioned earlier, the capital of France is Paris.

User: what's the capital of france?
System: As I said before, the capital of France is indeed Paris. Such a beautiful city!
```

### 3. Concise Responses

Response length matches question complexity - simple questions get brief answers without unnecessary markdown headers or bullet points.

## Implementation Details

### Context Inference Rules
Added to `clarification_analysis.md`:
- Follow-up patterns ("what about X?", "and Y?", "how about Z?") infer topic from recent context
- Pronouns and references resolved against conversation history
- High-confidence inferences proceed without clarification

### Repeated Question Detection
Implemented in `overlord.py` `_apply_persona()`:
- Normalizes questions (lowercase, strip punctuation)
- Compares against conversation context
- Adds acknowledgment instruction to persona prompt
- Disables caching to ensure varied responses

### Cache Bypass for Variety
- Persona stage uses `caching=False` for user-facing responses
- Ensures repeated questions get naturally varied phrasing
- `caching` parameter passes through to OneLLM for per-call control

## Related Files

- `src/muxi/formation/overlord/overlord.py` - Persona application with repeated detection
- `src/muxi/formation/overlord/chat_orchestrator.py` - Context loading
- `src/muxi/formation/prompts/clarification_analysis.md` - Context inference rules
- `src/muxi/formation/prompts/conversation_awareness_protocol.md` - Repeated question handling
- `src/muxi/services/llm/llm.py` - Cache bypass support
