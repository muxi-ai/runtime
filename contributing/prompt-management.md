# Prompt Management System

## Overview

MUXI Runtime uses a centralized prompt management system via the `PromptLoader` utility. This system externalizes all system prompts from Python code into markdown files, improving maintainability and enabling easier prompt optimization.

## Architecture

### PromptLoader Utility

Located at `src/muxi/formation/prompts/loader.py`, the PromptLoader is a singleton class that:

1. **Auto-discovers** all `.md` files in the prompts directory at startup
2. **Loads prompts once** during formation initialization (fail-fast pattern)
3. **Provides variable substitution** using Python's `.format()` method
4. **Offers clear error messages** showing available prompts when one is missing

### Prompt Files

All system prompts are stored as markdown files in `src/muxi/formation/prompts/`:

```
prompts/
├── agent_planning.md               # Agent task planning
├── clarification_analysis.md       # Clarification need detection
├── clarification_context_switch.md # Context switch detection
├── clarification_need_more.md      # Continuation check
├── decomposition_prompt.md         # Workflow decomposition
├── overlord_actionability_check.md # Message actionability
├── overlord_greeting_response.md   # Greeting responses
├── overlord_simple_question.md     # Question classification
├── scheduler_enhancement.md        # Task enhancement
├── scheduler_prompt_rewriter.md    # Scheduling pattern removal
├── scheduler_task_comparison.md    # Task similarity
├── sop_guide_mode.md               # SOP guide instructions
├── sop_template_mode.md            # SOP template instructions
├── soul.md                         # Default system persona
├── tool_parameter_inference.md     # Tool parameter extraction
├── workflow_request_analysis.md    # Request complexity analysis
└── loader.py                       # PromptLoader utility
```

## Usage

### Basic Usage

```python
from muxi.runtime.formation.prompts.loader import PromptLoader

# Get a prompt without variables
prompt = PromptLoader.get('soul.md')

# Get a prompt with variable substitution
prompt = PromptLoader.get(
    'overlord_actionability_check.md',
    message="Hello, how are you?"
)
```

### Variable Substitution

Prompts use Python's `.format()` style placeholders:

```markdown
# In overlord_actionability_check.md
Message: "{message}"

Examples of ACTIONABLE messages:
- "What database should I use?" → ACTIONABLE
```

Variables are passed as keyword arguments:

```python
prompt = PromptLoader.get(
    'clarification_analysis.md',
    conversation="User: Hi\nAssistant: Hello!",
    context="{}",
    capabilities="chat, search",
    mcp_services="None",
    response_style="conversational",
    cred_mode="standard",
    redirect_message="N/A"
)
```

### Complex Variable Sections

For prompts with dynamic sections, build the section first:

```python
# Build dynamic parameter section
parameters_section = ""
for param in required_params:
    parameters_section += f"\n- {param}:"
    parameters_section += f"\n  Type: {param_type}"
    parameters_section += f"\n  Description: {param_desc}"

# Pass to prompt
prompt = PromptLoader.get(
    'tool_parameter_inference.md',
    user_request=user_request,
    tool_name=tool_name,
    parameters_section=parameters_section
)
```

## Initialization

The PromptLoader is initialized during formation startup:

```python
# In src/muxi/formation/formation.py
from .prompts.loader import PromptLoader

# During formation initialization
try:
    PromptLoader.initialize()
    observability.observe(description="PromptLoader initialized successfully")
except FileNotFoundError as e:
    raise RuntimeError(f"Cannot start formation: {e}")
```

This fail-fast approach ensures:
- All prompts are valid at startup
- Missing prompts are detected immediately
- No runtime file I/O for prompt loading

## Creating New Prompts

### 1. Create the Markdown File

Create a new `.md` file in `src/muxi/formation/prompts/`:

```markdown
# my_new_prompt.md
Analyze the user request: "{user_request}"

Determine if this requires {capability_type} capabilities.

Return JSON:
{{
    "needs_capability": boolean,
    "reason": "explanation"
}}
```

Note: Use double braces `{{` and `}}` for literal braces in JSON examples.

### 2. Use in Python Code

```python
from muxi.runtime.formation.prompts.loader import PromptLoader

prompt = PromptLoader.get(
    'my_new_prompt.md',
    user_request=request,
    capability_type='research'
)

response = await llm.generate_text(prompt)
```

### 3. No Registration Required

The PromptLoader automatically discovers all `.md` files in the prompts directory. No registration or configuration is needed.

## Error Handling

### Missing Prompt File

```python
try:
    prompt = PromptLoader.get('nonexistent.md')
except KeyError as e:
    # Error message shows available prompts:
    # "Prompt not found: nonexistent.md. Available: ['agent_planning.md', ...]"
```

### Missing Variables

Python's `.format()` doesn't raise errors for missing variables by default. The placeholder will remain in the output:

```python
prompt = PromptLoader.get('overlord_actionability_check.md')
# Result: 'Message: "{message}"' (placeholder not replaced)
```

To ensure all variables are provided, include them explicitly:

```python
prompt = PromptLoader.get(
    'overlord_actionability_check.md',
    message=user_message  # Always provide required variables
)
```

## Best Practices

### 1. Use Descriptive Variable Names

```markdown
# Good
User Request: "{user_request}"
Original Prompt: "{original_prompt}"

# Avoid
Input: "{input}"
Data: "{data}"
```

### 2. Keep Prompts Focused

Each prompt should have a single, clear purpose. Split complex prompts into multiple files if needed.

### 3. Document Variable Requirements

Add comments in the prompt file to document required variables:

```markdown
# Variables required:
# - user_request: The user's original request
# - context: Conversation context (JSON string)
# - capabilities: Comma-separated list of capabilities

Analyze the request: "{user_request}"
```

### 4. Version Control Considerations

- Track prompt changes in git for version history
- Use meaningful commit messages when modifying prompts
- Consider A/B testing different prompt versions

### 5. Testing Prompts

Test prompt loading and variable substitution:

```python
def test_my_prompt():
    prompt = PromptLoader.get(
        'my_prompt.md',
        variable1="test value",
        variable2="another value"
    )
    assert "test value" in prompt
    assert "another value" in prompt
```

## Migration from Inline Prompts

To migrate an inline prompt:

1. **Extract the prompt** to a new `.md` file
2. **Replace variables** with `{variable_name}` placeholders
3. **Update Python code** to use PromptLoader:

```python
# Before
prompt = f"""
Analyze this: {message}
Return JSON: {{"result": "analysis"}}
"""

# After
prompt = PromptLoader.get(
    'analysis_prompt.md',
    message=message
)
```

## Performance Considerations

- **Startup Cost**: All prompts loaded at initialization (~10ms for 16 prompts)
- **Memory Usage**: Minimal (~30KB for typical prompt set)
- **Runtime Performance**: Zero file I/O after initialization
- **Caching**: Prompts cached in memory, no repeated reads

## Troubleshooting

### PromptLoader Not Initialized

```
RuntimeError: PromptLoader not initialized. Call initialize() first.
```

Ensure formation initialization includes PromptLoader setup.

### Prompt File Not Found

```
FileNotFoundError: No prompt files found in /path/to/prompts
```

Check that prompt files exist in `src/muxi/formation/prompts/`.

### Variable Substitution Issues

If variables aren't being replaced:
1. Check variable names match exactly (case-sensitive)
2. Ensure variables are passed as keyword arguments
3. Verify placeholder format: `{variable_name}`

## Future Enhancements

Potential improvements under consideration:

1. **Hot Reloading**: Reload prompts without restart in development
2. **Prompt Versioning**: Support multiple versions of same prompt
3. **Schema Validation**: Validate expected variables
4. **Metrics Collection**: Track prompt usage and performance
5. **Localization**: Multi-language prompt support

## Related Documentation

- [Formation Loading](configuration/README.md)
- [Clarification System](clarification-system.md)
- [Workflow Orchestration](workflow/orchestration.md)
- [Scheduler Architecture](scheduler/architecture.md)
