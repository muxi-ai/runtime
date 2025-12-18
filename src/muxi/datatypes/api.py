"""
API-specific data types for the Formation API.

This module contains enums and types used for API responses,
maintaining consistency with other datatype modules.
"""

from enum import Enum


class APIEventType(str, Enum):
    """Event types for API responses."""

    # Chat events
    CHAT_COMPLETED = "chat.completed"
    CHAT_FAILED = "chat.failed"
    CHAT_STREAMING = "chat.streaming"
    CHAT_ASYNC_ACCEPTED = "chat.async_accepted"

    # Request events (generic request processing)
    REQUEST_PROCESSING = "request.processing"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"

    # Resource events
    AGENT_CREATED = "agent.created"
    AGENT_RETRIEVED = "agent.retrieved"
    AGENT_UPDATED = "agent.updated"
    AGENT_DELETED = "agent.deleted"
    AGENT_LIST = "agent.list"

    SECRET_CREATED = "secret.created"
    SECRET_RETRIEVED = "secret.retrieved"
    SECRET_UPDATED = "secret.updated"
    SECRET_DELETED = "secret.deleted"
    SECRET_LIST = "secret.list"

    MEMORY_CREATED = "memory.created"
    MEMORY_RETRIEVED = "memory.retrieved"
    MEMORY_DELETED = "memory.deleted"
    MEMORY_LIST = "memory.list"
    MEMORY_CONFIG_RETRIEVED = "memory.config.retrieved"
    MEMORY_CONFIG_UPDATED = "memory.config.updated"

    JOB_RETRIEVED = "job.retrieved"
    JOB_DELETED = "job.deleted"
    JOB_LIST = "job.list"

    # Configuration events
    OVERLORD_CONFIG_RETRIEVED = "overlord.config.retrieved"
    OVERLORD_CONFIG_UPDATED = "overlord.config.updated"
    PERSONA_RETRIEVED = "persona.retrieved"
    PERSONA_UPDATED = "persona.updated"
    MCP_DEFAULTS_RETRIEVED = "mcp.defaults.retrieved"
    MCP_DEFAULTS_UPDATED = "mcp.defaults.updated"
    MCP_SERVER_LIST = "mcp.server.list"
    MCP_SERVER_CREATED = "mcp.server.created"
    MCP_SERVER_RETRIEVED = "mcp.server.retrieved"
    MCP_SERVER_UPDATED = "mcp.server.updated"
    MCP_SERVER_DELETED = "mcp.server.deleted"
    MCP_TOOL_LIST = "mcp_tool.list"
    MCP_TOOL_EXECUTED = "mcp_tool.executed"
    LLM_SETTINGS_RETRIEVED = "llm.settings.retrieved"
    LLM_SETTINGS_UPDATED = "llm.settings.updated"
    LLM_RESET = "llm.reset"
    LOGGING_RETRIEVED = "logging.retrieved"
    LOGGING_UPDATED = "logging.updated"
    ASYNC_RETRIEVED = "async.retrieved"
    ASYNC_UPDATED = "async.updated"
    SCHEDULER_RETRIEVED = "scheduler.retrieved"
    SCHEDULER_UPDATED = "scheduler.updated"
    A2A_RETRIEVED = "a2a.retrieved"
    A2A_UPDATED = "a2a.updated"
    FORMATION_CONFIG_RETRIEVED = "formation.config.retrieved"
    FORMATION_STATUS_RETRIEVED = "formation.status.retrieved"

    # Scheduler job events (for scheduled jobs management)
    SCHEDULER_JOBS_LIST = "scheduler.jobs.list"
    SCHEDULER_JOB_CREATED = "scheduler.job.created"
    SCHEDULER_JOB_RETRIEVED = "scheduler.job.retrieved"
    SCHEDULER_JOB_DELETED = "scheduler.job.deleted"

    # Session events
    SESSION_LIST = "session.list"
    SESSION_RETRIEVED = "session.retrieved"
    SESSION_CLEARED = "session.cleared"
    SESSION_DELETED = "session.deleted"
    SESSION_MESSAGES_LIST = "session.messages.list"
    SESSION_RESTORED = "session.restored"

    # User identifier events
    USER_IDENTIFIERS_LIST = "user.identifiers.list"
    USER_IDENTIFIERS_ASSOCIATED = "user.identifiers.associated"
    USER_IDENTIFIER_DELETED = "user.identifier.deleted"
    USER_RESOLVED = "user.resolved"

    # Request status events
    REQUEST_STATUS_RETRIEVED = "request.status.retrieved"
    REQUEST_LIST_RETRIEVED = "request.list.retrieved"
    REQUEST_CANCELLED = "request.cancelled"

    # Logging destination events (for log destination management)
    LOGGING_DESTINATIONS_LIST = "logging.destinations.list"
    LOGGING_DESTINATION_CREATED = "logging.destination.created"
    LOGGING_DESTINATION_UPDATED = "logging.destination.updated"
    LOGGING_DESTINATION_DELETED = "logging.destination.deleted"

    # Buffer memory events
    MEMORY_BUFFER_STATUS = "memory.buffer.status"
    MEMORY_BUFFER_USER_CLEARED = "memory.buffer.user.cleared"
    MEMORY_BUFFER_SESSION_CLEARED = "memory.buffer.session.cleared"

    # Generic list events
    LIST_RETRIEVED = "list.retrieved"

    # Audit events
    AUDIT_RETRIEVED = "audit.retrieved"
    AUDIT_CLEARED = "audit.cleared"

    # SOP events
    SOPS_LIST = "sops.list"
    SOP_RETRIEVED = "sop.retrieved"

    # Trigger events
    TRIGGERS_LIST = "triggers.list"
    TRIGGER_RETRIEVED = "trigger.retrieved"

    # Credential events
    CREDENTIALS_LISTED = "credentials.listed"
    CREDENTIAL_CREATED = "credentials.created"
    CREDENTIAL_RETRIEVED = "credentials.retrieved"
    CREDENTIAL_DELETED = "credentials.deleted"

    # Error events
    ERROR_VALIDATION = "error.validation"
    ERROR_AUTHENTICATION = "error.authentication"
    ERROR_AUTHORIZATION = "error.authorization"
    ERROR_NOT_FOUND = "error.not_found"
    ERROR_INTERNAL = "error.internal"
    ERROR_PROCESSING = "error.processing"

    # Stream events
    STREAM_CONNECTED = "stream.connected"


class APIObjectType(str, Enum):
    """Object types for API responses."""

    CHAT_RESPONSE = "chat_response"
    REQUEST = "request"
    AGENT = "agent"
    AGENT_LIST = "agent_list"
    SECRET = "secret"
    SECRET_LIST = "secret_list"
    MEMORY = "memory"
    MEMORY_LIST = "memory_list"
    MEMORY_CONFIG = "memory_config"
    JOB = "job"
    JOB_LIST = "job_list"
    ERROR = "error"
    EVENT_STREAM = "event_stream"

    # Generic list type for spec compliance
    LIST = "list"

    # Request cancellation
    REQUEST_CANCELLATION = "request_cancellation"

    # Configuration objects
    OVERLORD_CONFIG = "overlord_config"
    PERSONA = "persona"
    MCP_DEFAULTS = "mcp_defaults"
    MCP_SERVER = "mcp_server"
    MCP_SERVER_LIST = "mcp_server_list"
    MCP_TOOL_LIST = "mcp_tool_list"
    MCP_TOOL_RESULT = "mcp_tool_result"
    LLM_SETTINGS = "llm_settings"
    LOGGING = "logging"
    ASYNC = "async"
    SCHEDULER = "scheduler"
    A2A = "a2a"
    STATUS = "status"
    CONFIG = "config"
    FORMATION_STATUS = "formation_status"
    FORMATION_CONFIG = "formation_config"

    # Scheduler job objects (for scheduled jobs management)
    SCHEDULED_JOB = "scheduled_job"
    SCHEDULED_JOB_LIST = "scheduled_job_list"

    # Session objects
    SESSION = "session"
    SESSION_LIST = "session_list"

    # Request status objects
    REQUEST_STATUS = "request_status"
    REQUEST_LIST = "request_list"

    # User identifier objects
    USER = "user"
    USER_IDENTIFIER = "user_identifier"
    USER_IDENTIFIER_LIST = "user_identifier_list"

    # Credential objects
    CREDENTIAL = "credential"
    CREDENTIAL_LIST = "credential_list"

    # Logging destination objects (for log destination management)
    LOGGING_DESTINATION = "logging_destination"
    LOGGING_DESTINATION_LIST = "logging_destination_list"

    # Generic message type (used for delete/clear operations)
    MESSAGE = "message"

    # Audit objects
    AUDIT_LOG = "audit_log"

    # SOP objects
    SOP = "sop"
    SOP_LIST = "sop_list"

    # Trigger objects
    TRIGGER = "trigger"
    TRIGGER_LIST = "trigger_list"
