# MUXI LLM Migration Plan

This document outlines the steps needed to replace the current provider-specific model implementations with the standardized MUXI LLM package.

> **Important Note**: Backward compatibility is NOT a requirement for this migration. We are making a clean break with the old implementation.

## Status

- ✅ 1. Dependency Management
- ✅ 2. Code Changes
  - ✅ 2.1 Create unified Model class in base.py
  - ✅ 2.2 Update Overlord to use new Model class
  - ✅ 2.3 Update Muxi facade to use new Model class
  - ✅ 2.4 Update YAML configs to use new format
- ⏳ 3. Multi-Modal Support
- ⏳ 4. Testing
- ⏳ 5. Documentation Updates

## Progress Notes

### Completed Steps

#### 1. Dependency Management
- Removed provider-specific dependencies from requirements.txt
- Added muxi-llm as a dependency in core package
- Updated setup.py to include muxi-llm

#### 2. Code Changes
- Created a new Model class in base.py that uses muxi-llm
- Added create_model method to Overlord for creating models with provider/model format
- Updated _initialize_routing_model in Overlord to use the new Model class
- Modified Muxi facade's _create_model method to support both old and new config formats
- Updated example YAML config files to use new 'llm' key instead of 'model'
- Implemented provider/model format (e.g., "openai/gpt-4o") in config files

### Next Steps

#### 3. Multi-Modal Support
- Test multi-modal capabilities with the new Model implementation
- Ensure image and audio inputs work correctly with relevant models

#### 4. Testing
- Create test cases for all model functionality
- Test with various provider configurations
- Verify backward compatibility with legacy configuration format

#### 5. Documentation Updates
- Update user-facing documentation to reflect new model configuration format
- Add examples of using the new provider/model format
- Update README.md with new model usage instructions

## 1. Dependency Management

### 1.1 Remove Current Model Provider Dependencies

- Remove direct dependencies on provider packages from `requirements.txt`:
  - `openai`
  - `anthropic` (if present)
  - Any other provider-specific packages

### 1.2 Add MUXI LLM Dependency

- Add `muxi-llm` to requirements.txt/setup.py files
- Specify appropriate version constraint (e.g., `muxi-llm>=0.1.0`)
- For development mode, use `-e .` for local installation

### 1.3 Installation Commands

After updating the dependency files, run the following commands to update your development environment:

```bash
# Main project dependencies
pip install -r requirements.txt

# Install the packages in development mode
pip install -e .

# Optional: Install specific packages with their dependencies
pip install -e packages/core
pip install -e packages/llm
```

## 2. Code Changes

### 2.1 Identify Files for Modification

Key files that likely need modification:

- `muxi/core/models/base.py` - Base model interface
- `muxi/core/models/providers/*.py` - Provider-specific implementations
- `muxi/core/agent.py` - Agent class that uses models
- `muxi/core/overlord.py` - Overlord that manages agents and models
- `muxi/config/*.py` - Configuration handling

### 2.2 Replace Base Model Interface

- Update or replace the base model interface to use MUXI LLM's API
- Remove any provider-specific methods or attributes

```python
# Before
class Model:
    def __init__(self, model_name, api_key, ...):
        # ...

    async def chat(self, messages, ...):
        # ...

# After
from muxi_llm import LLM

class Model:
    def __init__(self, model=None, api_key=None, **kwargs):
        # Note: model parameter now expects the format "provider/model-name"
        self.llm = LLM(model=model, api_key=api_key, **kwargs)

    async def chat(self, messages, **kwargs):
        return await self.llm.chat(messages, **kwargs)
```

### 2.3 Update Agent and Overlord Classes

- Modify how the Agent class initializes and uses models
- Update Overlord's agent creation method

```python
# Agent class modification
class Agent:
    def __init__(self, model=None, ...):
        # Replace provider-specific model handling with MUXI LLM
        if isinstance(model, dict):
            # Handle dict configuration - now with unified model name format
            model = model.get("model")  # Now expects "openai/gpt-4o" format
            api_key = model.get("api_key")
            # Other model parameters
            self.model = Model(model=model, api_key=api_key)
        else:
            # Model object already created
            self.model = model
```

### 2.4 Update Configuration Handling

- Modify config loading to work with MUXI LLM configuration format
- Update YAML/JSON parsing for model configuration
- Update environment variable handling
- Change the YAML key from `model:` to `llm:` for clarity and consistency
- Use the unified model naming format (`provider/model-name`)

```python
# Example configuration format
"""
llm:
  model: openai/gpt-4o
  api_key: ${OPENAI_API_KEY}
  temperature: 0.7
  max_tokens: 2000
"""
```

### 2.5 Remove Provider-Specific Code

- Delete all provider-specific model implementations
- Remove any provider-specific code paths and references

## 3. Multi-Modal Support

Update any existing code to use MUXI LLM's multi-modal capabilities:

```python
# Before
# Specific provider code for handling images

# After
from muxi_llm import Content

async def process_with_image(agent, text, image_path):
    content = [
        Content.text(text),
        Content.image_path(image_path)
    ]
    response = await agent.model.llm.chat(content=content)
    return response
```

## 4. Testing

### 4.1 Unit Tests

- Create tests specifically for the new MUXI LLM integration
- Test different model providers through MUXI LLM
- Test streaming responses
- Test error handling and retries

### 4.2 Integration Tests

- Test agent creation with model configuration
- Test overlord operations with agents using different models
- Test memory operations with models

### 4.3 Performance Testing

- Benchmark performance with the new implementation
- Look for any regressions or issues

## 5. Documentation Updates

### 5.1 Update Docs for Developers

- Update architecture documentation to show MUXI LLM integration
- Update code examples to use the new interface

### 5.2 Update User-Facing Documentation

- Update examples in README.md
- Update quick-start guide
- Update configuration documentation

## 6. Implementation Approach

### Phase 1: Core Interface Changes

1. Add MUXI LLM as a dependency
2. Create adapter or update base model class to use MUXI LLM
3. Test basic functionality with the new implementation

### Phase 2: Full Implementation

1. Update Agent and Overlord classes to use the new interface
2. Update configuration handling for models
3. Remove old provider-specific implementations
4. Implement comprehensive tests

### Phase 3: Finalization

1. Update all documentation
2. Verify all tests pass
3. Clean up any remaining references to old implementation

## 7. Potential Challenges

- Different response format between old and new implementations
- Error handling differences
- Configuration differences
- Performance variations

## 8. Timeline Estimate

- Phase 1: 2-3 days
- Phase 2: 3-5 days
- Phase 3: 1-2 days
- Total: 6-10 days depending on complexity

## 9. Resources

- MUXI LLM Documentation
- Current Provider Model Code
- Test Framework

## 10. Success Criteria

- All tests pass with the new implementation
- No references to old provider-specific code remain
- Configuration works as expected
- Performance matches or exceeds the previous implementation
