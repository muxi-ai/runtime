"""
Async Operation Manager

Utility for managing async operations with timeout and cancellation support in Formation.
"""

import asyncio
from typing import Any, Dict, Optional, Callable, Awaitable, TypeVar, List

from ..utils.id_generator import generate_nanoid
from ..datatypes.async_operations import (
    OperationStatus,
    OperationContext,
    CancellationToken,
    TimeoutConfig,
    AsyncOperationResult,
    CancellationError,
    OperationTimeoutError,
)

T = TypeVar("T")


class AsyncOperationManager:
    """
    Manager for async operations with timeout and cancellation support.

    Provides a centralized way to manage async operations in Formation,
    with built-in timeout handling, cancellation support, and operation tracking.
    """

    def __init__(self, timeout_config: Optional[TimeoutConfig] = None):
        """
        Initialize the async operation manager.

        Args:
            timeout_config: Configuration for operation timeouts
        """
        self.timeout_config = timeout_config or TimeoutConfig()
        self._active_operations: Dict[str, OperationContext] = {}
        self._global_cancellation_token = CancellationToken()

    async def execute_with_timeout(
        self,
        operation: Callable[..., Awaitable[T]],
        operation_type: str,
        description: str,
        timeout: Optional[float] = None,
        cancellation_token: Optional[CancellationToken] = None,
        operation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs,
    ) -> AsyncOperationResult:
        """
        Execute an async operation with timeout and cancellation support.

        Args:
            operation: The async function to execute
            operation_type: Type of operation (e.g., 'config_load', 'secrets_operation')
            description: Human-readable description of the operation
            timeout: Timeout in seconds (uses default from config if None)
            cancellation_token: Token for cancelling the operation
            operation_id: Unique identifier for the operation
            metadata: Additional metadata for the operation
            *args, **kwargs: Arguments to pass to the operation

        Returns:
            AsyncOperationResult with operation status and result
        """
        # Generate operation ID if not provided
        if operation_id is None:
            operation_id = f"{operation_type}_{generate_nanoid()}"

        # Determine timeout
        if timeout is None:
            timeout = self._get_default_timeout(operation_type)

        # Create operation context
        context = OperationContext(
            operation_id=operation_id,
            operation_type=operation_type,
            description=description,
            timeout=timeout,
            cancellation_token=cancellation_token,
            metadata=metadata or {},
        )

        # Track the operation
        self._active_operations[operation_id] = context

        try:
            # Check if timeouts are enabled
            if not self.timeout_config.enable_timeouts:
                # Execute without timeout
                context.status = OperationStatus.RUNNING
                result = await operation(*args, **kwargs)
                context.status = OperationStatus.COMPLETED
                context.result = result

                return AsyncOperationResult(
                    operation_id=operation_id,
                    status=OperationStatus.COMPLETED,
                    result=result,
                    elapsed_time=context.elapsed_time,
                )

            # Execute with timeout and cancellation handling
            context.status = OperationStatus.RUNNING

            # Create task for the operation with exception safety
            task = None
            try:
                task = asyncio.create_task(operation(*args, **kwargs))

                # Register task with cancellation token if provided
                if cancellation_token:
                    cancellation_token.register_task(task)

                # Register with global cancellation token
                self._global_cancellation_token.register_task(task)

            except Exception:
                # If registration fails, ensure task is still registered with global token
                # to prevent orphaned tasks
                if task is not None:
                    try:
                        self._global_cancellation_token.register_task(task)
                    except Exception:
                        # Suppress registration errors during cleanup
                        pass
                # Re-raise the original exception
                raise

            try:
                # Wait for operation with timeout
                result = await asyncio.wait_for(task, timeout=timeout)

                context.status = OperationStatus.COMPLETED
                context.result = result

                return AsyncOperationResult(
                    operation_id=operation_id,
                    status=OperationStatus.COMPLETED,
                    result=result,
                    elapsed_time=context.elapsed_time,
                )

            except asyncio.TimeoutError:
                context.status = OperationStatus.TIMEOUT
                context.error = OperationTimeoutError(
                    f"Operation '{description}' timed out after {timeout}s", timeout, operation_id
                )

                return AsyncOperationResult(
                    operation_id=operation_id,
                    status=OperationStatus.TIMEOUT,
                    error=str(context.error),
                    elapsed_time=context.elapsed_time,
                    was_timeout=True,
                )

            except asyncio.CancelledError:
                context.status = OperationStatus.CANCELLED
                context.error = CancellationError(
                    f"Operation '{description}' was cancelled", operation_id
                )

                return AsyncOperationResult(
                    operation_id=operation_id,
                    status=OperationStatus.CANCELLED,
                    error=str(context.error),
                    elapsed_time=context.elapsed_time,
                    was_cancelled=True,
                )

        except Exception as e:
            context.status = OperationStatus.FAILED
            context.error = str(e)

            return AsyncOperationResult(
                operation_id=operation_id,
                status=OperationStatus.FAILED,
                error=str(e),
                elapsed_time=context.elapsed_time,
            )

        finally:
            # Clean up operation tracking - suppress exceptions to avoid masking original errors
            try:
                self._active_operations.pop(operation_id, None)
            except Exception:
                # Suppress cleanup errors to prevent masking original exceptions
                pass

    def _get_default_timeout(self, operation_type: str) -> float:
        """Get default timeout for an operation type."""
        timeout_map = {
            "config_load": self.timeout_config.config_load_timeout,
            "secrets_operation": self.timeout_config.secrets_operation_timeout,
            "service_startup": self.timeout_config.service_startup_timeout,
            "overlord_startup": self.timeout_config.overlord_startup_timeout,
            "cleanup": self.timeout_config.cleanup_timeout,
        }

        return timeout_map.get(operation_type, self.timeout_config.default_timeout)

    def create_cancellation_token(self) -> CancellationToken:
        """Create a new cancellation token."""
        return CancellationToken(self.timeout_config.cancellation_grace_period)

    def get_active_operations(self) -> List[OperationContext]:
        """Get list of currently active operations."""
        return list(self._active_operations.values())

    def get_operation_status(self, operation_id: str) -> Optional[OperationContext]:
        """Get status of a specific operation."""
        return self._active_operations.get(operation_id)

    def cancel_operation(self, operation_id: str) -> bool:
        """
        Cancel a specific operation.

        Args:
            operation_id: ID of the operation to cancel

        Returns:
            True if operation was found and cancelled, False otherwise
        """
        context = self._active_operations.get(operation_id)
        if context and context.cancellation_token:
            context.cancellation_token.cancel()
            return True
        return False

    def cancel_all_operations(self) -> None:
        """Cancel all active operations."""
        self._global_cancellation_token.cancel()

        # Cancel individual operation tokens as well
        for context in self._active_operations.values():
            if context.cancellation_token:
                context.cancellation_token.cancel()

    async def shutdown(self, timeout: Optional[float] = None) -> None:
        """
        Shutdown the operation manager gracefully.

        Args:
            timeout: Maximum time to wait for operations to complete
        """
        if not self._active_operations:
            return

        shutdown_timeout = timeout or self.timeout_config.cleanup_timeout

        try:
            # Give operations a chance to complete gracefully
            await asyncio.wait_for(self._wait_for_operations_completion(), timeout=shutdown_timeout)
        except asyncio.TimeoutError:
            # Force cancel all operations if they don't complete in time
            self.cancel_all_operations()

            # Wait a bit more for cancellation to take effect
            try:
                await asyncio.wait_for(
                    self._wait_for_operations_completion(),
                    timeout=self.timeout_config.cancellation_grace_period,
                )
            except asyncio.TimeoutError:
                # Operations didn't cancel gracefully, they'll be cleaned up by garbage collection
                pass

    async def _wait_for_operations_completion(self) -> None:
        """Wait for all active operations to complete."""
        while self._active_operations:
            await asyncio.sleep(0.1)  # Small delay to avoid busy waiting


# Global instance for Formation use
_global_operation_manager: Optional[AsyncOperationManager] = None


def get_operation_manager() -> AsyncOperationManager:
    """Get the global async operation manager instance."""
    global _global_operation_manager
    if _global_operation_manager is None:
        _global_operation_manager = AsyncOperationManager()
    return _global_operation_manager


def set_timeout_config(config: TimeoutConfig) -> None:
    """Set global timeout configuration."""
    global _global_operation_manager
    if _global_operation_manager is None:
        _global_operation_manager = AsyncOperationManager(config)
    else:
        _global_operation_manager.timeout_config = config


async def execute_with_timeout(
    operation: Callable[..., Awaitable[T]],
    operation_type: str,
    description: str,
    timeout: Optional[float] = None,
    cancellation_token: Optional[CancellationToken] = None,
    *args,
    **kwargs,
) -> AsyncOperationResult:
    """
    Convenience function to execute an operation with timeout using the global manager.

    Args:
        operation: The async function to execute
        operation_type: Type of operation
        description: Description of the operation
        timeout: Timeout in seconds
        cancellation_token: Cancellation token
        *args, **kwargs: Arguments for the operation

    Returns:
        AsyncOperationResult with operation status and result
    """
    manager = get_operation_manager()
    return await manager.execute_with_timeout(
        operation, operation_type, description, timeout, cancellation_token, *args, **kwargs
    )
