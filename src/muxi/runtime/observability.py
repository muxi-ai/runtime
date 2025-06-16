"""
MUXI Observability System - Phase 1 Implementation

This module provides the dual logging architecture for MUXI runtime:
1. SystemEvents: Infrastructure events, startup, MCP/A2A operations (always stdout)
2. ConversationEvents: User request lifecycle tracking (configurable output)

Key Components:
- EventLogger: Central component for event emission with intelligent routing
- SystemEvents: Enum for system infrastructure events (routed to stdout)
- ConversationEvents: Enum for conversation lifecycle events (routed to configured output)
- RequestContextManager: In-memory request tracking with automatic cleanup
- Event structures with JSON-L formatting for external tool consumption

Event Routing:
- SystemEvents events → Always stdout (for server monitoring)
- ConversationEvents events → Configured output (stdout/file/stream/trail for observability)

Note: This implementation follows Task 5 Phase 1 specification with dual event architecture.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from .utils.id_generator import generate_nanoid as generate_id

# ===================================================================
# CONTEXT VARIABLE INFRASTRUCTURE
# ===================================================================

# Global context variable to track current request context
_current_request_context: ContextVar[Optional['RequestContext']] = ContextVar(
    'request_context',
    default=None
)


def get_current_request_context() -> Optional['RequestContext']:
    """Get the current request context from context variable."""
    return _current_request_context.get()


def set_request_context(context: 'RequestContext') -> None:
    """Set the current request context (internal use only)."""
    _current_request_context.set(context)


class EventLevel(Enum):
    """Event severity levels for observability events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SystemEvents(Enum):
    """System infrastructure events for server monitoring and operations (routed to stdout)."""

    INITIALIZING = "service.initializing"
    # When server starts initializing

    SERVICE_STARTED = "service.started"
    # When server is fully initialized and ready

    # ===================================================================
    # MCP SYSTEM EVENTS
    # ===================================================================
    MCP_SERVER_PROCESS_STARTED = "mcp.server.process.started"
    # When MCP server subprocess is launched

    MCP_SERVER_PROCESS_FAILED = "mcp.server.process.failed"
    # When MCP server subprocess fails to start or crashes

    MCP_SERVER_REGISTERED = "mcp.server.registration.completed"
    # When MCP server is successfully registered

    MCP_SERVER_REGISTRATION_FAILED = "mcp.server.registration.failed"
    # When MCP server registration fails

    MCP_TOOL_DISCOVERY_COMPLETED = "mcp.tool.discovery.completed"
    # When MCP server tool discovery finishes

    # ===================================================================
    # AGENT SYSTEM EVENTS
    # ===================================================================
    AGENT_INITIALIZED = "agent.initialized"
    # When agent instance is created and configured

    # ===================================================================
    # A2A SYSTEM EVENTS
    # ===================================================================
    A2A_CONFIG_LOAD_STARTED = "a2a.config.load.started"
    # When starting to load A2A configuration

    A2A_CONFIG_LOAD_COMPLETED = "a2a.config.load.completed"
    # When A2A configuration is successfully loaded

    A2A_CREDENTIAL_LOADED = "a2a.credential.loaded"
    # When A2A credentials are loaded from storage

    A2A_CREDENTIALS_LOAD_FAILED = "a2a.credentials.load_failed"
    # When A2A credential loading fails

    A2A_CARD_GENERATOR_INITIALIZED = "a2a.card.generator.initialized"
    # When A2A agent card generator is set up

    A2A_AUTH_INITIALIZED = "a2a.auth.initialized"
    # When A2A authentication system is initialized

    A2A_AUTH_VALIDATING = "a2a.auth.validating"
    # When validating A2A authentication credentials

    A2A_AUTH_VALIDATED = "a2a.auth.validated"
    # When A2A authentication is successful

    A2A_AUTH_VALIDATION_FAILED = "a2a.auth.validation_failed"
    # When A2A authentication fails

    A2A_REGISTRY_CLIENT_INITIALIZED = "a2a.registry.client.initialized"
    # When A2A registry client is created

    A2A_REGISTRY_CONNECTED = "a2a.registry.connected"
    # When connection to A2A registry is established

    A2A_REGISTRY_DISCONNECTED = "a2a.registry.disconnected"
    # When A2A registry connection is lost

    A2A_REGISTRY_HEALTH_CHECK_COMPLETED = "a2a.registry.health_check.completed"
    # When A2A registry health check finishes

    A2A_HEALTH_CHECK_STARTED = "a2a.health.check.started"
    # When starting A2A system health check

    A2A_HEALTH_CHECK_COMPLETED = "a2a.health.check.completed"
    # When A2A health check completes successfully

    A2A_HEALTH_CHECK_FAILED = "a2a.health.check.failed"
    # When A2A health check fails

    A2A_REGISTRED = "a2a.registration.completed"
    # When agent is successfully registered with A2A registry

    A2A_REGISTRATION_FAILED = "a2a.registration.failed"
    # When agent registration with A2A registry fails

    A2A_DEREGISTERED = "a2a.deregistration.completed"
    # When agent is successfully deregistered from A2A registry

    A2A_DEREGISTRATION_FAILED = "a2a.deregistration.failed"
    # When agent deregistration from A2A registry fails

    A2A_SERVER_STARTED = "a2a.server.started"
    # When A2A server component starts

    A2A_SERVER_STOPPED = "a2a.server.stopped"
    # When A2A server component stops

    A2A_SERVER_FAILED = "a2a.server.failed"
    # When A2A server component fails

    A2A_DISCOVERY_STARTED = "a2a.discovery.started"
    # When starting A2A agent discovery process

    A2A_DISCOVERY_STOPPED = "a2a.discovery.stopped"
    # When A2A agent discovery process stops

    A2A_DISCOVERY_COMPLETED = "a2a.discovery.completed"
    # When A2A agent discovery process completes

    A2A_DISCOVERY_FAILED = "a2a.discovery.failed"
    # When A2A agent discovery process fails

    A2A_AGENT_REGISTERED = "a2a.agent.registered"
    # When external agent registers with our A2A system

    A2A_AGENT_DEREGISTERED = "a2a.agent.deregistered"
    # When external agent deregisters from our A2A system

    A2A_CARD_GENERATING = "a2a.card.generating"
    # When starting to generate A2A agent card

    A2A_CARD_GENERATED = "a2a.card.generated"
    # When A2A agent card generation completes

    A2A_CARD_EXPORTING = "a2a.card.exporting"
    # When starting to export A2A agent card

    A2A_CARD_EXPORTED = "a2a.card.exported"
    # When A2A agent card export completes

    # ===================================================================
    # CONFIGURATION & STARTUP EVENTS
    # ===================================================================
    CONFIG_FORMATION_LOADED = "config.formation.loaded"
    # When formation configuration file is loaded

    CONFIG_AGENT_LOADED = "config.agent.loaded"
    # When agent configuration is loaded

    CONFIG_MCP_LOADED = "config.mcp.loaded"
    # When MCP server configuration is loaded

    CONFIG_A2A_LOADED = "config.a2a.loaded"
    # When A2A configuration is loaded

    OVERLORD_INITIALIZING = "overlord.initializing"
    # When overlord component starts initialization

    OVERLORD_STARTED = "overlord.started"
    # When overlord component is fully initialized and ready

    CACHE_MANAGER_STARTED = "cache.manager.started"
    # When cache management system starts

    MEMORY_OPTIMIZER_STARTED = "memory.optimizer.started"
    # When memory optimization system starts

    # ===================================================================
    # AUTHENTICATION & SECURITY EVENTS
    # ===================================================================
    AUTH_MANAGER_INITIALIZED = "auth.manager.initialized"
    # When authentication manager is initialized

    INBOUND_AUTH_INITIALIZED = "inbound.auth.initialized"
    # When inbound authentication system is initialized

    # ===================================================================
    # EKNOWLEDGE SYSTEM EVENTS
    # ===================================================================
    KNOWLEDGE_SOURCE_LOADED = "knowledge.source.loaded"
    # When knowledge source is successfully loaded

    KNOWLEDGE_SOURCE_FAILED = "knowledge.source.failed"
    # When knowledge source loading fails

    # ===================================================================
    # INFRASTRUCTURE MONITORING (MOVED FROM CONVERSATIONEVENTs)
    # ===================================================================
    RESOURCE_USAGE_MEASURED = "resource.usage.measured"
    # When system resource usage is measured

    RESOURCE_ALLOCATED = "resource.allocated"
    # When system resources are allocated

    # ===================================================================
    # EXTENSION MANAGEMENT
    # ===================================================================
    EXTENSION_LOADED = "extension.loaded"
    # When extension is successfully loaded

    EXTENSION_FAILED = "extension.failed"
    # When extension loading or operation fails

    EXTENSION_LISTED = "extension.listed"
    # When extension listing operation completes

    EXTENSION_LISTING_FAILED = "extension.listing.failed"
    # When extension listing operation fails

    # ===================================================================
    # MEMORY SYSTEM OPERATIONS
    # ===================================================================
    MEMORY_CLEAR = "memory.clear"
    # When memory system is cleared

    MEMORY_DELETION_COMPLETED = "memory.deletion.completed"
    # When memory deletion operation completes

    MEMORY_DELETION_FAILED = "memory.deletion.failed"
    # When memory deletion operation fails

    # ===================================================================
    # PERFORMANCE MONITORING
    # ===================================================================
    PERFORMANCE_DURATION_RECORDED = "performance.duration.recorded"
    # When performance timing is recorded

    PERFORMANCE_OPTIMIZED = "performance.optimized"
    # When performance optimization is applied

    # ===================================================================
    # SECRET MANAGEMENT OPERATIONS
    # ===================================================================
    SECRET_OPERATION_COMPLETED = "secret.operation.completed"
    # When secret operation (store/retrieve/import/export) completes
    # (with operation_type: "storage", "retrieval", "import", etc. in event data)

    SECRET_OPERATION_FAILED = "secret.operation.failed"
    # When secret operation (store/retrieve/import/export) fails

    SECRET_LISTING_COMPLETED = "secret.listing.completed"
    # When secret listing operation completes

    SECRET_LISTING_FAILED = "secret.listing.failed"
    # When secret listing operation fails

    # ===================================================================
    # DATABASE/STORAGE OPERATIONS
    # ===================================================================
    DB_CONNECTION_STARTED = "db.connection.started"
    # When database connection is initiated

    DB_CONNECTION_FAILED = "db.connection.failed"
    # When database connection fails

    # ===================================================================
    # NETWORK/COMMUNICATION INFRASTRUCTURE
    # ===================================================================
    NETWORK_INTERFACE_INITIALIZED = "network.interface.initialized"
    # When network interface is initialized

    NETWORK_INTERFACE_FAILED = "network.interface.failed"
    # When network interface initialization fails


class ConversationEvents(Enum):
    """Comprehensive event types for MUXI observability covering complete request lifecycle."""

    # ===================================================================
    # SESSION MANAGEMENT
    # ===================================================================
    SESSION_CREATED = "session.created"
    # When new user session is established

    SESSION_ENDED = "session.ended"
    # When user session is terminated normally

    SESSION_EXPIRED = "session.expired"
    # When user session expires due to inactivity

    # ===================================================================
    # REQUEST INGESTION & VALIDATION
    # ===================================================================
    REQUEST_RECEIVED = "request.received"
    # When incoming request is received by the system

    REQUEST_PROCESSING = "request.processing"
    # When request enters processing pipeline

    REQUEST_VALIDATED = "request.validated"
    # When request passes validation checks

    REQUEST_DENIED_AUTH = "request.denied.auth"
    # When request is rejected due to authentication failure

    REQUEST_DENIED_RATE_LIMIT = "request.denied.rate_limit"
    # When request is rejected due to rate limiting

    REQUEST_DENIED_VALIDATION = "request.denied.validation"
    # When request is rejected due to validation errors

    REQUEST_FAILED = "request.failed"  # Error state
    # When request processing fails with error

    REQUEST_COMPLETED = "request.completed"  # Success state
    # When request processing completes successfully

    # ===================================================================
    # MULTI-MODAL CONTENT PROCESSING
    # ===================================================================
    DOCUMENT_PROCESSING_STARTED = "document.processing.started"
    # When document processing begins

    DOCUMENT_PROCESSING_COMPLETED = "document.processing.completed"
    # When document processing completes successfully

    DOCUMENT_PROCESSING_FAILED = "document.processing.failed"
    # When document processing fails

    CONTENT_EXTRACTION_STARTED = "content.extraction.started"
    # When content extraction from media begins

    CONTENT_EXTRACTION_COMPLETED = "content.extraction.completed"
    # When content extraction completes successfully

    CONTENT_EXTRACTION_FAILED = "content.extraction.failed"
    # When content extraction fails

    CONTENT_PROCESSED = "content.processed"
    # When content processing completes

    CONTENT_RETRIEVED = "content.retrieved"
    # When content is retrieved from storage

    CONTENT_IMAGE_ANALYZED = "content.image.analyzed"
    # When image analysis completes

    CONTENT_AUDIO_TRANSCRIBED = "content.audio.transcribed"
    # When audio transcription completes

    # ===================================================================
    # OVERLORD ORCHESTRATION
    # ===================================================================
    OVERLORD_ROUTING_STARTED = "overlord.routing.started"
    # When overlord begins routing decision process

    OVERLORD_ROUTING_COMPLETED = "overlord.routing.completed"
    # When overlord completes routing decision

    OVERLORD_ROUTING_FAILED = "overlord.routing.failed"
    # When overlord routing process fails

    OVERLORD_AGENT_SELECTION_STARTED = "overlord.agent.selection_started"
    # When overlord begins agent selection process

    OVERLORD_AGENT_SELECTED = "overlord.agent.selected"
    # When overlord selects specific agent for task

    OVERLORD_TASK_DECOMPOSED = "overlord.task.decomposed"
    # When overlord breaks down complex task into subtasks

    # ===================================================================
    # MEMORY & CONTEXT OPERATIONS
    # ===================================================================
    # Short-term memory operations
    MEMORY_SHORT_TERM_LOOKUP = "memory.short_term.lookup"
    # When searching short-term memory

    MEMORY_SHORT_TERM_RETRIEVED = "memory.short_term.retrieved"
    # When data is retrieved from short-term memory

    MEMORY_SHORT_TERM_UPDATED = "memory.short_term.updated"
    # When data is updated in short-term memory

    MEMORY_SHORT_TERM_UPDATE_FAILED = "memory.short_term.update_failed"
    # When short-term memory update fails

    MEMORY_SHORT_TERM_RETRIEVAL_FAILED = "memory.short_term.retrieval_failed"
    # When short-term memory retrieval fails

    MEMORY_AUTO_EXTRACTED = "memory.auto.extracted"
    # When memory is auto-extracted

    MEMORY_AUTO_EXTRACTION_FAILED = "memory.auto.extraction.failed"
    # When memory auto-extraction fails

    # Long-term memory operations
    MEMORY_LONG_TERM_LOOKUP = "memory.long_term.lookup"
    # When searching long-term memory

    MEMORY_LONG_TERM_RETRIEVED = "memory.long_term.retrieved"
    # When data is retrieved from long-term memory

    MEMORY_LONG_TERM_ENHANCED = "memory.long_term.enhanced"
    # When long-term memory is enhanced with new information

    MEMORY_LONG_TERM_UPDATED = "memory.long_term.updated"
    # When long-term memory is updated

    MEMORY_LONG_TERM_ENHANCEMENT_FAILED = "memory.long_term.enhancement_failed"
    # When long-term memory enhancement fails

    MEMORY_LONG_TERM_DELETION_FAILED = "memory.long_term.deletion_failed"
    # When long-term memory deletion fails

    MEMORY_LONG_TERM_UPDATE_FAILED = "memory.long_term.update_failed"
    # When long-term memory update fails

    MEMORY_LONG_TERM_RETRIEVAL_FAILED = "memory.long_term.retrieval_failed"
    # When long-term memory retrieval fails

    # ===================================================================
    # AGENT PROCESSING
    # ===================================================================
    AGENT_MESSAGE_PROCESSING = "agent.message.processing"
    # When agent begins processing a message

    AGENT_MESSAGE_COMPLETED = "agent.message.completed"
    # When agent completes message processing

    AGENT_MESSAGE_FAILED = "agent.message.failed"
    # When agent message processing fails

    AGENT_THINKING_STARTED = "agent.thinking.started"
    # When agent begins thinking/reasoning process

    AGENT_THINKING_COMPLETED = "agent.thinking.completed"
    # When agent completes thinking/reasoning

    AGENT_THINKING_FAILED = "agent.thinking.failed"
    # When agent thinking/reasoning fails

    AGENT_PLANNING_STARTED = "agent.planning.started"
    # When agent begins planning process

    AGENT_PLANNING_COMPLETED = "agent.planning.completed"
    # When agent completes planning

    AGENT_PLANNING_FAILED = "agent.planning.failed"
    # When agent planning fails

    AGENT_RESPONSE_GENERATED = "agent.response.generated"
    # When agent generates response

    # ===================================================================
    # MODEL OPERATIONS
    # ===================================================================
    MODEL_REQUEST_STARTED = "model.request.started"
    # When LLM request is initiated

    MODEL_REQUEST_COMPLETED = "model.request.completed"
    # When LLM request completes successfully

    MODEL_REQUEST_FAILED = "model.request.failed"
    # When LLM request fails

    MODEL_STREAMING_STARTED = "model.streaming.started"
    # When LLM streaming response begins

    MODEL_STREAMING_COMPLETED = "model.streaming.completed"
    # When LLM streaming response completes

    # ===================================================================
    # TOOL & MCP OPERATIONS
    # ===================================================================
    MCP_SERVER_CONNECTING = "mcp.server.connecting"
    # When connecting to MCP server for request

    MCP_SERVER_CONNECTED = "mcp.server.connected"
    # When MCP server connection established for request

    MCP_SERVER_DISCONNECTED = "mcp.server.disconnected"
    # When MCP server disconnects during request

    MCP_SERVER_CONNECTION_FAILED = "mcp.server.connection_failed"
    # When MCP server connection fails during request

    MCP_TOOL_DISCOVERY_STARTED = "mcp.tool.discovery_started"
    # When starting tool discovery for request

    MCP_TOOL_DISCOVERY_COMPLETED = "mcp.tool.discovery_completed"
    # When tool discovery completes for request

    MCP_TOOL_DISCOVERY_FAILED = "mcp.tool.discovery_failed"
    # When tool discovery fails for request

    MCP_TOOL_DISCOVERED = "mcp.tool.discovered"
    # When specific tool is discovered

    MCP_TOOL_CALLED = "mcp.tool.called"
    # When MCP tool is invoked

    MCP_TOOL_CALL_STARTED = "mcp.tool.call_started"
    # When MCP tool call begins

    MCP_TOOL_CALL_COMPLETED = "mcp.tool.call_completed"
    # When MCP tool call completes successfully

    MCP_TOOL_CALL_FAILED = "mcp.tool.call_failed"
    # When MCP tool call fails

    # ===================================================================
    # EXTERNAL AGENT COLLABORATION (A2A)
    # ===================================================================
    A2A_MESSAGE_SENT = "a2a.message.sent"
    # When A2A message is sent to external agent

    A2A_MESSAGE_RECEIVED = "a2a.message.received"
    # When A2A message is received from external agent

    A2A_MESSAGE_FAILED = "a2a.message.failed"
    # When A2A message delivery fails

    # Request/response flow
    A2A_REQUEST_SENT = "a2a.request.sent"  # outbound
    # When A2A request is sent to external agent

    A2A_REQUEST_RECEIVED = "a2a.request.received"  # inbound
    # When A2A request is received from external agent

    A2A_RESPONSE_SENT = "a2a.response.sent"  # outbound
    # When A2A response is sent to external agent

    A2A_RESPONSE_RECEIVED = "a2a.response.received"  # inbound
    # When A2A response is received from external agent

    # ===================================================================
    # INTERNAL AGENT COLLABORATION
    # ===================================================================
    COLAB_DISCOVERY_STARTED = "colab.discovery.started"
    # When internal agent discovery begins

    COLAB_REQUEST_SENT = "colab.request.sent"  # outbound
    # When request is sent to internal agent

    COLAB_REQUEST_RECEIVED = "colab.request.received"  # inbound
    # When request is received from internal agent

    COLAB_RESPONSE_SENT = "colab.response.sent"  # outbound
    # When response is sent to internal agent

    COLAB_RESPONSE_RECEIVED = "colab.response.received"  # inbound
    # When response is received from internal agent

    COLAB_MESSAGE_SENT = "colab.message.sent"
    # When message is sent to internal agent

    COLAB_MESSAGE_RECEIVED = "colab.message.received"
    # When message is received from internal agent

    # ===================================================================
    # RESPONSE GENERATION
    # ===================================================================
    RESPONSE_GENERATION_STARTED = "response.generation.started"
    # When response generation process begins

    RESPONSE_FORMATTED = "response.formatted"
    # When response is formatted for delivery

    RESPONSE_VALIDATION_COMPLETED = "response.validation.completed"
    # When response validation completes

    RESPONSE_CONVERSION_STARTED = "response.conversion.started"
    # When response format conversion begins

    RESPONSE_CONVERSION_COMPLETED = "response.conversion.completed"
    # When response format conversion completes

    RESPONSE_DELIVERY_STARTED = "response.delivery.started"
    # When response delivery begins

    RESPONSE_DELIVERY_FAILED = "response.delivery.failed"
    # When response delivery fails

    RESPONSE_DELIVERED = "response.delivered"
    # When response is successfully delivered

    # ===================================================================
    # ASYNC PROCESSING
    # ===================================================================
    ASYNC_THRESHOLD_DETECTED = "async.threshold.detected"
    # When request processing time exceeds async threshold

    ASYNC_PROCESSING_STARTED = "async.processing.started"
    # When request switches to async processing mode

    ASYNC_PROCESSING_COMPLETED = "async.processing.completed"
    # When async processing completes

    ASYNC_PROCESSING_FAILED = "async.processing.failed"
    # When async processing fails

    # ===================================================================
    # WEBHOOK DELIVERY
    # ===================================================================
    WEBHOOK_SENT = "webhook.sent"
    # When webhook notification is sent

    WEBHOOK_FAILED = "webhook.failed"
    # When webhook delivery fails

    # ===================================================================
    # CLARIFICATION HANDLING
    # ===================================================================
    CLARIFICATION_REQUEST_SENT = "clarification.request.sent"
    # When clarification request is sent to user

    CLARIFICATION_FAILED = "clarification.failed"
    # When clarification fails

    CLARIFICATION_RESPONSE_RECEIVED = "clarification.response.received"
    # When clarification response is received from user

    CLARIFICATION_COMPLETED = "clarification.completed"
    # When clarification completes


class ServerEvents(Enum):
    """Server event types for MUXI observability"""

    SERVER_STARTED = "server.started"
    # When server starts

    SERVER_FAILED = "server.failed"
    # When server fails


class ErrorEvents(Enum):
    """Error event types for MUXI observability (routed to stderr)."""

    # ===================================================================
    # VALIDATION ERRORS
    # ===================================================================
    VALIDATION_FAILED = "error.validation.failed"
    # When input validation fails (malformed data, missing fields, etc.)

    SCHEMA_VALIDATION_FAILED = "error.schema.validation.failed"
    # When data doesn't match expected schema

    # ===================================================================
    # AUTHENTICATION & AUTHORIZATION ERRORS
    # ===================================================================
    AUTHENTICATION_FAILED = "error.authentication.failed"
    # When user authentication fails

    AUTHORIZATION_FAILED = "error.authorization.failed"
    # When user lacks permission for requested action

    TOKEN_EXPIRED = "error.token.expired"
    # When authentication token has expired

    TOKEN_INVALID = "error.token.invalid"
    # When authentication token is malformed or invalid

    # ===================================================================
    # NETWORK & CONNECTIVITY ERRORS
    # ===================================================================
    NETWORK_ERROR = "error.network.error"
    # When network connectivity issues occur

    CONNECTION_TIMEOUT = "error.connection.timeout"
    # When connection times out

    CONNECTION_REFUSED = "error.connection.refused"
    # When connection is refused by target

    # ===================================================================
    # RESOURCE ERRORS
    # ===================================================================
    RESOURCE_NOT_FOUND = "error.resource.not_found"
    # When requested resource doesn't exist

    RESOURCE_UNAVAILABLE = "error.resource.unavailable"
    # When resource exists but is temporarily unavailable

    RESOURCE_EXHAUSTED = "error.resource.exhausted"
    # When system resources are exhausted (memory, disk, etc.)

    # ===================================================================
    # RATE LIMITING ERRORS
    # ===================================================================
    RATE_LIMIT_EXCEEDED = "error.rate_limit.exceeded"
    # When request rate exceeds configured limits

    QUOTA_EXCEEDED = "error.quota.exceeded"
    # When usage quota is exceeded

    # ===================================================================
    # CONFIGURATION ERRORS
    # ===================================================================
    CONFIGURATION_ERROR = "error.configuration.error"
    # When system configuration is invalid or missing

    ENVIRONMENT_ERROR = "error.environment.error"
    # When required environment variables are missing or invalid

    # ===================================================================
    # SYSTEM ERRORS
    # ===================================================================
    INTERNAL_ERROR = "error.internal.error"
    # When unexpected internal system error occurs

    SERVICE_UNAVAILABLE = "error.service.unavailable"
    # When required service is unavailable

    DEPENDENCY_ERROR = "error.dependency.error"
    # When external dependency fails or is unavailable

    # ===================================================================
    # DATA ERRORS
    # ===================================================================
    DATA_CORRUPTION = "error.data.corruption"
    # When data corruption is detected

    SERIALIZATION_ERROR = "error.serialization.error"
    # When data serialization/deserialization fails

    ENCODING_ERROR = "error.encoding.error"
    # When character encoding/decoding fails

    RETRY_ATTEMPTED = "error.retry.attempted"
    # When a retry is attempted

    WARNING = "error.warning"
    # When we want to warn about something


@dataclass
class TokenUsage:
    """Token usage tracking for LLM operations."""

    total: int = 0
    breakdown: Dict[str, int] = field(default_factory=dict)

    def add_tokens(self, model: str, tokens: int) -> None:
        """Add token usage for a specific model."""
        self.total += tokens
        self.breakdown[model] = self.breakdown.get(model, 0) + tokens


@dataclass
class RequestContext:
    """Request context tracking for complete lifecycle."""

    id: str
    status: str = "processing"
    started: float = field(default_factory=lambda: time.time() * 1000)  # milliseconds
    formation_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tokens: TokenUsage = field(default_factory=TokenUsage)
    _parent_events: Set[str] = field(default_factory=set, init=False)

    @property
    def duration_ms(self) -> int:
        """Calculate duration in milliseconds since request start."""
        return int(time.time() * 1000 - self.started)

    def add_parent_event(self, event_id: str) -> None:
        """Track parent event relationships."""
        self._parent_events.add(event_id)

    def complete(self) -> None:
        """Mark request as completed."""
        self.status = "completed"

    def fail(self) -> None:
        """Mark request as failed."""
        self.status = "failed"


class RequestContextManager:
    """In-memory request tracking with automatic cleanup."""

    def __init__(self, cleanup_interval: int = 300):  # 5 minutes
        self._contexts: Dict[str, RequestContext] = {}
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start_cleanup(self) -> None:
        """Start the automatic cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        """Stop the automatic cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old request contexts."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_contexts()
            except asyncio.CancelledError:
                break
            except Exception:
                # Silent cleanup failures to avoid disrupting main flow
                pass

    async def _cleanup_old_contexts(self) -> None:
        """Remove contexts older than 1 hour."""
        cutoff_time = time.time() * 1000 - (60 * 60 * 1000)  # 1 hour ago

        async with self._lock:
            to_remove = [
                req_id for req_id, ctx in self._contexts.items() if ctx.started < cutoff_time
            ]
            for req_id in to_remove:
                del self._contexts[req_id]

    @asynccontextmanager
    async def track_request(
        self,
        request_id: Optional[str] = None,
        formation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Context manager for request tracking with automatic context propagation."""
        if request_id is None:
            request_id = generate_id()

        context = RequestContext(
            id=request_id, formation_id=formation_id, user_id=user_id, session_id=session_id
        )

        # Set the context variable when entering the context
        token = _current_request_context.set(context)

        async with self._lock:
            self._contexts[request_id] = context

        try:
            yield context
            context.complete()
        except Exception:
            context.fail()
            raise
        finally:
            # Reset the context variable when exiting
            _current_request_context.reset(token)
            # Don't remove immediately - let cleanup handle it

    async def get_context(self, request_id: str) -> Optional[RequestContext]:
        """Get request context by ID."""
        async with self._lock:
            return self._contexts.get(request_id)

    async def update_context(self, request_id: str, **updates) -> None:
        """Update request context with new information."""
        async with self._lock:
            if context := self._contexts.get(request_id):
                for key, value in updates.items():
                    if hasattr(context, key):
                        setattr(context, key, value)


class EventLogger:
    """Central event logging component with configurable outputs."""

    def __init__(
        self,
        level: EventLevel = EventLevel.INFO,
        output: str = "stdout",
        output_config: Optional[Dict[str, Any]] = None,
        events: Optional[List[str]] = None,
        muxi_version: str = "1.0.0",
    ):
        self.level = level
        self.output = output
        self.output_config = output_config or {}
        self.events = set(events) if events else None
        self.muxi_version = muxi_version
        self._server_id = self._get_server_id()

    def _get_server_id(self) -> str:
        """Get server identifier for event tracking."""
        import socket

        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def _should_emit_event(self, event_type: str, level: EventLevel) -> bool:
        """Check if event should be emitted based on configuration."""
        # Check level filter
        level_priority = {
            EventLevel.DEBUG: 0,
            EventLevel.INFO: 1,
            EventLevel.WARNING: 2,
            EventLevel.ERROR: 3,
        }

        if level_priority[level] < level_priority[self.level]:
            return False

        # Check specific event filter
        if self.events is not None and event_type not in self.events:
            return False

        return True

    async def emit_event(
        self,
        event_type: Union[ConversationEvents, SystemEvents, str],
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        request_context: Optional[RequestContext] = None,
        parent_event_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """Emit an observability event with structured data."""
        # Handle different event types
        if isinstance(event_type, (ConversationEvents, SystemEvents)):
            event_type_str = event_type.value
        else:
            event_type_str = event_type

        if not self._should_emit_event(event_type_str, level):
            return ""

        # Generate event ID
        event_id = generate_id()

        # Build event structure
        event = {
            "id": event_id,
            "timestamp": int(time.time() * 1000),
            "level": level.value,
            "muxi_version": self.muxi_version,
            "server": self._server_id,
            "event": event_type_str,
        }

        # Add parent event relationship
        if parent_event_id:
            event["parent_event_id"] = parent_event_id

        # Add request context if available
        if request_context:
            event["request"] = {
                "id": request_context.id,
                "status": request_context.status,
                "started": int(request_context.started),
                "duration_ms": request_context.duration_ms,
                "formation_id": request_context.formation_id,
                "user_id": request_context.user_id,
                "tokens": {
                    "total": request_context.tokens.total,
                    "breakdown": request_context.tokens.breakdown,
                },
            }

            # Track parent relationship
            request_context.add_parent_event(event_id)

        # Add event-specific data
        if data or description:
            event["data"] = data or {}
            if description:
                event["data"]["description"] = description

        # Emit to configured output
        await self._emit_to_output(event, event_type)

        return event_id

    async def _emit_to_output(
        self, event: Dict[str, Any], event_type: Union[ConversationEvents, SystemEvents, str]
    ) -> None:
        """Emit event to the configured output destination."""
        try:
            # JSON-L format for easy parsing
            event_line = json.dumps(event, separators=(",", ":"))

            # Route SystemEvents to stdout only, regardless of configuration
            if isinstance(event_type, SystemEvents):
                print(event_line, flush=True)
                return

            # Route ConversationEvents to configured output
            if self.output == "stdout":
                print(event_line, flush=True)
            elif self.output == "file":
                await self._emit_to_file(event_line)
            elif self.output == "stream":
                await self._emit_to_stream(event_line)
            elif self.output == "trail":
                await self._emit_to_trail(event_line)

        except Exception:
            # Silent failures to avoid disrupting main application flow
            pass

    async def _emit_to_file(self, event_line: str) -> None:
        """Emit event to file output."""
        file_path = self.output_config.get("path", "muxi_events.jsonl")
        try:
            import aiofiles

            async with aiofiles.open(file_path, "a") as f:
                await f.write(event_line + "\n")
        except ImportError:
            # Fallback to synchronous file write
            with open(file_path, "a") as f:
                f.write(event_line + "\n")

    async def _emit_to_stream(self, event_line: str) -> None:
        """Emit event to stream output."""
        stream_url = self.output_config.get("url")
        if not stream_url:
            return

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                await session.post(
                    stream_url,
                    data=event_line + "\n",
                    headers={"Content-Type": "application/x-ndjson"},
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception:
            # Silent failure for external stream connectivity issues
            pass

    async def _emit_to_trail(self, event_line: str) -> None:
        """Emit event to MUXI trail output."""
        trail_config = self.output_config.get("trail", {})
        trail_url = trail_config.get("url")

        if not trail_url:
            return

        try:
            import aiohttp

            headers = {"Content-Type": "application/x-ndjson"}

            # Add authentication if configured
            if api_key := trail_config.get("api_key"):
                headers["Authorization"] = f"Bearer {api_key}"

            async with aiohttp.ClientSession() as session:
                await session.post(
                    trail_url,
                    data=event_line + "\n",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception:
            # Silent failure for external trail connectivity issues
            pass


class ObservabilityManager:
    """Central manager for the observability system."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.event_logger = self._create_event_logger()
        self.request_manager = RequestContextManager(
            cleanup_interval=self.config.get("cleanup_interval", 300)
        )

    def _create_event_logger(self) -> EventLogger:
        """Create event logger from configuration."""
        logging_config = self.config.get("logging", {})

        # Parse level
        level_str = logging_config.get("level", "info").lower()
        valid_levels = [level.value for level in EventLevel]
        level = EventLevel(level_str) if level_str in valid_levels else EventLevel.INFO

        # Parse output configuration
        output = logging_config.get("output", "stdout")
        output_config = {}

        if output == "file":
            output_config["path"] = logging_config.get("path", "muxi_events.jsonl")
        elif output == "stream":
            output_config["url"] = logging_config.get("stream_url", "")
        elif output == "trail":
            output_config["trail"] = {
                "url": logging_config.get("trail_url", ""),
                "api_key": logging_config.get("trail_api_key", ""),
            }

        # Parse event filters
        events = logging_config.get("events")

        return EventLogger(
            level=level,
            output=output,
            output_config=output_config,
            events=events,
            muxi_version=self.config.get("muxi_version", "1.0.0"),
        )

    async def start(self) -> None:
        """Start the observability system."""
        await self.request_manager.start_cleanup()

    async def stop(self) -> None:
        """Stop the observability system."""
        await self.request_manager.stop_cleanup()

    @asynccontextmanager
    async def track_request(
        self,
        request_id: Optional[str] = None,
        formation_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Context manager for request tracking with automatic context propagation."""
        async with self.request_manager.track_request(
            request_id=request_id, formation_id=formation_id, user_id=user_id
        ) as context:
            # Emit request received event - context automatically available!
            await self.event_logger.emit_event(
                ConversationEvents.REQUEST_RECEIVED,
                level=EventLevel.INFO,
                request_context=context,
                description=f"Request {context.id} received",
            )

            try:
                yield context

                # Emit request completed event - context automatically available!
                await self.event_logger.emit_event(
                    ConversationEvents.REQUEST_COMPLETED,
                    level=EventLevel.INFO,
                    request_context=context,
                    description=f"Request {context.id} completed in {context.duration_ms}ms",
                )

            except Exception as e:
                # Emit request failed event - context automatically available!
                await self.event_logger.emit_event(
                    ConversationEvents.REQUEST_FAILED,
                    level=EventLevel.ERROR,
                    request_context=context,
                    data={"error": str(e)},
                    description=f"Request {context.id} failed: {str(e)}",
                )
                raise

    async def emit_conversation_event(
        self,
        event_type: ConversationEvents,
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        request_context: Optional[RequestContext] = None,
        parent_event_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """Emit a conversation lifecycle event (routed to configured output)."""
        return await self.event_logger.emit_event(
            event_type=event_type,
            level=level,
            data=data,
            request_context=request_context,
            parent_event_id=parent_event_id,
            description=description,
        )

    async def emit_system_event(
        self,
        event_type: SystemEvents,
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> str:
        """Emit a system infrastructure event (always routed to stdout)."""
        return await self.event_logger.emit_event(
            event_type=event_type,
            level=level,
            data=data,
            request_context=None,  # System events don't have request context
            parent_event_id=None,
            description=description,
        )


# ===================================================================
# SIMPLE HELPER FUNCTION FOR PLACEHOLDER REPLACEMENT
# ===================================================================


async def emit_event(
    event_type: str,
    level: str = "INFO",
    data: Optional[Dict[str, Any]] = None,
    description: str = "",
):
    """
    Emit an observability event with automatic context propagation.

    This function automatically retrieves the request context from the
    contextvars system, eliminating the need to manually pass request_context
    throughout the codebase.

    Args:
        event_type: ConversationEvents enum name (e.g., "AGENT_MESSAGE_PROCESSING")
        level: EventLevel name (e.g., "INFO", "ERROR", "DEBUG")
        data: Additional event data dictionary
        description: Human-readable event description
    """
    # Automatically get context from ContextVar
    request_context = get_current_request_context()

    # Skip if no context available (not in a tracked request)
    if not request_context:
        return

    try:
        # Get observability manager directly (singleton pattern)
        observability_manager = ObservabilityManager.get_instance()
        if not observability_manager:
            return

        # Convert string names to enum values
        event_enum = getattr(ConversationEvents, event_type)
        level_enum = getattr(EventLevel, level)

        # Emit event through observability manager
        await observability_manager.event_logger.emit_event(
            event_enum,
            level=level_enum,
            request_context=request_context,  # Context automatically provided
            data=data or {},
            description=description,
        )
    except (ImportError, AttributeError):
        # Silently fail if observability not available
        pass
