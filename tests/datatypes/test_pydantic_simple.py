#!/usr/bin/env python3
"""Simple test for Pydantic migration verification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.runtime.datatypes.async_operations import (
    TimeoutConfig,
    OperationContext,
    AsyncOperationResult,
    OperationStatus,
)
from muxi.runtime.datatypes.workflow import TaskInput, SubTask, Workflow, generate_workflow_id
from muxi.runtime.datatypes.errors import ErrorCodeInfo, create_error_details
from muxi.runtime.datatypes.task_status import TaskStatus

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

print("\n✅ All Pydantic V2 migrations are working correctly!")
