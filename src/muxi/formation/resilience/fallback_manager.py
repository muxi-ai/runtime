"""
Fallback Management for Resilience Framework.

This module provides fallback mechanisms and graceful degradation
when primary recovery strategies fail.
"""

import asyncio
from typing import Any, Dict, Optional

from ...datatypes.resilience import (
    ErrorType,
    FallbackFunction,
)
from ...datatypes import observability


class FallbackManager:
    """
    Manages fallback mechanisms and graceful degradation strategies
    when primary recovery attempts fail.
    """

    def __init__(self):
        """Initialize the fallback manager."""
        self._fallback_cache: Dict[str, Any] = {}
        self._fallback_functions: Dict[str, FallbackFunction] = {}
        self._simplified_workflows: Dict[str, Dict[str, Any]] = {}

    async def get_fallback_response(
        self, workflow: Any, error_type: ErrorType, context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Get a fallback response for a failed workflow.

        Args:
            workflow: The failed workflow
            error_type: Type of error that occurred
            context: Additional context information

        Returns:
            Fallback response
        """
        try:
            # Try cached response first
            cached_response = await self._get_cached_fallback(workflow, context)
            if cached_response is not None:
                return cached_response

            # Try simplified workflow
            simplified_response = await self._get_simplified_workflow_response(workflow, context)
            if simplified_response is not None:
                return simplified_response

            # Try partial response
            partial_response = await self._get_partial_response(workflow, context)
            if partial_response is not None:
                return partial_response

            # Generate error message as last resort
            error_response = await self._generate_error_message(workflow, error_type, context)
            observability.observe(
                event_type=observability.SystemEvents.CIRCUIT_BREAKER_FALLBACK_TRIGGERED,
                level=observability.EventLevel.WARNING,
                data={
                    "workflow_id": workflow,
                    "error_type": error_type.value,
                    "fallback_strategy": "error_message_generation",
                },
                description=f"Generated error message as final fallback for workflow '{workflow}'",
            )
            return error_response

        except Exception as fallback_error:
            observability.observe(
                event_type=observability.ErrorEvents.FALLBACK_EXECUTION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow,
                    "error_type": error_type.value,
                    "fallback_error": str(fallback_error),
                },
                description=f"Fallback execution failed for workflow '{workflow}': {str(fallback_error)}",
            )
            return self._get_emergency_response(workflow, error_type)

    async def _get_cached_fallback(
        self, workflow: Any, context: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """Try to get a cached response for similar workflow."""
        try:
            # Generate cache key based on workflow characteristics
            cache_key = self._generate_cache_key(workflow, context)

            if cache_key in self._fallback_cache:
                cached_data = self._fallback_cache[cache_key]

                # Check if cached data is still valid (not too old)
                import time

                if time.time() - cached_data.get("timestamp", 0) < 3600:  # 1 hour
                    return cached_data.get("response")

        except Exception as cache_error:
            _ = cache_error  # remove this after implementing observability

        return None

    async def _get_simplified_workflow_response(
        self, workflow: Any, context: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """Generate response using a simplified version of the workflow."""
        try:
            workflow_type = getattr(workflow, "type", "unknown")

            if workflow_type in self._simplified_workflows:
                simplified_config = self._simplified_workflows[workflow_type]

                # Create simplified response based on configuration
                return await self._execute_simplified_workflow(workflow, simplified_config, context)

        except Exception as simplification_error:
            _ = simplification_error  # remove this after implementing observability

        return None

    async def _get_partial_response(
        self, workflow: Any, context: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """Generate a partial response based on completed tasks."""
        try:
            # Check if workflow has any completed tasks
            completed_tasks = getattr(workflow, "completed_tasks", [])

            if completed_tasks:
                # Synthesize response from completed tasks
                partial_content = []

                for task in completed_tasks:
                    if hasattr(task, "result") and task.result:
                        partial_content.append(task.result)

                if partial_content:
                    return {
                        "type": "partial_response",
                        "content": partial_content,
                        "status": "incomplete",
                        "message": "This is a partial response due to workflow interruption.",
                        "completed_tasks": len(completed_tasks),
                        "total_tasks": getattr(workflow, "total_tasks", len(completed_tasks)),
                    }

        except Exception as partial_error:
            _ = partial_error  # remove this after implementing observability

        return None

    async def _generate_error_message(
        self, workflow: Any, error_type: ErrorType, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate a user-friendly error message."""

        # Error message templates
        error_messages = {
            ErrorType.NETWORK_TIMEOUT: "I'm experiencing network connectivity issues. Please try again in a moment.",  # noqa: E501
            ErrorType.AGENT_UNAVAILABLE: "The required service is temporarily unavailable. Please try again later.",  # noqa: E501
            ErrorType.LLM_RATE_LIMITED: "I'm currently experiencing high demand. Please wait a moment and try again.",  # noqa: E501
            ErrorType.MEMORY_FULL: "I'm running low on resources. Please try a simpler request.",  # noqa: E501
            ErrorType.AUTH_FAILED: "There's an authentication issue. Please check your credentials.",  # noqa: E501
            ErrorType.SYSTEM_OVERLOAD: "The system is currently overloaded. Please try again in a few minutes.",  # noqa: E501
            ErrorType.CONFIGURATION_ERROR: "There's a configuration issue. Please contact support.",  # noqa: E501
        }

        user_message = error_messages.get(
            error_type,
            "I encountered an unexpected issue while processing your request. Please try again.",
        )

        return {
            "type": "error_response",
            "message": user_message,
            "error_type": error_type.value,
            "workflow_id": getattr(workflow, "id", None),
            "timestamp": asyncio.get_event_loop().time(),
            "support_available": True,
        }

    def _get_emergency_response(self, workflow: Any, error_type: ErrorType) -> Dict[str, Any]:
        """Generate an emergency response when all fallbacks fail."""
        return {
            "type": "emergency_response",
            "message": "I apologize, but I'm unable to process your request at this time. Please try again later or contact support.",  # noqa: E501
            "error_type": error_type.value,
            "workflow_id": getattr(workflow, "id", None),
            "status": "system_error",
        }

    def _generate_cache_key(self, workflow: Any, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate a cache key for workflow fallback lookup."""
        import hashlib

        # Create key from workflow characteristics
        key_components = [
            getattr(workflow, "type", "unknown"),
            str(getattr(workflow, "complexity", 0)),
            str(getattr(workflow, "agent_count", 0)),
        ]

        if context:
            key_components.append(str(sorted(context.items())))

        key_string = "|".join(key_components)
        return hashlib.md5(key_string.encode()).hexdigest()

    async def _execute_simplified_workflow(
        self,
        workflow: Any,
        simplified_config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a simplified version of the workflow."""

        # This is a placeholder implementation
        # In a real system, this would execute a simplified workflow

        return {
            "type": "simplified_response",
            "content": simplified_config.get("default_response", "Simplified response generated"),
            "original_workflow": getattr(workflow, "id", None),
            "simplification_applied": True,
            "message": "This response was generated using a simplified approach due to system constraints.",  # noqa: E501
        }

    def cache_successful_response(
        self, workflow: Any, response: Any, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Cache a successful response for future fallback use."""
        try:
            cache_key = self._generate_cache_key(workflow, context)

            import time

            self._fallback_cache[cache_key] = {
                "response": response,
                "timestamp": time.time(),
                "workflow_type": getattr(workflow, "type", "unknown"),
                "context": context,
            }

            # Limit cache size
            if len(self._fallback_cache) > 1000:
                # Remove oldest entries
                sorted_items = sorted(
                    self._fallback_cache.items(), key=lambda x: x[1].get("timestamp", 0)
                )

                # Keep only the newest 800 entries
                self._fallback_cache = dict(sorted_items[-800:])

        except Exception as cache_error:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "component": "fallback_manager",
                    "operation": "cache_cleanup",
                    "error": str(cache_error),
                },
                description=f"Fallback cache cleanup failed: {str(cache_error)}",
            )

    def register_fallback_function(self, name: str, function: FallbackFunction) -> None:
        """Register a custom fallback function."""
        self._fallback_functions[name] = function

    def register_simplified_workflow(self, workflow_type: str, config: Dict[str, Any]) -> None:
        """Register a simplified workflow configuration."""
        self._simplified_workflows[workflow_type] = config

    def clear_cache(self) -> None:
        """Clear the fallback cache."""
        self._fallback_cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get fallback cache statistics."""
        return {
            "cache_size": len(self._fallback_cache),
            "registered_functions": len(self._fallback_functions),
            "simplified_workflows": len(self._simplified_workflows),
        }
