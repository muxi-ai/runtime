"""
Resilient Workflow Executor - Integrates resilience framework with workflow execution.

This module wraps the WorkflowExecutor with resilience capabilities, providing
better error handling, recovery strategies, and user-friendly error messages.
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from ...datatypes.workflow import (
    Workflow,
    SubTask,
    TaskStatus,
    TaskResult,
)
from ...datatypes.resilience import (
    ErrorType,
    ErrorSeverity,
    ResilienceConfig,
    ErrorContext,
)

from ..agents.agent import Agent
from ..resilience import (
    ErrorClassifier,
    FallbackManager,
    RecoveryStrategist,
)
from .executor import WorkflowExecutor
from .config import WorkflowConfig


class ResilientWorkflowExecutor(WorkflowExecutor):
    """
    Enhanced WorkflowExecutor with resilience capabilities.

    Provides better error handling, recovery strategies, and user-friendly
    error messages when MCP tools or other components fail.
    """

    def __init__(self, agent_registry: Dict[str, Agent], config: Optional[WorkflowConfig] = None):
        """Initialize with resilience components."""
        super().__init__(agent_registry, config)

        # Initialize resilience components
        self.error_classifier = ErrorClassifier()
        self.fallback_manager = FallbackManager()
        self.recovery_strategist = RecoveryStrategist(ResilienceConfig())

        # Track error history for better messages
        self.error_history: Dict[str, List[Dict[str, Any]]] = {}

    async def _execute_task_with_agent(
        self, task: SubTask, agent: Agent, context: Dict[str, Any]
    ) -> TaskResult:
        """
        Execute task with resilience and better error messages.

        This method integrates with the parent's retry logic while adding
        better error classification and user-friendly messages.
        """
        task_description = task.description
        agent_name = getattr(agent, 'name', agent.agent_id)

        # Check if we're in a retry attempt (parent class tracks this)
        retry_count = len(self.error_history.get(task.id, []))

        # Pass retry count to context for agents to be aware
        if retry_count > 0:
            context = context.copy() if context else {}
            context['retry_attempt'] = retry_count + 1

        try:
            # Let parent handle the execution with its retry logic
            # This will use the WorkflowErrorHandler configured retry settings
            result = await super()._execute_task_with_agent(task, agent, context)

            # Clear error history on success
            if task.id in self.error_history:
                del self.error_history[task.id]

            return result

        except Exception as e:
            # Only handle the final error after retries are exhausted
            # Check if parent's retry logic is done
            if hasattr(self, 'error_handler') and self.error_handler:
                error_action = await self.error_handler.handle_task_error(
                    task.id, e, context
                )

                # If parent says to retry, let it handle that
                if error_action.get("action") in ["retry", "retry_alternate"]:
                    raise  # Re-raise to let parent handle retry

            # If we get here, retries are exhausted or not configured
            # Now provide user-friendly error messages
            # Classify the error
            error_info = await self._classify_error(e, task, agent)
            error_type = error_info['type']
            error_severity = error_info['severity']

            # Track error history
            if task.id not in self.error_history:
                self.error_history[task.id] = []
            self.error_history[task.id].append({
                'error': str(e),
                'type': error_type,
                'severity': error_severity,
                'timestamp': datetime.now(),
                'agent': agent_name,
                'retry_count': len(self.error_history[task.id]) + 1,
            })

            # Get recovery strategy
            current_retry_count = len(self.error_history.get(task.id, []))
            error_context = ErrorContext(
                error=e,
                error_type=error_type,
                severity=error_severity,
                task_id=task.id,
                agent_id=agent.agent_id if agent else None,
                attempt_count=current_retry_count + 1,
                context_data={
                    'task': task_description,
                    'agent': agent_name,
                    'has_alternatives': len(self.agent_registry) > 1,
                    'retry_count': current_retry_count,
                }
            )
            recovery_strategy = await self.recovery_strategist.select_strategy(error_context)

            # Apply recovery strategy
            recovery_result = await self._apply_recovery_strategy(
                task, agent, context, error_info, recovery_strategy
            )

            if recovery_result:
                return recovery_result

            # If recovery failed, create user-friendly error result
            return await self._create_error_result(task, error_info)

    async def _classify_error(self, error: Exception, task: SubTask, agent: Agent) -> Dict[str, Any]:
        """Classify the error for appropriate handling."""
        error_str = str(error).lower()
        error_type_name = type(error).__name__

        # Check for specific exception types first
        if isinstance(error, TimeoutError) or isinstance(error, asyncio.TimeoutError):
            return {
                'type': ErrorType.NETWORK_TIMEOUT,
                'severity': ErrorSeverity.MEDIUM,
                'message': f"The {task.description} operation timed out.",
                'details': f"Timeout while {task.description}",
                'retry_count': len(self.error_history.get(task.id, [])),
            }

        # Connection errors
        if isinstance(error, (ConnectionError, OSError)):
            # Check for connection refused error codes
            if hasattr(error, 'errno') and error.errno in [111, 10061]:  # Connection refused
                return {
                    'type': ErrorType.NETWORK_TIMEOUT,
                    'severity': ErrorSeverity.MEDIUM,
                    'message': f"Unable to connect to the service needed for {task.description}.",
                    'details': "Connection refused",
                    'retry_count': len(self.error_history.get(task.id, [])),
                }
            # General connection error
            return {
                'type': ErrorType.NETWORK_TIMEOUT,
                'severity': ErrorSeverity.MEDIUM,
                'message': f"Network error while {task.description}.",
                'details': f"Connection error: {error_type_name}",
                'retry_count': len(self.error_history.get(task.id, [])),
            }

        # HTTP-specific errors (if using httpx or requests)
        if error_type_name in ['HTTPStatusError', 'HTTPError']:
            if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
                status_code = error.response.status_code
                if status_code == 401:
                    return {
                        'type': ErrorType.AUTH_FAILED,
                        'severity': ErrorSeverity.CRITICAL,
                        'message': f"Authentication failed for {task.description}.",
                        'details': "HTTP 401 Unauthorized",
                        'retry_count': len(self.error_history.get(task.id, [])),
                    }
                elif status_code == 404:
                    return {
                        'type': ErrorType.AGENT_UNAVAILABLE,
                        'severity': ErrorSeverity.MEDIUM,
                        'message': f"The resource required for {task.description} was not found.",
                        'details': "HTTP 404 Not Found",
                        'retry_count': len(self.error_history.get(task.id, [])),
                    }
                elif status_code == 429:
                    return {
                        'type': ErrorType.LLM_RATE_LIMITED,
                        'severity': ErrorSeverity.MEDIUM,
                        'message': "Rate limit exceeded. Waiting before retry.",
                        'details': "HTTP 429 Too Many Requests",
                        'retry_count': len(self.error_history.get(task.id, [])),
                    }

        # MCP tool errors (string matching as fallback)
        if 'mcp' in error_str or 'tool' in error_str:
            if 'timeout' in error_str:
                return {
                    'type': ErrorType.NETWORK_TIMEOUT,
                    'severity': ErrorSeverity.MEDIUM,
                    'message': f"The {task.description} tool is taking longer than expected to respond.",
                    'details': f"Tool timeout while {task.description}",
                    'retry_count': len(self.error_history.get(task.id, [])),
                }
            elif 'connection' in error_str or 'network' in error_str:
                return {
                    'type': ErrorType.NETWORK_TIMEOUT,
                    'severity': ErrorSeverity.MEDIUM,
                    'message': f"Unable to connect to the tool needed for {task.description}.",
                    'details': "Network connectivity issue",
                    'retry_count': len(self.error_history.get(task.id, [])),
                }
            elif 'not found' in error_str or '404' in error_str:
                return {
                    'type': ErrorType.AGENT_UNAVAILABLE,
                    'severity': ErrorSeverity.MEDIUM,
                    'message': f"The tool required for {task.description} is not available.",
                    'details': "Tool not found",
                    'retry_count': len(self.error_history.get(task.id, [])),
                }
            else:
                return {
                    'type': ErrorType.CONFIGURATION_ERROR,
                    'severity': ErrorSeverity.LOW,
                    'message': f"There was an issue with the tool configuration for {task.description}.",
                    'details': f"MCP error: {error_str}",
                    'retry_count': len(self.error_history.get(task.id, [])),
                }

        # API/LLM errors
        elif 'rate limit' in error_str or 'quota' in error_str:
            return {
                'type': ErrorType.LLM_RATE_LIMITED,
                'severity': ErrorSeverity.MEDIUM,
                'message': "I'm experiencing high demand. Let me try a different approach.",
                'details': "API rate limit reached",
                'retry_count': len(self.error_history.get(task.id, [])),
            }

        # Authentication errors
        elif 'auth' in error_str or 'unauthorized' in error_str or '401' in error_str:
            return {
                'type': ErrorType.AUTH_FAILED,
                'severity': ErrorSeverity.CRITICAL,
                'message': f"I don't have the proper credentials to complete {task.description}.",
                'details': "Authentication failure",
                'retry_count': len(self.error_history.get(task.id, [])),
            }

        # Default classification
        else:
            return {
                'type': ErrorType.UNKNOWN,
                'severity': ErrorSeverity.LOW,
                'message': f"I encountered an issue while {task.description}.",
                'details': f"{error_type_name}: {error_str}",
                'retry_count': len(self.error_history.get(task.id, [])),
            }

    async def _apply_recovery_strategy(
        self,
        task: SubTask,
        agent: Agent,
        context: Dict[str, Any],
        error_info: Dict[str, Any],
        recovery_strategy: Any
    ) -> Optional[TaskResult]:
        """Apply recovery strategy based on error type."""

        # For recoverable errors, try alternative approaches
        if error_info['severity'] == ErrorSeverity.MEDIUM:
            # Adjust strategy based on retry count
            retry_count = error_info.get('retry_count', 0)

            # Try without tools if it was a tool error
            if error_info['type'] == ErrorType.NETWORK_TIMEOUT:
                # Only try fallback after at least one retry, or immediately if retry count >= 2
                should_fallback = retry_count >= 1

                if should_fallback:
                    # Create modified context without tool usage
                    no_tool_context = context.copy()
                    no_tool_context['skip_tools'] = True
                    no_tool_context['fallback_mode'] = True
                    no_tool_context['retry_info'] = {
                        'retry_count': retry_count,
                        'reason': 'tool_timeout'
                    }

                    # Add explanation to prompt
                    task_prompt = self._create_task_prompt(task, no_tool_context)
                    fallback_prompt = (
                        f"{task_prompt}\n\n"
                        "Note: External tools are unavailable"
                        f"{' after ' + str(retry_count) + ' attempts' if retry_count > 0 else ''}. "
                        "Please provide the best response you can based on your knowledge, "
                        "and mention any limitations."
                    )

                    try:
                        # Execute without tools
                        response = await agent.process_message(
                            fallback_prompt,
                            context=no_tool_context,
                            user_id=context.get('user_id'),
                            session_id=context.get('session_id'),
                        )

                        # Create result with explanation - wrap in proper TaskOutput structure
                        fallback_output = {
                            'result': {
                                'content': response.content if hasattr(response, 'content') else str(response),
                                'fallback_used': True,
                                'limitation_note': (
                                    f"Note: This response was generated without access to external tools "
                                    f"{f'after {retry_count} failed attempts ' if retry_count > 0 else ''}"
                                    f"due to connectivity issues. Some specific details may be limited."
                                ),
                                'retry_count': retry_count,
                            },
                            'status': 'success',
                        }

                        outputs = {
                            'response': fallback_output
                        }

                        return TaskResult(
                            task_id=task.id,
                            status=TaskStatus.DONE,
                            outputs=outputs,
                            execution_time=0.0,
                        )

                    except Exception:
                        # Fallback also failed
                        pass

        return None

    async def _create_error_result(
        self, task: SubTask, error_info: Dict[str, Any]
    ) -> TaskResult:
        """Create a user-friendly error result."""

        # Get error history for this task
        error_count = len(self.error_history.get(task.id, []))

        # Build user-friendly message with retry information
        if error_count > 2:
            user_message = (
                f"I've tried {error_count} times but am unable to {task.description}. "
                f"{error_info['message']} "
                f"You might want to try this request later or use a different approach."
            )
        elif error_count > 0:
            user_message = (
                f"{error_info['message']} (Attempt {error_count} of {getattr(self.config.retry_config, 'max_attempts', 3)}). "  # noqa: E501
                f"Let me continue with what I can do."
            )
        else:
            user_message = f"{error_info['message']} Let me continue with what I can do."

        # Create result with explanation - wrap in proper TaskOutput structure
        error_output = {
            'result': {
                'error': True,
                'error_type': error_info['type'].value,
                'user_message': user_message,
                'task_attempted': task.description,
                'recovery_attempted': error_count > 1,
                'retry_count': error_count,
            },
            'status': 'failure',
            'error': user_message,
        }

        # For critical errors, include more details
        if error_info['severity'] == ErrorSeverity.CRITICAL:
            error_output['result']['requires_action'] = True
            error_output['result']['suggested_action'] = self._get_suggested_action(error_info['type'])

        # Wrap in outputs dict with a key
        outputs = {
            'error_details': error_output
        }

        return TaskResult(
            task_id=task.id,
            status=TaskStatus.FAILED,
            outputs=outputs,
            error_message=user_message,
            execution_time=0.0,
        )

    def _get_suggested_action(self, error_type: ErrorType) -> str:
        """Get suggested user action for critical errors."""
        suggestions = {
            ErrorType.AUTH_FAILED: (
                "Please check that the required credentials are configured correctly."
            ),
            ErrorType.CONFIGURATION_ERROR: (
                "This appears to be a configuration issue. Please contact support."
            ),
            ErrorType.MEMORY_FULL: (
                "Try breaking down your request into smaller parts."
            ),
        }

        return suggestions.get(
            error_type,
            "Please try again later or contact support if the issue persists."
        )

    async def execute_workflow(
        self, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> Workflow:
        """
        Execute workflow with enhanced error handling.

        Tracks errors across the workflow and provides comprehensive
        error summaries if multiple tasks fail.
        """
        # Execute with parent method
        result = await super().execute_workflow(workflow, context)

        # Check if we had failures and add summary
        failed_tasks = [
            task for task in result.tasks.values()
            if task.status == TaskStatus.FAILED
        ]

        if failed_tasks and hasattr(result, 'error_summary'):
            # Build comprehensive error summary
            error_summary = []

            for task in failed_tasks:
                if task.id in self.error_history:
                    task_errors = self.error_history[task.id]
                    error_summary.append({
                        'task': task.description,
                        'attempts': len(task_errors),
                        'errors': [e['type'].value for e in task_errors],
                        'final_message': task.error_message,
                        'retry_details': [
                            {
                                'attempt': e.get('retry_count', i + 1),
                                'error_type': e['type'].value,
                                'timestamp': e['timestamp'].isoformat() if 'timestamp' in e else None
                            }
                            for i, e in enumerate(task_errors)
                        ]
                    })

            result.error_summary = error_summary

        # Clear error history for this workflow's tasks only
        for task_id in result.tasks.keys():
            if task_id in self.error_history:
                del self.error_history[task_id]

        return result
