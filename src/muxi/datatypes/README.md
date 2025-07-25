# MUXI Runtime Datatypes

This directory contains the unified data structures used across all MUXI Runtime services and components.

## Overview

All data types in MUXI Runtime are defined using Pydantic V2 models, providing:
- **Type Safety**: Strong typing with runtime validation
- **Serialization**: Automatic JSON/dict conversion
- **Validation**: Built-in field validation and constraints
- **Documentation**: Self-documenting through field descriptions

## Migration to Pydantic V2

As of June 2025, all dataclasses have been migrated to Pydantic V2 models:

### Migrated Modules

- **async_operations.py**: Async operation management with timeouts
  - `TimeoutConfig`: Configurable timeouts for different operations
  - `OperationContext`: Context tracking for async operations
  - `AsyncOperationResult`: Results with status and error handling

- **workflow.py**: Workflow execution data structures
  - `TaskInput`, `TaskOutput`: Input/output specifications
  - `SubTask`: Individual task definitions with validation
  - `Workflow`: Complete workflow with task dependencies
  - `RequestAnalysis`, `TaskResult`: Analysis and execution results

- **errors.py**: Standardized error handling
  - `ErrorCodeInfo`: Immutable error definitions
  - `ErrorDetails`: Runtime error details
  - Centralized error code registry

### Key Features

1. **Field Validation**: All models include comprehensive validation
   ```python
   @field_validator("timeout")
   @classmethod
   def validate_timeout(cls, v):
       if v > 300:
           raise ValueError("Timeout should not exceed 5 minutes")
       return v
   ```

2. **Enum Serialization**: Configured with `use_enum_values=True` for JSON compatibility

3. **Immutable Models**: Critical models like `ErrorCodeInfo` use `frozen=True`

4. **Model Configuration**: Standardized with `ConfigDict`:
   - `extra="forbid"`: Prevent unknown fields
   - `validate_assignment=True`: Runtime validation
   - `use_enum_values=True`: Enum serialization

## Usage Examples

### Creating Models
```python
from muxi.datatypes.async_operations import TimeoutConfig

config = TimeoutConfig(
    default_timeout=60.0,
    enable_timeouts=True
)
```

### Serialization
```python
# To dictionary
data = model.model_dump()

# To JSON
json_str = model.model_dump_json()

# From dictionary
model = ModelClass(**data)
```

### Validation
```python
from pydantic import ValidationError

try:
    config = TimeoutConfig(default_timeout=500.0)  # Too high
except ValidationError as e:
    print(e)  # "Default timeout should not exceed 5 minutes"
```

## Best Practices

1. **Use Field Descriptions**: Document all fields with the `description` parameter
2. **Set Constraints**: Use `Field()` with `ge`, `le`, `min_length`, etc.
3. **Custom Validators**: Add field validators for complex validation logic
4. **Consistent Naming**: Follow Python naming conventions (snake_case)
5. **Type Hints**: Always provide complete type annotations

## Module Reference

- **async_operations.py**: Async operation management
- **caching.py**: Cache configuration and policies
- **clarification.py**: Clarification system types
- **errors.py**: Error codes and details
- **exceptions.py**: Custom exception types
- **intelligence.py**: AI/LLM intelligence types
- **llm.py**: LLM provider configurations
- **mcp.py**: Model Context Protocol types
- **observability.py**: Monitoring and event types
- **parallel.py**: Parallel execution structures
- **resilience.py**: Circuit breaker and resilience patterns
- **response.py**: Standardized response formats
- **retry.py**: Retry policies and configurations
- **schema.py**: JSON schema definitions
- **task_status.py**: Task status enumerations
- **validation.py**: Validation utilities
- **workflow.py**: Workflow execution types

## Testing

All Pydantic models are thoroughly tested:
- Field validation tests
- Serialization/deserialization tests
- Edge case handling
- Integration with services

Run tests with:
```bash
pytest tests/datatypes/
```
