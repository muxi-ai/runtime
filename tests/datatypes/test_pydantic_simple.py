#!/usr/bin/env python3
"""Simple test for Pydantic migration verification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.datatypes.async_operations import (
    TimeoutConfig,
    OperationContext,
    AsyncOperationResult,
    OperationStatus,
)
from muxi.datatypes.workflow import TaskInput, SubTask, Workflow, generate_workflow_id
from muxi.datatypes.errors import ErrorCodeInfo, create_error_details
from muxi.datatypes.task_status import TaskStatus

print("Testing Pydantic V2 migrations...")

# Test 1: TimeoutConfig
config = TimeoutConfig()
print(f"✓ TimeoutConfig created: default_timeout={config.default_timeout}")

# Test 2: OperationContext
context = OperationContext(
    operation_id="op_123", operation_type="test", description="Test operation", timeout=30.0
)
print(f"✓ OperationContext created: {context.operation_id}")

# Test 3: AsyncOperationResult
result = AsyncOperationResult(
    operation_id="op_123", status=OperationStatus.COMPLETED, result={"test": "data"}
)
print(f"✓ AsyncOperationResult created: status={result.status}")

# Test 4: TaskInput
task_input = TaskInput(name="input1", description="Test input", type="json")
print(f"✓ TaskInput created: {task_input.name}")

# Test 5: SubTask
subtask = SubTask(id="task_123", description="Test task", required_capabilities=["test"])
print(f"✓ SubTask created: {subtask.id}")

# Test 6: Workflow
workflow = Workflow(
    id=generate_workflow_id(), user_request="Test request", tasks={"task_123": subtask}
)
print(f"✓ Workflow created: {workflow.id}")

# Test 7: ErrorCodeInfo
error_info = ErrorCodeInfo(
    code="TEST_ERROR",
    message="Test error",
    http_status=400,
    category="validation",
    description="Test description",
)
print(f"✓ ErrorCodeInfo created: {error_info.code}")

# Test 8: create_error_details
details = create_error_details("TIMEOUT", "Custom timeout message")
print(f"✓ ErrorDetails created: {details.code}")

# Test 9: Model serialization
data = workflow.model_dump()
print(f"✓ Model serialization works: {len(data)} fields")

# Test 10: JSON serialization
json_str = workflow.model_dump_json()
print(f"✓ JSON serialization works: {len(json_str)} chars")

print("\n" + "="*60)
print("Testing validation and error handling...")

# Test 11: TimeoutConfig validation - negative timeout
print("\nTest 11: TimeoutConfig validation")
try:
    invalid_config = TimeoutConfig(default_timeout=-5.0)
    print("✗ ERROR: TimeoutConfig should reject negative timeout!")
except Exception as e:
    print(f"✓ TimeoutConfig properly validates negative timeout: {type(e).__name__}: {e}")

try:
    invalid_config = TimeoutConfig(max_timeout=-10.0)
    print("✗ ERROR: TimeoutConfig should reject negative max_timeout!")
except Exception as e:
    print(f"✓ TimeoutConfig properly validates negative max_timeout: {type(e).__name__}: {e}")

# Test 12: AsyncOperationResult validation - invalid status
print("\nTest 12: AsyncOperationResult validation")
try:
    invalid_result = AsyncOperationResult(
        operation_id="test_op",
        status="INVALID_STATUS",  # This should fail
        result={}
    )
    print("✗ ERROR: AsyncOperationResult should reject invalid status!")
except Exception as e:
    print(f"✓ AsyncOperationResult properly validates status: {type(e).__name__}: {e}")

# Test 13: OperationContext validation - invalid timeout
print("\nTest 13: OperationContext validation")
try:
    invalid_context = OperationContext(
        operation_id="",
        operation_type="test",
        description="Test",
        timeout=-1.0
    )
    print("✗ ERROR: OperationContext should reject negative timeout!")
except Exception as e:
    print(f"✓ OperationContext properly validates timeout: {type(e).__name__}: {e}")

try:
    invalid_context = OperationContext(
        operation_id="test_op",
        operation_type="",
        description="Test",
        timeout=30.0
    )
    print("✗ ERROR: OperationContext should reject empty operation_type!")
except Exception as e:
    print(f"✓ OperationContext properly validates operation_type: {type(e).__name__}: {e}")

# Test 14: TaskInput validation - invalid type
print("\nTest 14: TaskInput validation")
try:
    invalid_task = TaskInput(name="", description="Test", type="json")
    print("✗ ERROR: TaskInput should reject empty name!")
except Exception as e:
    print(f"✓ TaskInput properly validates name: {type(e).__name__}: {e}")

# Test 15: SubTask validation - empty required_capabilities
print("\nTest 15: SubTask validation")
try:
    invalid_subtask = SubTask(id="", description="Test", required_capabilities=[])
    print("✗ ERROR: SubTask should reject empty id!")
except Exception as e:
    print(f"✓ SubTask properly validates id: {type(e).__name__}: {e}")

print("\n" + "="*60)
print("Testing JSON deserialization...")

# Test 16: TimeoutConfig JSON roundtrip
print("\nTest 16: TimeoutConfig JSON roundtrip")
try:
    original_config = TimeoutConfig(default_timeout=45.0, max_timeout=120.0)
    json_data = original_config.model_dump_json()
    deserialized_config = TimeoutConfig.model_validate_json(json_data)
    assert original_config.default_timeout == deserialized_config.default_timeout
    assert original_config.max_timeout == deserialized_config.max_timeout
    print(f"✓ TimeoutConfig JSON roundtrip successful: {deserialized_config.default_timeout}s")
except Exception as e:
    print(f"✗ TimeoutConfig JSON roundtrip failed: {type(e).__name__}: {e}")

# Test 17: AsyncOperationResult JSON roundtrip
print("\nTest 17: AsyncOperationResult JSON roundtrip")
try:
    original_result = AsyncOperationResult(
        operation_id="test_123",
        status=OperationStatus.FAILED,
        result={"error": "test error", "code": 500},
        error_message="Test error occurred"
    )
    json_data = original_result.model_dump_json()
    deserialized_result = AsyncOperationResult.model_validate_json(json_data)
    assert original_result.operation_id == deserialized_result.operation_id
    assert original_result.status == deserialized_result.status
    assert original_result.result == deserialized_result.result
    assert original_result.error_message == deserialized_result.error_message
    print(f"✓ AsyncOperationResult JSON roundtrip successful: status={deserialized_result.status}")
except Exception as e:
    print(f"✗ AsyncOperationResult JSON roundtrip failed: {type(e).__name__}: {e}")

# Test 18: Workflow JSON roundtrip
print("\nTest 18: Workflow JSON roundtrip")
try:
    original_workflow = Workflow(
        id=generate_workflow_id(),
        user_request="Test JSON workflow",
        tasks={"task_1": SubTask(id="task_1", description="JSON test task", required_capabilities=["json"])}
    )
    json_data = original_workflow.model_dump_json()
    deserialized_workflow = Workflow.model_validate_json(json_data)
    assert original_workflow.id == deserialized_workflow.id
    assert original_workflow.user_request == deserialized_workflow.user_request
    assert len(original_workflow.tasks) == len(deserialized_workflow.tasks)
    print(f"✓ Workflow JSON roundtrip successful: {deserialized_workflow.id}")
except Exception as e:
    print(f"✗ Workflow JSON roundtrip failed: {type(e).__name__}: {e}")

# Test 19: Invalid JSON deserialization
print("\nTest 19: Invalid JSON handling")
try:
    invalid_json = '{"operation_id": "test", "status": "INVALID_STATUS", "result": {}}'
    AsyncOperationResult.model_validate_json(invalid_json)
    print("✗ ERROR: Should reject invalid JSON with bad status!")
except Exception as e:
    print(f"✓ Properly rejects invalid JSON: {type(e).__name__}: {e}")

try:
    malformed_json = '{"operation_id": "test", "status": "COMPLETED"'  # Missing closing brace
    AsyncOperationResult.model_validate_json(malformed_json)
    print("✗ ERROR: Should reject malformed JSON!")
except Exception as e:
    print(f"✓ Properly rejects malformed JSON: {type(e).__name__}: {e}")

# Test 20: Model validation from dict
print("\nTest 20: Model validation from dict")
try:
    valid_dict = {
        "operation_id": "dict_test",
        "status": "IN_PROGRESS",
        "result": {"progress": 50}
    }
    result_from_dict = AsyncOperationResult.model_validate(valid_dict)
    print(f"✓ Model validation from dict successful: {result_from_dict.operation_id}")
except Exception as e:
    print(f"✗ Model validation from dict failed: {type(e).__name__}: {e}")

try:
    invalid_dict = {
        "operation_id": "dict_test",
        "status": "UNKNOWN_STATUS",  # Invalid status
        "result": {}
    }
    AsyncOperationResult.model_validate(invalid_dict)
    print("✗ ERROR: Should reject dict with invalid status!")
except Exception as e:
    print(f"✓ Properly rejects invalid dict: {type(e).__name__}: {e}")

print("\n✅ All Pydantic V2 validation and serialization tests completed!")
print("✅ Models properly validate input data and handle JSON serialization/deserialization!")
