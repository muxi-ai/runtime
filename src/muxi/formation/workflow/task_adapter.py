"""
Task Adapter for Workflow Models

This module provides adapters to convert between the new separated workflow models
(TaskSpecification, TaskExecutionState, TaskExecutionResult) and the existing
SubTask model used throughout the MUXI Runtime.

The adapter ensures backward compatibility while allowing internal code to benefit
from the cleaner separation of concerns provided by the new models.
"""

from typing import Tuple, Optional
from datetime import datetime

from ...datatypes.workflow import SubTask, TaskInput, TaskOutput
from ...datatypes.workflow_models import (
    TaskSpecification,
    TaskExecutionState,
    TaskExecutionResult
)
from ...datatypes.task_status import TaskStatus


class TaskAdapter:
    """
    Adapter for converting between SubTask and the new separated task models.

    This adapter provides bidirectional conversion between:
    - SubTask (legacy combined model)
    - TaskSpecification + TaskExecutionState + TaskExecutionResult (new separated models)

    The adapter maintains full fidelity of data during conversion and ensures
    that all existing code using SubTask continues to work correctly.
    """

    @staticmethod
    def from_subtask(subtask: SubTask) -> Tuple[TaskSpecification, TaskExecutionState]:
        """
        Convert a SubTask into separated TaskSpecification and TaskExecutionState.

        This method extracts the immutable specification from the SubTask and
        creates the corresponding execution state tracking the runtime information.

        Args:
            subtask: The SubTask to convert

        Returns:
            Tuple of (TaskSpecification, TaskExecutionState)
        """
        # Extract expected outputs from SubTask outputs
        expected_outputs = []
        for output in subtask.outputs:
            expected_outputs.append({
                "name": output.name,
                "type": output.type,
                "description": output.description
            })

        # Extract input requirements from SubTask inputs
        input_requirements = {}
        for inp in subtask.inputs:
            input_requirements[inp.name] = {
                "type": inp.type,
                "required": inp.required,
                "description": inp.description,
                "source_task_id": inp.source_task_id
            }

        # Create the immutable specification
        spec = TaskSpecification(
            id=subtask.id,
            description=subtask.description,
            required_capabilities=subtask.required_capabilities,
            expected_outputs=expected_outputs,
            dependencies=subtask.dependencies,
            estimated_complexity=subtask.estimated_complexity,
            input_requirements=input_requirements if input_requirements else None
        )

        # Create the mutable execution state
        state = TaskExecutionState(
            spec=spec,
            status=subtask.status,
            assigned_agent_id=subtask.assigned_agent_id,
            start_time=subtask.start_time,
            progress_percent=subtask.progress_percent
        )

        # Calculate blocked_by based on dependencies
        # This would require access to the workflow, so we leave it empty for now
        # The executor should populate this based on workflow state

        return spec, state

    @staticmethod
    def to_subtask(
        spec: TaskSpecification,
        state: TaskExecutionState,
        result: Optional[TaskExecutionResult] = None
    ) -> SubTask:
        """
        Convert separated models back into a SubTask.

        This method combines the specification, execution state, and optional result
        back into a single SubTask model for compatibility with existing code.

        Args:
            spec: The task specification
            state: The current execution state
            result: Optional execution result

        Returns:
            SubTask combining all the information
        """
        # Convert expected outputs back to TaskOutput objects
        outputs = []
        for idx, expected in enumerate(spec.expected_outputs):
            outputs.append(TaskOutput(
                name=expected.get("name", f"output_{idx}"),
                description=expected.get("description", ""),
                type=expected.get("type", "data")
            ))

        # Convert input requirements back to TaskInput objects
        inputs = []
        if spec.input_requirements:
            for name, req in spec.input_requirements.items():
                inputs.append(TaskInput(
                    name=name,
                    description=req.get("description", ""),
                    type=req.get("type", "data"),
                    required=req.get("required", True),
                    source_task_id=req.get("source_task_id")
                ))

        # Create the SubTask
        subtask = SubTask(
            id=spec.id,
            description=spec.description,
            required_capabilities=list(spec.required_capabilities),
            dependencies=list(spec.dependencies),
            inputs=inputs,
            outputs=outputs,
            estimated_complexity=spec.estimated_complexity,
            assigned_agent_id=state.assigned_agent_id,
            status=state.status,
            start_time=state.start_time,
            progress_percent=state.progress_percent
        )

        # If we have a result, update the SubTask with result information
        if result:
            subtask.result = result.outputs
            subtask.end_time = result.end_time
            if not result.success:
                subtask.status = TaskStatus.FAILED
                subtask.error_message = result.error
            else:
                subtask.status = TaskStatus.COMPLETED

        return subtask

    @staticmethod
    def update_subtask_from_result(
        subtask: SubTask,
        result: TaskExecutionResult
    ) -> SubTask:
        """
        Update a SubTask with information from a TaskExecutionResult.

        This method applies the execution result to an existing SubTask,
        updating its status, outputs, and error information as needed.

        Args:
            subtask: The SubTask to update
            result: The execution result to apply

        Returns:
            Updated SubTask
        """
        # Update result data
        subtask.result = result.outputs
        subtask.end_time = result.end_time

        # Update status based on success
        if result.success:
            subtask.status = TaskStatus.COMPLETED
            subtask.error_message = None
        else:
            subtask.status = TaskStatus.FAILED
            subtask.error_message = result.error

        # If we have an assigned agent from the result, update it
        if result.agent_id and not subtask.assigned_agent_id:
            subtask.assigned_agent_id = result.agent_id

        return subtask

    @staticmethod
    def create_result_from_subtask(
        subtask: SubTask,
        agent_id: str
    ) -> Optional[TaskExecutionResult]:
        """
        Create a TaskExecutionResult from a completed SubTask.

        This method extracts result information from a SubTask that has
        completed execution and creates the corresponding result object.

        Args:
            subtask: The completed SubTask
            agent_id: ID of the agent that executed the task

        Returns:
            TaskExecutionResult if task is complete, None otherwise
        """
        # Only create result for completed tasks
        if subtask.status not in [TaskStatus.COMPLETED, TaskStatus.DONE, TaskStatus.FAILED]:
            return None

        # Determine success based on status
        success = subtask.status in [TaskStatus.COMPLETED, TaskStatus.DONE]

        # Calculate execution time
        if subtask.start_time and subtask.end_time:
            execution_time = (subtask.end_time - subtask.start_time).total_seconds()
        else:
            execution_time = 0.0

        # Extract outputs
        outputs = subtask.result if isinstance(subtask.result, dict) else {}

        return TaskExecutionResult(
            task_id=subtask.id,
            success=success,
            outputs=outputs,
            error=subtask.error_message,
            execution_time=execution_time,
            agent_id=agent_id or subtask.assigned_agent_id or "unknown",
            start_time=subtask.start_time or datetime.now(),
            end_time=subtask.end_time or datetime.now()
        )

    @staticmethod
    def validate_conversion(subtask: SubTask) -> bool:
        """
        Validate that a SubTask can be safely converted to the new models.

        This method checks that all required fields are present and valid
        for conversion to the separated models.

        Args:
            subtask: The SubTask to validate

        Returns:
            True if conversion is safe, False otherwise
        """
        # Check required fields
        if not subtask.id or not subtask.description:
            return False

        if not subtask.required_capabilities:
            return False

        # Validate status is a valid TaskStatus
        if not isinstance(subtask.status, (TaskStatus, str)):
            return False

        # Validate complexity is in valid range
        if not (1.0 <= subtask.estimated_complexity <= 10.0):
            return False

        return True


# Utility functions for common conversion patterns

def subtask_to_models(subtask: SubTask) -> Tuple[TaskSpecification, TaskExecutionState]:
    """
    Convenience function to convert SubTask to separated models.

    Args:
        subtask: SubTask to convert

    Returns:
        Tuple of (TaskSpecification, TaskExecutionState)
    """
    return TaskAdapter.from_subtask(subtask)


def models_to_subtask(
    spec: TaskSpecification,
    state: TaskExecutionState,
    result: Optional[TaskExecutionResult] = None
) -> SubTask:
    """
    Convenience function to convert separated models to SubTask.

    Args:
        spec: Task specification
        state: Execution state
        result: Optional execution result

    Returns:
        Combined SubTask
    """
    return TaskAdapter.to_subtask(spec, state, result)


def apply_result_to_subtask(
    subtask: SubTask,
    result: TaskExecutionResult
) -> SubTask:
    """
    Convenience function to apply execution result to SubTask.

    Args:
        subtask: SubTask to update
        result: Execution result to apply

    Returns:
        Updated SubTask
    """
    return TaskAdapter.update_subtask_from_result(subtask, result)
