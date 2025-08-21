"""
Task Adapter for Workflow Models

This module provides adapters to convert between the new separated workflow models
(TaskSpecification, TaskExecutionState, TaskExecutionResult) and the existing
SubTask model used throughout the MUXI Runtime.

The adapter ensures backward compatibility while allowing internal code to benefit
from the cleaner separation of concerns provided by the new models.

Important:
    All task outputs MUST have explicit names. The adapter will raise a ValueError
    if any output is missing a name to ensure data integrity and prevent potential
    mismatches in task dependencies and data flow.
"""

from typing import Tuple, Optional, TYPE_CHECKING

from ...datatypes.workflow import SubTask, TaskInput, TaskOutput
from ...datatypes.workflow_models import TaskSpecification, TaskExecutionState, TaskExecutionResult
from ...datatypes.task_status import TaskStatus

if TYPE_CHECKING:
    from ...datatypes.workflow import Workflow


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
    def from_subtask(
        subtask: SubTask,
        workflow: Optional['Workflow'] = None
    ) -> Tuple[TaskSpecification, TaskExecutionState]:
        """
        Convert a SubTask into separated TaskSpecification and TaskExecutionState.

        This method extracts the immutable specification from the SubTask and
        creates the corresponding execution state tracking the runtime information.

        Note:
            The `blocked_by` field in TaskExecutionState will be calculated based on the
            workflow context if provided. Otherwise, it will be initialized as an empty set.
            When workflow is provided, blocked_by will contain IDs of incomplete dependency
            the actual workflow state.

        Args:
            subtask: The SubTask to convert

        Returns:
            Tuple of (TaskSpecification, TaskExecutionState)

        Raises:
            ValueError: If the subtask is missing required fields or contains invalid data
            TypeError: If the subtask is not a valid SubTask instance
        """
        # Validate input type
        if not subtask:
            raise ValueError("SubTask cannot be None")

        if not hasattr(subtask, "id"):
            raise TypeError("Invalid SubTask: missing required attributes")

        # Use existing validation method
        if not TaskAdapter.validate_conversion(subtask):
            raise ValueError(
                f"SubTask {subtask.id if hasattr(subtask, 'id') and subtask.id else '<unknown>'} failed validation"
            )

        # Validate required fields
        if not subtask.id:
            raise ValueError("SubTask.id is required but was empty or None")

        if not subtask.description:
            raise ValueError(f"SubTask {subtask.id} has no description")

        # Validate outputs list
        if subtask.outputs is None:
            raise ValueError(
                f"SubTask {subtask.id} has None outputs - expected a list (can be empty)"
            )

        if not isinstance(subtask.outputs, list):
            raise TypeError(
                f"SubTask {subtask.id} outputs must be a list, got {type(subtask.outputs).__name__}"
            )

        # Validate inputs list
        if subtask.inputs is None:
            raise ValueError(
                f"SubTask {subtask.id} has None inputs - expected a list (can be empty)"
            )

        if not isinstance(subtask.inputs, list):
            raise TypeError(
                f"SubTask {subtask.id} inputs must be a list, got {type(subtask.inputs).__name__}"
            )

        # Validate required_capabilities
        if not subtask.required_capabilities:
            raise ValueError(f"SubTask {subtask.id} must have at least one required capability")

        if not isinstance(subtask.required_capabilities, list):
            raise TypeError(
                f"SubTask {subtask.id} required_capabilities must be a list, "
                f"got {type(subtask.required_capabilities).__name__}"
            )

        # Validate dependencies
        if subtask.dependencies is None:
            raise ValueError(
                f"SubTask {subtask.id} has None dependencies - expected a list (can be empty)"
            )

        if not isinstance(subtask.dependencies, list):
            raise TypeError(
                f"SubTask {subtask.id} dependencies must be a list, got {type(subtask.dependencies).__name__}"
            )

        # Validate estimated_complexity
        if subtask.estimated_complexity is None:
            raise ValueError(f"SubTask {subtask.id} has no estimated_complexity")

        if not isinstance(subtask.estimated_complexity, (int, float)):
            raise TypeError(
                f"SubTask {subtask.id} estimated_complexity must be a number, "
                f"got {type(subtask.estimated_complexity).__name__}"
            )

        if not (1.0 <= subtask.estimated_complexity <= 10.0):
            raise ValueError(
                f"SubTask {subtask.id} estimated_complexity must be between 1.0 and 10.0, "
                f"got {subtask.estimated_complexity}"
            )

        # Validate status
        if not subtask.status:
            raise ValueError(f"SubTask {subtask.id} has no status")

        # Extract expected outputs from SubTask outputs
        expected_outputs = []
        for idx, output in enumerate(subtask.outputs):
            # Validate output has a name
            if not output.name:
                raise ValueError(
                    f"Output at index {idx} in subtask {subtask.id} is missing a name. "
                    "All outputs must have explicit names to ensure data integrity."
                )
            expected_outputs.append(
                {"name": output.name, "type": output.type, "description": output.description}
            )

        # Extract input requirements from SubTask inputs
        input_requirements = {}
        for idx, inp in enumerate(subtask.inputs):
            # Validate input has a name
            if not inp.name:
                raise ValueError(
                    f"Input at index {idx} in subtask {subtask.id} is missing a name. "
                    "All inputs must have explicit names to ensure data integrity."
                )
            input_requirements[inp.name] = {
                "type": inp.type,
                "required": inp.required,
                "description": inp.description,
                "source_task_id": inp.source_task_id,
            }

        # Create the immutable specification
        spec = TaskSpecification(
            id=subtask.id,
            description=subtask.description,
            required_capabilities=subtask.required_capabilities,
            expected_outputs=expected_outputs,
            dependencies=subtask.dependencies,
            estimated_complexity=subtask.estimated_complexity,
            input_requirements=input_requirements if input_requirements else None,
        )

        # Create the mutable execution state
        state = TaskExecutionState(
            spec=spec,
            status=subtask.status,
            assigned_agent_id=subtask.assigned_agent_id,
            start_time=subtask.start_time,
            progress_percent=subtask.progress_percent,
        )

        # Calculate blocked_by based on dependencies if workflow context is available
        if workflow and subtask.dependencies:
            # Find all dependency tasks that haven't completed yet
            blocked_by = set()
            for dep_id in subtask.dependencies:
                # Direct lookup by ID - O(1) instead of O(N)
                dep_task = workflow.tasks.get(dep_id)

                # If dependency task exists and isn't completed, add to blocked_by
                # Check both string and enum values for COMPLETED and DONE
                if dep_task and dep_task.status not in ['COMPLETED', 'DONE', TaskStatus.COMPLETED, TaskStatus.DONE]:
                    blocked_by.add(dep_id)

            # Update the state with calculated blocked_by
            state.blocked_by = blocked_by
        # else: blocked_by is already initialized as empty set in TaskExecutionState

        return spec, state

    @staticmethod
    def to_subtask(
        spec: TaskSpecification,
        state: TaskExecutionState,
        result: Optional[TaskExecutionResult] = None,
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
            # Ensure output has an explicit name
            if not expected.get("name"):
                raise ValueError(
                    f"Output at index {idx} in task {spec.id} is missing a name. "
                    "All outputs must have explicit names to ensure data integrity."
                )
            outputs.append(
                TaskOutput(
                    name=expected["name"],
                    description=expected.get("description", ""),
                    type=expected.get("type", "data"),
                )
            )

        # Convert input requirements back to TaskInput objects
        inputs = []
        if spec.input_requirements:
            for name, req in spec.input_requirements.items():
                inputs.append(
                    TaskInput(
                        name=name,
                        description=req.get("description", ""),
                        type=req.get("type", "data"),
                        required=req.get("required", True),
                        source_task_id=req.get("source_task_id"),
                    )
                )

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
            progress_percent=state.progress_percent,
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
    def update_subtask_from_result(subtask: SubTask, result: TaskExecutionResult) -> SubTask:
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
        subtask: SubTask, agent_id: str
    ) -> Optional[TaskExecutionResult]:
        """
        Create a TaskExecutionResult from a completed SubTask.

        This method extracts result information from a SubTask that has
        completed execution and creates the corresponding result object.

        The method handles various types of results:
        - dict: Used as-is
        - str: Wrapped as {"result": <string>}
        - list/tuple: Wrapped as {"results": <list>}
        - int/float/bool: Wrapped as {"value": <primitive>}
        - Objects with __dict__: Converted to dict
        - Other types: Converted to string and wrapped as {"result": <string>}

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

        # Extract outputs with proper type handling
        outputs = {}
        if subtask.result is not None:
            if isinstance(subtask.result, dict):
                outputs = subtask.result
            elif isinstance(subtask.result, str):
                # Single string result gets wrapped as 'result' key
                outputs = {"result": subtask.result}
            elif isinstance(subtask.result, (list, tuple)):
                # List/tuple results get wrapped as 'results' key
                outputs = {"results": list(subtask.result)}
            elif isinstance(subtask.result, (int, float, bool)):
                # Primitive types get wrapped as 'value' key
                outputs = {"value": subtask.result}
            else:
                # For other types, attempt to extract meaningful data
                try:
                    # Try to convert to dict if object has __dict__
                    if hasattr(subtask.result, "__dict__"):
                        outputs = subtask.result.__dict__
                    else:
                        # Last resort: convert to string representation
                        outputs = {"result": str(subtask.result)}
                except Exception:
                    # If all else fails, use string representation
                    outputs = {"result": str(subtask.result)}

        # Ensure we have valid timestamps - raise error if missing
        if not subtask.start_time:
            raise ValueError(f"Cannot create result for task {subtask.id}: start_time is missing")
        if not subtask.end_time:
            raise ValueError(f"Cannot create result for task {subtask.id}: end_time is missing")

        return TaskExecutionResult(
            task_id=subtask.id,
            success=success,
            outputs=outputs,
            error=subtask.error_message,
            execution_time=execution_time,
            agent_id=agent_id or subtask.assigned_agent_id or "unknown",
            start_time=subtask.start_time,
            end_time=subtask.end_time,
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


def subtask_to_models(
    subtask: SubTask,
    workflow: Optional['Workflow'] = None
) -> Tuple[TaskSpecification, TaskExecutionState]:
    """
    Convenience function to convert SubTask to separated models.

    Args:
        subtask: SubTask to convert
        workflow: Optional workflow context for calculating blocked_by field

    Returns:
        Tuple of (TaskSpecification, TaskExecutionState)
    """
    return TaskAdapter.from_subtask(subtask, workflow=workflow)


def models_to_subtask(
    spec: TaskSpecification, state: TaskExecutionState, result: Optional[TaskExecutionResult] = None
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


def apply_result_to_subtask(subtask: SubTask, result: TaskExecutionResult) -> SubTask:
    """
    Convenience function to apply execution result to SubTask.

    Args:
        subtask: SubTask to update
        result: Execution result to apply

    Returns:
        Updated SubTask
    """
    return TaskAdapter.update_subtask_from_result(subtask, result)
