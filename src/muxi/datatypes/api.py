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
