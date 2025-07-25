#!/usr/bin/env python3
"""Test Pydantic migration for datatypes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

# Import migrated datatypes
from muxi.datatypes.async_operations import (
    TimeoutConfig,
    OperationContext,
    AsyncOperationResult,
    OperationStatus,
)
from muxi.datatypes.workflow import (
    TaskInput,
    TaskOutput,
    SubTask,
    RequestAnalysis,
    TaskResult,
    Workflow,
    WorkflowStatus,
    ApprovalStatus,
    generate_workflow_id,
    generate_task_id,
)
from muxi.datatypes.errors import (
    ErrorCodeInfo,
    ErrorDetails,
    create_error_details,
)
from muxi.datatypes.task_status import TaskStatus


def test_timeout_config():
    """Test TimeoutConfig Pydantic model."""
    # Valid config
    config = TimeoutConfig()
    assert config.config_load_timeout == 30.0
    assert config.enable_timeouts is True

    # Custom config
    config = TimeoutConfig(config_load_timeout=45.0, default_timeout=90.0, enable_timeouts=False)
    assert config.config_load_timeout == 45.0
    assert config.default_timeout == 90.0
    assert config.enable_timeouts is False

    # Validation error - timeout too high
    with pytest.raises(ValidationError) as exc_info:
        TimeoutConfig(default_timeout=400.0)
    assert "Default timeout should not exceed 5 minutes" in str(exc_info.value)

    # Validation error - negative timeout
    with pytest.raises(ValidationError) as exc_info:
        TimeoutConfig(config_load_timeout=-1.0)
    assert "greater than or equal to 0.1" in str(exc_info.value)


def test_operation_context():
    """Test OperationContext Pydantic model."""
    # Valid context
    context = OperationContext(
        operation_id="op_123",
        operation_type="test_operation",
        description="Test operation",
        timeout=30.0,
    )
    assert context.operation_id == "op_123"
    assert context.status == OperationStatus.PENDING
    assert context.result is None

    # Test properties
    assert context.elapsed_time >= 0
    assert context.is_expired is False
    assert context.time_remaining > 0

    # Validation error - empty operation_id
    with pytest.raises(ValidationError) as exc_info:
        OperationContext(operation_id="", operation_type="test", description="Test", timeout=30.0)
    # Check for min_length validation error
    assert "at least 1 character" in str(exc_info.value) or "Field cannot be empty" in str(
        exc_info.value
    )

    # Validation error - invalid timeout
    with pytest.raises(ValidationError) as exc_info:
        OperationContext(
            operation_id="op_123", operation_type="test", description="Test", timeout=5000.0
        )
    # Check for timeout validation error
    assert "less than or equal to 3600" in str(
        exc_info.value
    ) or "Timeout cannot exceed 1 hour" in str(exc_info.value)


def test_async_operation_result():
    """Test AsyncOperationResult Pydantic model."""
    # Successful result
    result = AsyncOperationResult(
        operation_id="op_123",
        status=OperationStatus.COMPLETED,
        result={"data": "test"},
        elapsed_time=5.5,
    )
    # Check status (enum might be serialized to value)
    assert result.status == OperationStatus.COMPLETED or result.status == "completed"
    assert result.error is None

    # Failed result - since use_enum_values=True, we need to use string value
    with pytest.raises(ValidationError) as exc_info:
        AsyncOperationResult(
            operation_id="op_123",
            status="failed",  # Use string value since use_enum_values=True
            # Missing error message for failure status
            elapsed_time=5.5,
        )
    assert "Error message required for failure status" in str(exc_info.value)

    # Valid failed result
    result = AsyncOperationResult(
        operation_id="op_123",
        status=OperationStatus.FAILED,
        error="Operation failed",
        elapsed_time=5.5,
        was_timeout=True,
    )
    assert result.status == OperationStatus.FAILED or result.status == "failed"
    assert result.was_timeout is True


def test_task_input_output():
    """Test TaskInput and TaskOutput Pydantic models."""
    # Valid input
    task_input = TaskInput(
        name="user_data", description="User input data", type="json", required=True
    )
    assert task_input.name == "user_data"
    assert task_input.type == "json"

    # Invalid type
    with pytest.raises(ValidationError) as exc_info:
        TaskInput(name="test", description="Test", type="invalid_type")
    assert "Invalid input type" in str(exc_info.value)

    # Valid output
    task_output = TaskOutput(
        name="result", description="Task result", type="text", target_task_ids=["task_2", "task_3"]
    )
    assert len(task_output.target_task_ids) == 2


def test_subtask():
    """Test SubTask Pydantic model."""
    # Valid subtask
    subtask = SubTask(
        id="task_123",
        description="Process data",
        required_capabilities=["data_processing"],
        estimated_complexity=7.5,
    )
    assert subtask.id == "task_123"
    assert subtask.status == TaskStatus.PENDING
    assert subtask.estimated_complexity == 7.5

    # Invalid ID format
    with pytest.raises(ValidationError) as exc_info:
        SubTask(id="task@123!", description="Test", required_capabilities=["test"])
    assert "ID must be alphanumeric" in str(exc_info.value)

    # Self-dependency validation
    with pytest.raises(ValidationError) as exc_info:
        SubTask(
            id="task_123",
            description="Test",
            required_capabilities=["test"],
            dependencies=["task_123"],  # Self-dependency
        )
    assert "Task cannot depend on itself" in str(exc_info.value)

    # Empty capabilities
    with pytest.raises(ValidationError) as exc_info:
        SubTask(id="task_123", description="Test", required_capabilities=[])
    assert "At least one capability must be required" in str(exc_info.value)


def test_workflow():
    """Test Workflow Pydantic model."""
    # Create tasks
    task1 = SubTask(id="task_1", description="First task", required_capabilities=["cap1"])
    task2 = SubTask(
        id="task_2",
        description="Second task",
        required_capabilities=["cap2"],
        dependencies=["task_1"],
    )

    # Valid workflow
    workflow = Workflow(
        id=generate_workflow_id(),
        user_request="Process my data",
        tasks={"task_1": task1, "task_2": task2},
    )
    assert workflow.id.startswith("workflow_")
    assert len(workflow.tasks) == 2
    assert workflow.status == WorkflowStatus.PENDING or workflow.status == "pending"

    # Invalid workflow ID
    with pytest.raises(ValidationError) as exc_info:
        Workflow(id="invalid_id", user_request="Test", tasks={"task_1": task1})
    assert "Workflow ID must start with 'workflow_'" in str(exc_info.value)

    # Empty tasks
    with pytest.raises(ValidationError) as exc_info:
        Workflow(id=generate_workflow_id(), user_request="Test", tasks={})
    assert "Workflow must have at least one task" in str(exc_info.value)


def test_error_code_info():
    """Test ErrorCodeInfo Pydantic model."""
    # Valid error info
    error_info = ErrorCodeInfo(
        code="TEST_ERROR",
        message="This is a test error",
        http_status=400,
        category="validation",
        description="Test error for validation",
    )
    assert error_info.code == "TEST_ERROR"
    assert error_info.http_status == 400

    # Invalid code format
    with pytest.raises(ValidationError) as exc_info:
        ErrorCodeInfo(
            code="test-error",  # Should be uppercase
            message="Test",
            http_status=400,
            category="validation",
            description="Test",
        )
    assert "Error code must be uppercase" in str(exc_info.value)

    # Invalid HTTP status
    with pytest.raises(ValidationError) as exc_info:
        ErrorCodeInfo(
            code="TEST_ERROR",
            message="Test",
            http_status=600,  # Invalid
            category="validation",
            description="Test",
        )
    assert "Invalid HTTP status code" in str(exc_info.value)

    # Invalid category
    with pytest.raises(ValidationError) as exc_info:
        ErrorCodeInfo(
            code="TEST_ERROR",
            message="Test",
            http_status=400,
            category="invalid_category",  # Not in allowed values
            description="Test",
        )

    # Test frozen model
    error_info = ErrorCodeInfo(
        code="TEST_ERROR",
        message="Test",
        http_status=400,
        category="validation",
        description="Test",
    )
    with pytest.raises(ValidationError):
        error_info.code = "CHANGED"  # Should fail as model is frozen


def test_error_details():
    """Test ErrorDetails and create_error_details."""
    # Valid error details
    details = ErrorDetails(
        code="INTERNAL_ERROR", message="Something went wrong", trace="Stack trace here"
    )
    assert details.code == "INTERNAL_ERROR"
    assert details.trace == "Stack trace here"

    # Using create_error_details
    details = create_error_details("TIMEOUT", custom_message="Custom timeout message")
    assert details.code == "TIMEOUT"
    assert details.message == "Custom timeout message"

    # Unknown error code
    details = create_error_details("UNKNOWN_ERROR_CODE", custom_message="Unknown error")
    assert details.code == "UNKNOWN_ERROR_CODE"
    assert details.message == "Unknown error"


def test_request_analysis():
    """Test RequestAnalysis Pydantic model."""
    # Valid analysis
    analysis = RequestAnalysis(
        complexity_score=8.5,
        requires_decomposition=True,
        requires_approval=True,
        implicit_subtasks=["task1", "task2"],
        required_capabilities=["cap1", "cap2"],
        acceptance_criteria=["criterion1"],
        confidence_score=0.85,
    )
    assert analysis.complexity_score == 8.5
    assert analysis.confidence_score == 0.85

    # Invalid complexity score
    with pytest.raises(ValidationError) as exc_info:
        RequestAnalysis(
            complexity_score=11.0,  # Out of range
            requires_decomposition=True,
            requires_approval=True,
            implicit_subtasks=[],
            required_capabilities=["cap1"],
            acceptance_criteria=["criterion1"],
        )
    assert "less than or equal to 10" in str(exc_info.value)

    # Empty required lists
    with pytest.raises(ValidationError) as exc_info:
        RequestAnalysis(
            complexity_score=5.0,
            requires_decomposition=True,
            requires_approval=True,
            implicit_subtasks=[],
            required_capabilities=[],  # Cannot be empty
            acceptance_criteria=["criterion1"],
        )
    assert "required_capabilities cannot be empty" in str(exc_info.value)


def test_task_result():
    """Test TaskResult Pydantic model."""
    # Successful result
    result = TaskResult(
        task_id="task_123", status=TaskStatus.DONE, outputs={"result": "data"}, execution_time=5.5
    )
    assert result.task_id == "task_123"
    assert result.execution_time == 5.5

    # Failed result without error message
    with pytest.raises(ValidationError) as exc_info:
        TaskResult(
            task_id="task_123",
            status=TaskStatus.FAILED,
            # Missing error_message for failed status
        )
    assert "Error message required for failed tasks" in str(exc_info.value)

    # Valid failed result
    result = TaskResult(
        task_id="task_123", status=TaskStatus.FAILED, error_message="Task execution failed"
    )
    assert result.error_message == "Task execution failed"


def test_model_serialization():
    """Test Pydantic model serialization."""
    # Create a complex workflow
    task = SubTask(
        id="task_123",
        description="Test task",
        required_capabilities=["test"],
        status=TaskStatus.PENDING,
    )

    workflow = Workflow(
        id=generate_workflow_id(),
        user_request="Test request",
        tasks={"task_123": task},
        status=WorkflowStatus.PENDING,
    )

    # Serialize to dict
    workflow_dict = workflow.model_dump()
    assert isinstance(workflow_dict, dict)
    assert workflow_dict["id"] == workflow.id
    assert workflow_dict["status"] == "pending"  # Enum serialized to value

    # Serialize to JSON
    workflow_json = workflow.model_dump_json()
    assert isinstance(workflow_json, str)
    assert workflow.id in workflow_json

    # Deserialize from dict
    workflow2 = Workflow(**workflow_dict)
    assert workflow2.id == workflow.id
    assert workflow2.status == workflow.status


if __name__ == "__main__":
    # Run basic tests
    print("Testing Pydantic migrations...")

    test_timeout_config()
    print("✓ TimeoutConfig tests passed")

    test_operation_context()
    print("✓ OperationContext tests passed")

    test_async_operation_result()
    print("✓ AsyncOperationResult tests passed")

    test_task_input_output()
    print("✓ TaskInput/TaskOutput tests passed")

    test_subtask()
    print("✓ SubTask tests passed")

    test_workflow()
    print("✓ Workflow tests passed")

    test_error_code_info()
    print("✓ ErrorCodeInfo tests passed")

    test_error_details()
    print("✓ ErrorDetails tests passed")

    test_request_analysis()
    print("✓ RequestAnalysis tests passed")

    test_task_result()
    print("✓ TaskResult tests passed")

    test_model_serialization()
    print("✓ Model serialization tests passed")

    print("\n✅ All Pydantic migration tests passed!")
