"""
Formation Exception Hierarchy

Provides specific exception types for different Formation operations to enable
better error handling, debugging, and user experience.
"""

from typing import Optional, Dict, Any, List


# Base Formation Exception
class FormationError(Exception):
    """Base exception for all Formation-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


# Configuration Errors
class FormationConfigurationError(FormationError):
    """Base class for configuration-related errors."""

    pass


class ConfigurationNotFoundError(FormationConfigurationError):
    """Raised when formation configuration file/directory cannot be found."""

    def __init__(self, path: str, details: Optional[Dict[str, Any]] = None):
        message = f"Formation configuration not found: {path}"
        super().__init__(message, details)
        self.path = path


class ConfigurationValidationError(FormationConfigurationError):
    """Raised when formation configuration fails validation."""

    def __init__(self, errors: List[str], details: Optional[Dict[str, Any]] = None):
        message = f"Configuration validation failed: {'; '.join(errors)}"
        super().__init__(message, details)
        self.validation_errors = errors


class ConfigurationLoadError(FormationConfigurationError):
    """Raised when formation configuration cannot be loaded."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        # Extract path from details if available for backward compatibility
        self.path = details.get("config_path") if details else None


# Service Errors
class FormationServiceError(FormationError):
    """Base class for service-related errors."""

    pass


class ServiceConfigurationError(FormationServiceError):
    """Raised when service configuration is invalid."""

    def __init__(self, service_name: str, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Invalid {service_name} service configuration: {reason}"
        super().__init__(message, details)
        self.service_name = service_name
        self.reason = reason


class ServiceStartupError(FormationServiceError):
    """Raised when a service fails to start."""

    def __init__(self, service_name: str, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Failed to start {service_name} service: {reason}"
        super().__init__(message, details)
        self.service_name = service_name
        self.reason = reason


class ServiceDependencyError(FormationServiceError):
    """Raised when service dependencies are not met."""

    def __init__(
        self,
        service_name: str,
        missing_dependencies: List[str],
        details: Optional[Dict[str, Any]] = None,
    ):
        deps = ", ".join(missing_dependencies)
        message = f"Service {service_name} missing dependencies: {deps}"
        super().__init__(message, details)
        self.service_name = service_name
        self.missing_dependencies = missing_dependencies


class UnsupportedServiceError(FormationServiceError):
    """
    Raised when user requests a service not configured in the formation.

    This error is raised when a user tries to use a service (e.g., "show my repos")
    but that service is not configured in the formation's MCP servers.
    """

    def __init__(self, service_name: str, details: Optional[Dict[str, Any]] = None):
        message = f"Service '{service_name}' is not configured in this formation"
        # Create a new dict with the service name, preserving any existing details
        if details is None:
            merged_details = {"service": service_name}
        else:
            # Create a shallow copy to avoid mutating the caller's dict
            merged_details = dict(details)
            merged_details["service"] = service_name
        super().__init__(message, merged_details)
        self.service_name = service_name


# Overlord Errors
class OverlordError(FormationError):
    """Base class for overlord-related errors."""

    pass


class OverlordImportError(OverlordError):
    """Raised when Overlord class cannot be imported."""

    def __init__(self, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Failed to import Overlord class: {reason}"
        super().__init__(message, details)
        self.reason = reason


class OverlordStartupError(OverlordError):
    """Raised when overlord fails to start."""

    def __init__(self, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Failed to start overlord: {reason}"
        super().__init__(message, details)
        self.reason = reason


class RegistryConfigurationError(OverlordStartupError):
    """Raised when registry requirements are not met according to startup policy."""

    def __init__(self, policy: str, unreachable_registries: List[str]):
        self.policy = policy
        self.unreachable_registries = unreachable_registries
        reason = f"Required registries are unreachable (policy: {policy})"

        # Create user-friendly message
        error_lines = [
            "\n" + "=" * 60,
            "⚠️  FORMATION STARTUP FAILED",
            "=" * 60,
            "",
            f"Policy: {policy.upper()}",
            "Required registries are unreachable:",
            "",
        ]

        for registry in unreachable_registries:
            error_lines.append(f"  ❌ {registry}")

        error_lines.extend(
            [
                "",
                "To resolve this issue, you can:",
                "  1. Start the registry server(s) listed above",
                "  2. Change startup_policy to 'lenient' in formation.afs",
                "  3. Remove the unreachable registries from configuration",
                "",
                "=" * 60,
            ]
        )

        self.user_message = "\n".join(error_lines)

        details = {
            "policy": policy,
            "unreachable_registries": unreachable_registries,
            "user_message": self.user_message,
        }

        super().__init__(reason, details)


class OverlordStateError(OverlordError):
    """Raised when overlord is in an invalid state for the requested operation."""

    def __init__(
        self, current_state: str, required_state: str, details: Optional[Dict[str, Any]] = None
    ):
        message = f"Overlord in {current_state} state, but {required_state} required"
        super().__init__(message, details)
        self.current_state = current_state
        self.required_state = required_state


# Agent Errors
class AgentError(FormationError):
    """Base class for agent-related errors."""

    pass


class AgentConfigurationError(AgentError):
    """Raised when agent configuration is invalid."""

    def __init__(self, agent_id: str, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Invalid configuration for agent '{agent_id}': {reason}"
        super().__init__(message, details)
        self.agent_id = agent_id
        self.reason = reason


class DuplicateAgentError(AgentError):
    """Raised when duplicate agent IDs are found."""

    def __init__(
        self, agent_id: str, positions: List[int], details: Optional[Dict[str, Any]] = None
    ):
        pos_str = ", ".join(map(str, positions))
        message = f"Duplicate agent ID '{agent_id}' found at positions: {pos_str}"
        super().__init__(message, details)
        self.agent_id = agent_id
        self.positions = positions


class AgentValidationError(AgentError):
    """Raised when agent validation fails."""

    def __init__(
        self, agent_id: str, validation_errors: List[str], details: Optional[Dict[str, Any]] = None
    ):
        errors_str = "; ".join(validation_errors)
        message = f"Agent '{agent_id}' validation failed: {errors_str}"
        super().__init__(message, details)
        self.agent_id = agent_id
        self.validation_errors = validation_errors


# Agent Management Errors
class AgentNotFoundError(AgentError):
    """Raised when attempting to operate on a non-existent agent."""

    def __init__(self, agent_id: str, details: Optional[Dict[str, Any]] = None):
        message = f"Agent '{agent_id}' not found"
        super().__init__(message, details)
        self.agent_id = agent_id


class AgentHasDependentsError(AgentError):
    """Raised when attempting to remove an agent that has dependent agents."""

    def __init__(
        self, agent_id: str, dependent_agents: List[str], details: Optional[Dict[str, Any]] = None
    ):
        deps_str = ", ".join(dependent_agents)
        message = f"Cannot remove agent '{agent_id}' - other agents depend on it: {deps_str}"
        super().__init__(message, details)
        self.agent_id = agent_id
        self.dependent_agents = dependent_agents


class OverlordShuttingDownError(OverlordError):
    """Raised when overlord is shutting down and cannot accept new requests."""

    def __init__(self, details: Optional[Dict[str, Any]] = None):
        message = "Overlord is shutting down - not accepting new requests"
        super().__init__(message, details)


class NoAvailableAgentsError(OverlordError):
    """Raised when no agents are available to handle requests."""

    def __init__(
        self, reason: str = "No agents available", details: Optional[Dict[str, Any]] = None
    ):
        message = f"No available agents: {reason}"
        super().__init__(message, details)
        self.reason = reason


class FormationNotRunningError(OverlordError):
    """Raised when attempting to operate on a formation that is not running."""

    def __init__(self, operation: str, details: Optional[Dict[str, Any]] = None):
        message = f"Formation not running - cannot perform operation: {operation}"
        super().__init__(message, details)
        self.operation = operation


# Secrets Management Errors
class SecretsError(FormationError):
    """Base class for secrets management errors."""

    pass


class SecretsManagerNotAvailableError(SecretsError):
    """Raised when secrets manager is not available or initialized."""

    def __init__(self, details: Optional[Dict[str, Any]] = None):
        message = "Secrets manager not available or failed to initialize"
        super().__init__(message, details)


class SecretNotFoundError(SecretsError):
    """Raised when a requested secret is not found."""

    def __init__(self, secret_name: str, details: Optional[Dict[str, Any]] = None):
        message = f"Secret '{secret_name}' not found"
        super().__init__(message, details)
        self.secret_name = secret_name


class SecretPermissionError(SecretsError):
    """Raised when permission is denied for secret operations."""

    def __init__(self, operation: str, secret_name: str, details: Optional[Dict[str, Any]] = None):
        message = f"Permission denied for {operation} operation on secret '{secret_name}'"
        super().__init__(message, details)
        self.operation = operation
        self.secret_name = secret_name


class SecretsManagementError(SecretsError):
    """Raised when general secrets management operations fail."""

    def __init__(self, operation: str, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Secrets management {operation} failed: {reason}"
        super().__init__(message, details)
        self.operation = operation
        self.reason = reason


# Resource Management Errors
class ResourceError(FormationError):
    """Base class for resource management errors."""

    pass


class ResourceCleanupError(ResourceError):
    """Raised when resource cleanup fails."""

    def __init__(self, resource_type: str, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Failed to cleanup {resource_type} resources: {reason}"
        super().__init__(message, details)
        self.resource_type = resource_type
        self.reason = reason


class ResourceNotAvailableError(ResourceError):
    """Raised when a required resource is not available."""

    def __init__(self, resource_name: str, details: Optional[Dict[str, Any]] = None):
        message = f"Required resource not available: {resource_name}"
        super().__init__(message, details)
        self.resource_name = resource_name


# Dependency Errors
class DependencyError(FormationError):
    """Base class for dependency-related errors."""

    pass


class CircularDependencyError(DependencyError):
    """Raised when circular dependencies are detected."""

    def __init__(self, dependency_chain: List[str], details: Optional[Dict[str, Any]] = None):
        chain_str = " -> ".join(dependency_chain)
        message = f"Circular dependency detected: {chain_str}"
        super().__init__(message, details)
        self.dependency_chain = dependency_chain


class MissingDependencyError(DependencyError):
    """Raised when required dependencies are missing."""

    def __init__(
        self, dependent: str, missing_deps: List[str], details: Optional[Dict[str, Any]] = None
    ):
        deps_str = ", ".join(missing_deps)
        message = f"'{dependent}' requires missing dependencies: {deps_str}"
        super().__init__(message, details)
        self.dependent = dependent
        self.missing_dependencies = missing_deps


class DependencyValidationError(DependencyError):
    """Raised when dependency validation fails."""

    def __init__(self, validation_errors: List[str], details: Optional[Dict[str, Any]] = None):
        message = f"Dependency validation failed: {'; '.join(validation_errors)}"
        super().__init__(message, details)
        self.validation_errors = validation_errors


# MCP Errors
class MCPError(FormationError):
    """Base class for MCP-related errors."""

    pass


class MCPRequestError(MCPError):
    """Raised when MCP request fails."""

    def __init__(
        self,
        message: str,
        method: str = None,
        server_id: str = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.method = method
        self.server_id = server_id


class MCPConnectionError(MCPError):
    """Raised when MCP connection fails."""

    def __init__(self, server_id: str, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Failed to connect to MCP server '{server_id}': {reason}"
        super().__init__(message, details)
        self.server_id = server_id
        self.reason = reason


class MCPToolError(MCPError):
    """Raised when MCP tool execution fails."""

    def __init__(
        self,
        tool_name: str,
        reason: str,
        server_id: str = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"MCP tool '{tool_name}' failed: {reason}"
        if server_id:
            message = f"MCP tool '{tool_name}' on server '{server_id}' failed: {reason}"
        super().__init__(message, details)
        self.tool_name = tool_name
        self.server_id = server_id
        self.reason = reason


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out."""

    def __init__(
        self,
        operation: str,
        timeout: float,
        server_id: str = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"MCP {operation} timed out after {timeout}s"
        if server_id:
            message = f"MCP {operation} on server '{server_id}' timed out after {timeout}s"
        super().__init__(message, details)
        self.operation = operation
        self.timeout = timeout
        self.server_id = server_id


class MCPServerNotFoundError(MCPError):
    """Raised when attempting to operate on a non-existent MCP server."""

    def __init__(self, server_id: str, details: Optional[Dict[str, Any]] = None):
        message = f"MCP server '{server_id}' not found"
        super().__init__(message, details)
        self.server_id = server_id


# Workflow Errors
class WorkflowError(FormationError):
    """Base class for workflow-related errors."""

    pass


class WorkflowTimeoutError(WorkflowError):
    """Raised when workflow execution exceeds maximum allowed time."""

    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        max_timeout: float | None = None,
        elapsed: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.workflow_id = workflow_id
        self.max_timeout = max_timeout
        self.elapsed = elapsed


# Security Errors
class SecurityError(FormationError):
    """Base class for security-related errors."""

    pass


class SecurityViolation(SecurityError):
    """Raised when a security threat is detected in user input."""

    def __init__(
        self,
        reason: str,
        threat_type: str = "unknown",
        message_preview: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"Security violation detected: {reason}"
        super().__init__(message, details)
        self.reason = reason
        self.threat_type = threat_type
        self.message_preview = message_preview


# Utility function for error context
def add_error_context(exception: Exception, context: Dict[str, Any]) -> FormationError:
    """
    Convert a generic exception to a FormationError with additional context.

    Args:
        exception: The original exception
        context: Additional context information

    Returns:
        FormationError with context information
    """
    if isinstance(exception, FormationError):
        # Already a FormationError, just add context
        exception.details.update(context)
        return exception

    # Convert to FormationError with context
    return FormationError(
        message=str(exception),
        details={
            "original_exception": type(exception).__name__,
            "original_message": str(exception),
            **context,
        },
    )
