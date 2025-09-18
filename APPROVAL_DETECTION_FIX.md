# Fix Pattern Matching in Approval Detection

## Problem
The current `requires_user_approval()` method in `src/muxi/formation/workflow/analyzer.py` uses hardcoded English phrases for pattern matching, which violates our multilingual principle.

## Current Implementation (Line 139-180)
```python
async def requires_user_approval(self, user_message: str, analysis: Optional[RequestAnalysis] = None) -> bool:
    approval_phrases = [
        "let me know how you're going to",
        "show me your plan",
        # ... more English phrases
    ]
    message_lower = user_message.lower()
    return any(phrase in message_lower for phrase in approval_phrases)
```

## Proposed Solution

### Option 1: Move to LLM Analysis (Recommended)
Integrate approval detection into the existing LLM analysis prompt:

**In `_create_analysis_prompt()`:**
```python
return f"""
Analyze this user request to determine its complexity and requirements:

User Request: "{user_message}" {context_info}

Please provide analysis in JSON format:

{{
    "complexity_score": [1-10 scale],
    "requires_approval": [true if user wants to see/approve the plan before execution],
    "is_approval_request": [true if user is asking to see approach/plan/method],
    "implicit_subtasks": [...],
    "required_capabilities": [...],
    "acceptance_criteria": [...],
    "confidence_score": [0.0-1.0]
}}

For "requires_approval", return true if the user is asking:
- To see your plan or approach before you start
- How you would handle or solve something
- For you to explain your method or process
- To approve before execution
- To understand the steps you'll take

This should work in ANY language - detect the intent, not specific words.
"""
```

**In `_parse_llm_analysis()`:**
```python
return RequestAnalysis(
    complexity_score=float(data.get("complexity_score", 5.0)),
    requires_decomposition=False,  # Still set by should_decompose
    requires_approval=data.get("requires_approval", False),  # From LLM now
    # ... rest of fields
)
```

**In `analyze_request()`:**
```python
# Remove this line since LLM now handles it:
# requires_approval = await self.requires_user_approval(user_message)

# The LLM analysis already includes requires_approval
analysis = await self._llm_analyze_request(user_message, context)

# No need to override anymore:
# analysis.requires_approval = requires_approval  # Remove this
```

### Option 2: Create Dedicated LLM Method
If we want to keep approval detection separate:

```python
async def requires_user_approval(self, user_message: str, analysis: Optional[RequestAnalysis] = None) -> bool:
    """Detect if user wants to review plan before execution using LLM."""

    if not self.llm:
        # Fallback to simple detection if no LLM
        return False

    prompt = f"""
    Analyze if the user is asking to see or approve a plan before execution.

    User message: "{user_message}"

    Return "true" if the user wants to:
    - See the plan/approach before starting
    - Approve before execution
    - Understand how you'll handle it
    - Know the steps/method/process

    Return "false" if the user just wants the task done.

    Consider ANY language - focus on intent, not specific words.

    Answer with just "true" or "false".
    """

    response = await self.llm.generate_text(prompt, max_tokens=10)
    return response.strip().lower() == "true"
```

## Benefits

1. **Multilingual Support**: Works in any language the LLM understands
2. **Context Aware**: Can understand nuanced requests
3. **No Maintenance**: No need to add phrases for new languages
4. **Consistent**: Uses same LLM as other analysis

## Implementation Notes

- For heuristic mode (when no LLM), we could keep a minimal fallback
- The LLM prompt should emphasize intent detection over word matching
- Consider caching results for identical messages
- Add observability to track approval detection accuracy

## Testing

Test in multiple languages:
- English: "Show me your plan first"
- Spanish: "Muéstrame tu plan primero"
- French: "Montre-moi ton plan d'abord"
- Chinese: "先给我看看你的计划"
- Japanese: "最初に計画を見せてください"

All should be detected as requiring approval.