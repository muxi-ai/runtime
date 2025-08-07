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

    JOB_RETRIEVED = "job.retrieved"
    JOB_DELETED = "job.deleted"
    JOB_LIST = "job.list"

    # Configuration events
    OVERLORD_RETRIEVED = "overlord.retrieved"
    OVERLORD_UPDATED = "overlord.updated"
    PERSONA_RETRIEVED = "persona.retrieved"
    PERSONA_UPDATED = "persona.updated"
    MCP_RETRIEVED = "mcp.retrieved"
    MCP_UPDATED = "mcp.updated"
    MCP_SERVER_LIST = "mcp_server.list"
    MCP_SERVER_CREATED = "mcp_server.created"
    MCP_SERVER_RETRIEVED = "mcp_server.retrieved"
    MCP_SERVER_UPDATED = "mcp_server.updated"
    MCP_SERVER_DELETED = "mcp_server.deleted"
    MCP_TOOL_LIST = "mcp_tool.list"
    MCP_TOOL_EXECUTED = "mcp_tool.executed"
    LLM_RETRIEVED = "llm.retrieved"
    LLM_UPDATED = "llm.updated"
    LLM_RESET = "llm.reset"
    LOGGING_RETRIEVED = "logging.retrieved"
    LOGGING_UPDATED = "logging.updated"
    ASYNC_RETRIEVED = "async.retrieved"
    ASYNC_UPDATED = "async.updated"
    SCHEDULER_RETRIEVED = "scheduler.retrieved"
    SCHEDULER_UPDATED = "scheduler.updated"
    A2A_RETRIEVED = "a2a.retrieved"
    A2A_UPDATED = "a2a.updated"
    CONFIG_RETRIEVED = "config.retrieved"
    STATUS_RETRIEVED = "status.retrieved"

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
    AGENT = "agent"
    AGENT_LIST = "agent_list"
    SECRET = "secret"
    SECRET_LIST = "secret_list"
    MEMORY = "memory"
    MEMORY_LIST = "memory_list"
    JOB = "job"
    JOB_LIST = "job_list"
    ERROR = "error"
    EVENT_STREAM = "event_stream"

    # Generic list type for spec compliance
    LIST = "list"

    # Configuration objects
    OVERLORD = "overlord"
    PERSONA = "persona"
    MCP = "mcp"
    MCP_SERVER = "mcp_server"
    MCP_SERVER_LIST = "mcp_server_list"
    MCP_TOOL_LIST = "mcp_tool_list"
    MCP_TOOL_RESULT = "mcp_tool_result"
    LLM = "llm"
    LOGGING = "logging"
    ASYNC = "async"
    SCHEDULER = "scheduler"
    A2A = "a2a"
    STATUS = "status"
    CONFIG = "config"
    FORMATION_STATUS = "formation_status"
    FORMATION_CONFIG = "formation_config"
