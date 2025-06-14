"""
MUXI Observability System - Phase 1 Implementation

This module provides the dual logging architecture for MUXI runtime:
1. SystemEventType: Infrastructure events, startup, MCP/A2A operations (always stdout)
2. ConversationEventType: User request lifecycle tracking (configurable output)

Key Components:
- EventLogger: Central component for event emission with intelligent routing
- SystemEventType: Enum for system infrastructure events (routed to stdout)
- ConversationEventType: Enum for conversation lifecycle events (routed to configured output)
- RequestContextManager: In-memory request tracking with automatic cleanup
- Event structures with JSON-L formatting for external tool consumption

Event Routing:
- SystemEventType events → Always stdout (for server monitoring)
- ConversationEventType events → Configured output (stdout/file/stream/trail for observability)

Note: This implementation follows Task 5 Phase 1 specification with dual event architecture.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from .utils.id_generator import generate_nanoid as generate_id


class EventLevel(Enum):
    """Event severity levels for observability events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SystemEventType(Enum):
    """System infrastructure events for server monitoring and operations (routed to stdout)."""

    # ===================================================================
    # MCP SYSTEM EVENTS
    # ===================================================================
    MCP_SERVER_CONNECTING = "mcp.server.connecting"
    MCP_SERVER_CONNECTED = "mcp.server.connected"
    MCP_SERVER_DISCONNECTED = "mcp.server.disconnected"
    MCP_SERVER_REGISTRATION_STARTED = "mcp.server.registration.started"
    MCP_SERVER_REGISTRATION_COMPLETED = "mcp.server.registration.completed"
    MCP_SERVER_REGISTRATION_FAILED = "mcp.server.registration.failed"
    MCP_TOOL_DISCOVERY_COMPLETED = "mcp.tool.discovery.completed"
    MCP_SERVER_PROCESS_STARTED = "mcp.server.process.started"
    MCP_SERVER_PROCESS_FAILED = "mcp.server.process.failed"

    # ===================================================================
    # A2A SYSTEM EVENTS
    # ===================================================================
    A2A_REGISTRY_CLIENT_INITIALIZED = "a2a.registry.client.initialized"
    A2A_REGISTRY_CONNECTED = "a2a.registry.connected"
    A2A_REGISTRY_DISCONNECTED = "a2a.registry.disconnected"
    A2A_HEALTH_CHECK = "a2a.health.check"
    A2A_REGISTRATION_STARTED = "a2a.registration.started"
    A2A_REGISTRATION_COMPLETED = "a2a.registration.completed"
    A2A_REGISTRATION_FAILED = "a2a.registration.failed"
    A2A_DISCOVERY_STARTED = "a2a.discovery.started"
    A2A_DISCOVERY_COMPLETED = "a2a.discovery.completed"
    A2A_DISCOVERY_FAILED = "a2a.discovery.failed"
    A2A_AGENT_REGISTERED = "a2a.agent.registered"
    A2A_AGENT_DEREGISTERED = "a2a.agent.deregistered"
    A2A_FORMATION_SERVER_STARTED = "a2a.formation.server.started"
    A2A_FORMATION_SERVER_STOPPED = "a2a.formation.server.stopped"
    A2A_FORMATION_SERVER_FAILED = "a2a.formation.server.failed"
    A2A_REGISTRY_HEALTH_CHECK_COMPLETED = "a2a.registry.health_check.completed"

    # ===================================================================
    # CONFIGURATION & STARTUP EVENTS
    # ===================================================================
    FORMATION_CONFIG_LOADED = "formation.config.loaded"
    AGENT_CONFIG_LOADED = "agent.config.loaded"
    MCP_CONFIG_LOADED = "mcp.config.loaded"
    A2A_CONFIG_LOADED = "a2a.config.loaded"
    OVERLORD_SERVICES_STARTED = "overlord.services.started"
    OVERLORD_INITIALIZATION_STARTED = "overlord.initialization.started"
    OVERLORD_INITIALIZATION_COMPLETED = "overlord.initialization.completed"
    OVERLORD_ROUTING_STARTED = "overlord.routing.started"
    OVERLORD_ROUTING_COMPLETED = "overlord.routing.completed"
    OVERLORD_AGENT_SELECTION_STARTED = "overlord.agent.selection.started"
    OVERLORD_AGENT_SELECTION_COMPLETED = "overlord.agent.selection.completed"
    CACHE_MANAGER_STARTED = "cache.manager.started"
    MEMORY_OPTIMIZER_STARTED = "memory.optimizer.started"

    # ===================================================================
    # AUTHENTICATION & SECURITY EVENTS
    # ===================================================================
    CREDENTIALS_LOADED = "credentials.loaded"
    AUTH_MANAGER_INITIALIZED = "auth.manager.initialized"
    INBOUND_AUTH_INITIALIZED = "inbound.auth.initialized"
    SECRET_LOADING_COMPLETED = "secret.loading.completed"
    SECRET_LOADING_FAILED = "secret.loading.failed"

    # ===================================================================
    # EXTENSION & KNOWLEDGE SYSTEM EVENTS
    # ===================================================================
    SQLITE_EXTENSION_INITIALIZED = "sqlite.extension.initialized"
    KNOWLEDGE_SOURCE_LOADED = "knowledge.source.loaded"
    KNOWLEDGE_SOURCE_FAILED = "knowledge.source.failed"

    # ===================================================================
    # INFRASTRUCTURE MONITORING (MOVED FROM CONVERSATIONEVENTTYPE)
    # ===================================================================
    RESOURCE_USAGE_MEASURED = "resource.usage.measured"
    RESOURCE_ALLOCATED = "resource.allocated"
    ERROR_RETRY_ATTEMPTED = "error.retry.attempted"
    OVERLORD_INITIALIZED = "overlord.initialized"

    # ===================================================================
    # ENCRYPTION & SECURITY OPERATIONS
    # ===================================================================
    ENCRYPTION_STARTED = "encryption.started"
    ENCRYPTION_COMPLETED = "encryption.completed"

    # ===================================================================
    # EXTENSION MANAGEMENT
    # ===================================================================
    EXTENSION_INITIALIZATION_STARTED = "extension.initialization.started"
    EXTENSION_INITIALIZATION_COMPLETED = "extension.initialization.completed"
    EXTENSION_LISTING_STARTED = "extension.listing.started"
    EXTENSION_LISTING_COMPLETED = "extension.listing.completed"
    EXTENSION_LOOKUP_STARTED = "extension.lookup.started"
    EXTENSION_LOOKUP_COMPLETED = "extension.lookup.completed"
    EXTENSION_REGISTRATION_STARTED = "extension.registration.started"
    EXTENSION_REGISTRATION_COMPLETED = "extension.registration.completed"

    # ===================================================================
    # ID GENERATION UTILITIES
    # ===================================================================
    ID_GENERATION_STARTED = "id.generation.started"
    ID_GENERATION_COMPLETED = "id.generation.completed"

    # ===================================================================
    # MEMORY SYSTEM OPERATIONS
    # ===================================================================
    MEMORY_CLEAR = "memory.clear"
    MEMORY_CONTEXT_CLEARED = "memory.context.cleared"
    MEMORY_DELETION_COMPLETED = "memory.deletion.completed"

    # ===================================================================
    # PERFORMANCE MONITORING
    # ===================================================================
    PERFORMANCE_DURATION_RECORDED = "performance.duration.recorded"
    PERFORMANCE_OPTIMIZED = "performance.optimized"

    # ===================================================================
    # SECRET MANAGEMENT OPERATIONS
    # ===================================================================
    SECRET_CLEARING_STARTED = "secret.clearing.started"
    SECRET_CLEARING_COMPLETED = "secret.clearing.completed"
    SECRET_DELETION_STARTED = "secret.deletion.started"
    SECRET_DELETION_COMPLETED = "secret.deletion.completed"
    SECRET_EXPORT_STARTED = "secret.export.started"
    SECRET_EXPORT_COMPLETED = "secret.export.completed"
    SECRET_IMPORT_STARTED = "secret.import.started"
    SECRET_IMPORT_COMPLETED = "secret.import.completed"
    SECRET_INTERPOLATION_STARTED = "secret.interpolation.started"
    SECRET_INTERPOLATION_COMPLETED = "secret.interpolation.completed"
    SECRET_LISTING_STARTED = "secret.listing.started"
    SECRET_LISTING_COMPLETED = "secret.listing.completed"
    SECRET_RETRIEVAL_STARTED = "secret.retrieval.started"
    SECRET_RETRIEVAL_COMPLETED = "secret.retrieval.completed"
    SECRET_STORAGE_STARTED = "secret.storage.started"
    SECRET_STORAGE_COMPLETED = "secret.storage.completed"

    # ===================================================================
    # UTILITY OPERATIONS
    # ===================================================================
    UTILITY_STARTED = "utility.started"
    UTILITY_COMPLETED = "utility.completed"


class ConversationEventType(Enum):
    """Comprehensive event types for MUXI observability covering complete request lifecycle."""

    # ===================================================================
    # REQUEST INGESTION & VALIDATION
    # ===================================================================
    REQUEST_RECEIVED = "request.received"
    REQUEST_DENIED_AUTH = "request.denied.auth"
    REQUEST_DENIED_RATE_LIMIT = "request.denied.rate_limit"
    REQUEST_DENIED_VALIDATION = "request.denied.validation"
    REQUEST_VALIDATED = "request.validated"

    # ===================================================================
    # MULTI-MODAL CONTENT PROCESSING
    # ===================================================================
    CONTENT_DOCUMENT_PARSED = "content.document.parsed"
    CONTENT_IMAGE_ANALYZED = "content.image.analyzed"
    CONTENT_AUDIO_TRANSCRIBED = "content.audio.transcribed"
    CONTENT_EXTRACTION_STARTED = "content.extraction.started"
    CONTENT_EXTRACTION_COMPLETED = "content.extraction.completed"
    CONTENT_EXTRACTION_FAILED = "content.extraction.failed"
    CONTENT_PROCESSED = "content.processed"
    CONTENT_RETRIEVED = "content.retrieved"
    DOCUMENT_PROCESSING_STARTED = "document.processing.started"
    DOCUMENT_PROCESSING_COMPLETED = "document.processing.completed"

    # ===================================================================
    # OVERLORD ORCHESTRATION
    # ===================================================================
    OVERLORD_ROUTING_FAILED = "overlord.routing.failed"
    OVERLORD_AGENT_SELECTED = "overlord.agent.selected"
    OVERLORD_AGENT_NOTFOUND = "overlord.agent.not_found"
    OVERLORD_TASK_DECOMPOSED = "overlord.task.decomposed"

    # ===================================================================
    # MEMORY & CONTEXT OPERATIONS
    # ===================================================================
    MEMORY_SHORT_TERM_RETRIEVED = "memory.short_term.retrieved"
    MEMORY_LONG_TERM_RETRIEVED = "memory.long_term.retrieved"
    MEMORY_SHORT_TERM_STORED = "memory.short_term.stored"
    MEMORY_LONG_TERM_STORED = "memory.long_term.stored"
    MEMORY_EXTRACTION_STARTED = "memory.extraction.started"
    MEMORY_CONTEXT_ENHANCED = "memory.context.enhanced"
    MEMORY_CONTEXT_RETRIEVED = "memory.context.retrieved"
    MEMORY_CONTEXT_UPDATED = "memory.context.updated"

    # Memory operation results
    MEMORY_LONG_TERM_UPDATED = "memory.long_term.updated"
    MEMORY_SHORT_TERM_UPDATED = "memory.short_term.updated"

    # Memory error events
    MEMORY_LONG_TERM_STORE_FAILED = "memory.long_term.store_failed"
    MEMORY_SHORT_TERM_STORE_FAILED = "memory.short_term.store_failed"
    MEMORY_LONG_TERM_DELETION_FAILED = "memory.long_term.deletion_failed"
    MEMORY_SHORT_TERM_DELETION_FAILED = "memory.short_term.deletion_failed"
    MEMORY_LONG_TERM_UPDATE_FAILED = "memory.long_term.update_failed"
    MEMORY_SHORT_TERM_UPDATE_FAILED = "memory.short_term.update_failed"
    MEMORY_LONG_TERM_RETRIEVAL_FAILED = "memory.long_term.retrieval_failed"
    MEMORY_SHORT_TERM_RETRIEVAL_FAILED = "memory.short_term.retrieval_failed"

    # ===================================================================
    # AGENT PROCESSING
    # ===================================================================
    AGENT_SELECTED = "agent.selected"
    AGENT_INITIALIZED = "agent.initialized"
    AGENT_THINKING_STARTED = "agent.thinking.started"
    AGENT_THINKING_COMPLETED = "agent.thinking.completed"
    AGENT_PLANNING_CREATED = "agent.planning.created"
    AGENT_CONTEXT_APPLIED = "agent.context.applied"
    AGENT_MESSAGE_PROCESSING = "agent.message.processing"
    AGENT_MESSAGE_COMPLETED = "agent.message.completed"
    AGENT_MESSAGE_FAILED = "agent.message.failed"
    AGENT_RESPONSE_GENERATED = "agent.response.generated"

    # ===================================================================
    # MODEL OPERATIONS
    # ===================================================================
    MODEL_REQUEST_STARTED = "model.request.started"
    MODEL_REQUEST_COMPLETED = "model.request.completed"
    MODEL_STREAMING_STARTED = "model.streaming.started"

    # ===================================================================
    # TOOL & MCP OPERATIONS
    # ===================================================================
    MCP_CONNECTION_ESTABLISHED = "mcp.connection.established"
    MCP_TOOL_DISCOVERED = "mcp.tool.discovered"
    MCP_TOOL_CALLED = "mcp.tool.called"

    MCP_TOOL_CALL_STARTED = "mcp.tool.call_started"
    MCP_TOOL_CALL_COMPLETED = "mcp.tool.call_completed"
    MCP_TOOL_CALL_FAILED = "mcp.tool.call_failed"
    MCP_SERVER_CONNECTED = "mcp.server.connected"
    MCP_SERVER_DISCONNECTED = "mcp.server.disconnected"

    # ===================================================================
    # A2A & COLLABORATION
    # ===================================================================
    # external agent collaboration
    A2A_DISCOVERY_STARTED = "a2a.discovery.started"
    A2A_REQUEST_SENT = "a2a.request.sent"  # outbound
    A2A_REQUEST_RECEIVED = "a2a.request.received"  # inbound
    A2A_RESPONSE_RECEIVED = "a2a.response.received"  # inbound
    A2A_RESPONSE_SENT = "a2a.response.sent"  # outbound
    A2A_MESSAGE_SENT = "a2a.message.sent"
    A2A_MESSAGE_RECEIVED = "a2a.message.received"

    # internal agent collaboration
    COLAB_DISCOVERY_STARTED = "colab.discovery.started"
    COLAB_REQUEST_SENT = "colab.request.sent"  # outbound
    COLAB_REQUEST_RECEIVED = "colab.request.received"  # inbound
    COLAB_RESPONSE_RECEIVED = "colab.response.received"  # inbound
    COLAB_RESPONSE_SENT = "colab.response.sent"  # outbound
    COLAB_MESSAGE_SENT = "colab.message.sent"
    COLAB_MESSAGE_RECEIVED = "colab.message.received"

    # ===================================================================
    # RESPONSE GENERATION
    # ===================================================================
    RESPONSE_GENERATION_STARTED = "response.generation.started"
    RESPONSE_MULTIMODAL_CREATED = "response.multimodal.created"
    RESPONSE_VALIDATION_COMPLETED = "response.validation.completed"
    RESPONSE_FORMATTED = "response.formatted"
    RESPONSE_CONVERSION_STARTED = "response.conversion.started"
    RESPONSE_CONVERSION_COMPLETED = "response.conversion.completed"

    # ===================================================================
    # ASYNC & DELIVERY
    # ===================================================================
    ASYNC_THRESHOLD_DETECTED = "async.threshold.detected"
    ASYNC_PROCESSING_STARTED = "async.processing.started"
    RESPONSE_WEBHOOK_SENT = "response.webhook.sent"
    RESPONSE_DELIVERED = "response.delivered"

    # ===================================================================
    # CLARIFICATION HANDLING
    # ===================================================================
    CLARIFICATION_REQUEST_SENT = "clarification.request.sent"
    CLARIFICATION_RESPONSE_RECEIVED = "clarification.response.received"

    # ===================================================================
    # ERROR HANDLING & RECOVERY
    # ===================================================================
    ERROR_TIMEOUT_DETECTED = "error.timeout.detected"
    ERROR_FALLBACK_ACTIVATED = "error.fallback.activated"
    ERROR_RECOVERY_COMPLETED = "error.recovery.completed"
    ERROR_CLARIFICATION_FAILED = "error.clarification.failed"
    ERROR_AGENT_PROCESSING = "error.agent.processing"
    ERROR_RETRY_ATTEMPTED = "error.retry.attempted"

    # ===================================================================
    # SESSION MANAGEMENT
    # ===================================================================
    SESSION_CREATED = "session.created"
    SESSION_CONTEXT_UPDATED = "session.context.updated"

    # ===================================================================
    # REQUEST LIFECYCLE (LEGACY COMPATIBILITY)
    # ===================================================================
    REQUEST_PROCESSING = "request.processing"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"


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
                req_id for req_id, ctx in self._contexts.items()
                if ctx.started < cutoff_time
            ]
            for req_id in to_remove:
                del self._contexts[req_id]

    @asynccontextmanager
    async def track_request(
        self,
        request_id: Optional[str] = None,
        formation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """Context manager for request tracking with automatic cleanup."""
        if request_id is None:
            request_id = generate_id()

        context = RequestContext(
            id=request_id,
            formation_id=formation_id,
            user_id=user_id
        )

        async with self._lock:
            self._contexts[request_id] = context

        try:
            yield context
            context.complete()
        except Exception:
            context.fail()
            raise
        finally:
            # Don't remove immediately - let cleanup handle it
            pass

    async def get_context(self, request_id: str) -> Optional[RequestContext]:
        """Get request context by ID."""
        async with self._lock:
            return self._contexts.get(request_id)

    async def update_context(
        self,
        request_id: str,
        **updates
    ) -> None:
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
        muxi_version: str = "1.0.0"
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
            EventLevel.ERROR: 3
        }

        if level_priority[level] < level_priority[self.level]:
            return False

        # Check specific event filter
        if self.events is not None and event_type not in self.events:
            return False

        return True

    async def emit_event(
        self,
        event_type: Union[ConversationEventType, SystemEventType, str],
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        request_context: Optional[RequestContext] = None,
        parent_event_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> str:
        """Emit an observability event with structured data."""
        # Handle different event types
        if isinstance(event_type, (ConversationEventType, SystemEventType)):
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
            "event": event_type_str
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
                    "breakdown": request_context.tokens.breakdown
                }
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
        self,
        event: Dict[str, Any],
        event_type: Union[ConversationEventType, SystemEventType, str]
    ) -> None:
        """Emit event to the configured output destination."""
        try:
            # JSON-L format for easy parsing
            event_line = json.dumps(event, separators=(',', ':'))

            # Route SystemEventType to stdout only, regardless of configuration
            if isinstance(event_type, SystemEventType):
                print(event_line, flush=True)
                return

            # Route ConversationEventType to configured output
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
                    timeout=aiohttp.ClientTimeout(total=5)
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
                    timeout=aiohttp.ClientTimeout(total=10)
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
                "api_key": logging_config.get("trail_api_key", "")
            }

        # Parse event filters
        events = logging_config.get("events")

        return EventLogger(
            level=level,
            output=output,
            output_config=output_config,
            events=events,
            muxi_version=self.config.get("muxi_version", "1.0.0")
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
        user_id: Optional[str] = None
    ):
        """Context manager for request tracking."""
        async with self.request_manager.track_request(
            request_id=request_id,
            formation_id=formation_id,
            user_id=user_id
        ) as context:
            # Emit request received event
            await self.event_logger.emit_event(
                ConversationEventType.REQUEST_RECEIVED,
                level=EventLevel.INFO,
                request_context=context,
                description=f"Request {context.id} received"
            )

            try:
                yield context

                # Emit request completed event
                await self.event_logger.emit_event(
                    ConversationEventType.REQUEST_COMPLETED,
                    level=EventLevel.INFO,
                    request_context=context,
                    description=f"Request {context.id} completed in {context.duration_ms}ms"
                )

            except Exception as e:
                # Emit request failed event
                await self.event_logger.emit_event(
                    ConversationEventType.REQUEST_FAILED,
                    level=EventLevel.ERROR,
                    request_context=context,
                    data={"error": str(e)},
                    description=f"Request {context.id} failed: {str(e)}"
                )
                raise

    async def emit_conversation_event(
        self,
        event_type: ConversationEventType,
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        request_context: Optional[RequestContext] = None,
        parent_event_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> str:
        """Emit a conversation lifecycle event (routed to configured output)."""
        return await self.event_logger.emit_event(
            event_type=event_type,
            level=level,
            data=data,
            request_context=request_context,
            parent_event_id=parent_event_id,
            description=description
        )

    async def emit_system_event(
        self,
        event_type: SystemEventType,
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None
    ) -> str:
        """Emit a system infrastructure event (always routed to stdout)."""
        return await self.event_logger.emit_event(
            event_type=event_type,
            level=level,
            data=data,
            request_context=None,  # System events don't have request context
            parent_event_id=None,
            description=description
        )


# ===================================================================
# SIMPLE HELPER FUNCTION FOR PLACEHOLDER REPLACEMENT
# ===================================================================

async def emit_event(
    event_type: str,
    level: str = "INFO",
    request_context=None,
    data: dict = None,
    description: str = ""
):
    """
    Emit an observability event with direct access to observability system.

    Simple helper function to replace 943 observability placeholders throughout the codebase.
    Uses direct access to ObservabilityManager singleton instead of requiring overlord reference.

    Args:
        event_type: ConversationEventType enum name (e.g., "AGENT_MESSAGE_PROCESSING")
        level: EventLevel name (e.g., "INFO", "ERROR", "DEBUG")
        request_context: Request context for event correlation
        data: Additional event data dictionary
        description: Human-readable event description
    """
    if not request_context:
        return

    try:
        # Get observability manager directly (singleton pattern)
        observability_manager = ObservabilityManager.get_instance()
        if not observability_manager:
            return

        # Convert string names to enum values
        event_enum = getattr(ConversationEventType, event_type)
        level_enum = getattr(EventLevel, level)

        # Emit event directly through observability manager
        await observability_manager.event_logger.emit_event(
            event_enum,
            level=level_enum,
            request_context=request_context,
            data=data or {},
            description=description
        )
    except (ImportError, AttributeError):
        # Silently fail if observability not available
        pass
