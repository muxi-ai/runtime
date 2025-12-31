"""
MUXI Observability Manager

This module contains the ObservabilityManager class which provides
the central coordination for the observability system.
"""

import socket
from contextlib import contextmanager
from typing import Any, Dict, Optional, List
import time
from .logger import EventLogger
from .request_manager import RequestContextManager
from .stream_processor import StreamProcessor
from .health import HealthManager, HealthMonitor, HealthStatusAPI
from ...datatypes.observability import ConversationEvents, SystemEvents, EventLevel, RequestContext
from ...utils.user_dirs import get_observability_dir
from ...utils.id_generator import generate_nanoid


class ObservabilityManager:
    """Central manager for the observability system."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # Check if an event_logger was passed in config
        if "event_logger" in self.config:
            self.event_logger = self.config["event_logger"]
        else:
            self.event_logger = self._create_event_logger()

        # Set the configured event logger in context for global access
        from .context import set_event_logger
        from . import set_runtime_event_logger

        set_event_logger(self.event_logger)
        # Also set as runtime logger for cross-context access
        set_runtime_event_logger(self.event_logger)

        self.request_manager = RequestContextManager(
            cleanup_interval=self.config.get("cleanup_interval", 300)
        )
        self.stream_processor = StreamProcessor()
        self.health_manager = HealthManager()
        self.health_monitor = HealthMonitor(
            health_manager=self.health_manager,
            check_interval=self.config.get("health_check_interval", 30),
        )
        self.health_api = HealthStatusAPI(self.health_manager)
        self._streams_initialized = False
        self._health_monitoring_started = False

        # Track async requests to prevent premature completion
        self._async_requests = set()

        # Event streaming subscriptions for live log streaming
        self._subscribers: List[tuple] = []  # List of (queue, filters) tuples
        self._subscriber_lock = None  # Lazy-initialized to bind to correct event loop
        self.subscriber_queue_maxsize = self.config.get("subscriber_queue_maxsize", 1000)

        # Metrics for dropped events (when subscriber queue is full)
        self._dropped_events_count = 0

        # Cache for compiled regex patterns (performance optimization)
        self._compiled_patterns: Dict[str, Any] = {}

    async def _get_subscriber_lock(self):
        """Lazily initialize subscriber lock on the correct event loop."""
        if self._subscriber_lock is None:
            import asyncio
            self._subscriber_lock = asyncio.Lock()
        return self._subscriber_lock

    def _create_event_logger(self) -> EventLogger:
        """Create event logger from configuration.

        Two-tier logging architecture:
        - system: Infrastructure events (level + destination)
        - conversation: User-facing events (enabled + streams)
        """
        logging_config = self.config.get("logging", {})

        # Parse system config (defaults: level=debug, destination=stdout)
        system_config = logging_config.get("system", {})
        system_level_str = system_config.get("level", "debug").lower()
        system_destination = system_config.get("destination", "stdout")

        # Parse conversation config
        conversation_config = logging_config.get("conversation", {})
        conversation_enabled = conversation_config.get("enabled", False)
        streams = conversation_config.get("streams", [])

        # Determine conversation output from first file stream (if any)
        level = EventLevel.INFO
        output = "stdout"
        output_config = {}
        events = None

        if conversation_enabled and streams:
            for stream in streams:
                if stream.get("transport") == "file" and stream.get("destination"):
                    level_str = stream.get("level", "info").lower()
                    valid_levels = [lvl.value for lvl in EventLevel]
                    level = EventLevel(level_str) if level_str in valid_levels else EventLevel.INFO
                    output = "file"
                    output_config["path"] = stream.get("destination")
                    events = stream.get("events")
                    break
                elif stream.get("transport") == "stream" and stream.get("destination"):
                    output = "stream"
                    output_config["url"] = stream.get("destination")
                    break
                elif stream.get("transport") == "trail":
                    output = "trail"
                    auth = stream.get("auth", {})
                    output_config["trail"] = {
                        "url": auth.get("url", ""),
                        "api_key": auth.get("api_key", ""),
                    }
                    break

        return EventLogger(
            level=level,
            output=output,
            output_config=output_config,
            events=events,
            system_level=system_level_str,
            system_destination=system_destination,
        )

    async def _initialize_streams(self) -> None:
        """Initialize streaming transports from configuration."""
        if self._streams_initialized:
            return

        logging_config = self.config.get("logging", {})
        conversation_config = logging_config.get("conversation", {})
        streams_config = conversation_config.get("streams", [])

        if streams_config:
            await self.stream_processor.initialize(streams_config)
            await self.stream_processor.start()
            self._streams_initialized = True

    async def _start_health_monitoring(self) -> None:
        """Start health monitoring for stream destinations."""
        if self._health_monitoring_started or not self._streams_initialized:
            return

        # Get destinations from configured transports
        destinations = []
        for transport_id, transport in self.stream_processor.transports.items():
            destination = transport.config.get("destination", f"transport_{transport_id}")
            destinations.append(destination)

        if destinations:
            await self.health_monitor.start(destinations)
            self._health_monitoring_started = True

    async def start(self) -> None:
        """Start the observability system."""
        await self.request_manager.start_cleanup()
        await self._initialize_streams()
        await self._start_health_monitoring()

    async def stop(self) -> None:
        """Stop the observability system."""
        await self.request_manager.stop_cleanup()
        if self._streams_initialized:
            await self.stream_processor.stop()
        if self._health_monitoring_started:
            await self.health_monitor.stop()

    async def subscribe(self, filters: Optional[Dict[str, Any]] = None):
        """
        Subscribe to filtered event stream for live log streaming.

        Args:
            filters: Optional dict of filters to apply (user_id, session_id, level, etc.)

        Yields:
            Events that match the filters
        """
        import asyncio

        filters = filters or {}
        queue = asyncio.Queue(maxsize=self.subscriber_queue_maxsize)

        # Add subscriber
        lock = await self._get_subscriber_lock()
        async with lock:
            self._subscribers.append((queue, filters))

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            # Cleanup on disconnect - remove subscriber in-place under lock
            lock = await self._get_subscriber_lock()
            async with lock:
                # Find and remove the matching queue in-place (safer than reassigning list)
                for i, (q, f) in enumerate(self._subscribers):
                    if q is queue:
                        self._subscribers.pop(i)
                        break

    def _matches_filters(self, event: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """
        Check if an event matches the given filters.

        Args:
            event: Event dict with keys like user_id, session_id, level, event_type
            filters: Filter dict with same keys

        Returns:
            True if event matches all filters, False otherwise
        """
        for key, value in filters.items():
            if key == "event_type":
                # Support wildcard matching for event_type
                # Use cached compiled patterns for performance
                if value not in self._compiled_patterns:
                    import re
                    pattern_str = value.replace("*", ".*")
                    self._compiled_patterns[value] = re.compile(pattern_str)
                pattern = self._compiled_patterns[value]
                if not pattern.fullmatch(event.get("event_type", "")):
                    return False
            elif key == "level":
                # Match level or higher severity (e.g., INFO matches INFO, WARNING, ERROR, CRITICAL)
                event_level = event.get("level", "")
                level_order = ["debug", "info", "warning", "error", "critical"]
                try:
                    event_idx = level_order.index(event_level.lower())
                    filter_idx = level_order.index(value.lower())
                    if event_idx < filter_idx:
                        return False
                except (ValueError, AttributeError):
                    # Invalid level, exclude event
                    return False
            else:
                # Exact match for other fields
                if event.get(key) != value:
                    return False
        return True

    async def _emit_to_subscribers(self, event: Dict[str, Any]) -> None:
        """
        Emit event to all matching subscribers.

        Args:
            event: Event dict to emit
        """
        import asyncio

        # Take shallow copy of subscribers under lock, then release
        # This prevents lock contention from filter checks and slow subscribers
        lock = await self._get_subscriber_lock()
        async with lock:
            subscribers_snapshot = list(self._subscribers)

        # Iterate snapshot without holding lock
        for queue, filters in subscribers_snapshot:
            if self._matches_filters(event, filters):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop events if subscriber is slow
                    # Track dropped events for observability
                    self._dropped_events_count += 1
                    # Emit metric if we have significant drops
                    if self._dropped_events_count % 100 == 0:
                        # Use event_logger to avoid recursion in observability system
                        self.event_logger.log_event(
                            event_type="observability.subscriber_slow",
                            level=EventLevel.WARNING,
                            data={
                                "dropped_events": self._dropped_events_count,
                                "subscriber_queue_size": queue.qsize() if hasattr(queue, 'qsize') else 'unknown'
                            },
                            description=f"Dropped {self._dropped_events_count} events due to slow subscribers"
                        )

    def get_dropped_events_count(self) -> int:
        """
        Get the total number of events dropped due to slow subscribers.

        Returns:
            Number of events dropped
        """
        return self._dropped_events_count

    def mark_request_async(self, request_id: str) -> None:
        """Mark a request as async to prevent premature completion.

        This should be called after determining that a request will be processed
        asynchronously. The track_request context manager will not mark the request
        as completed when it exits for async requests.

        Args:
            request_id: The request ID to mark as async
        """
        self._async_requests.add(request_id)

    @contextmanager
    def track_request(
        self,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        formation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        internal_user_id: Optional[int] = None,
        muxi_user_id: Optional[str] = None,
    ):
        """Context manager for request tracking with automatic context propagation (sync version)."""
        # Since request_manager.track_request is async, we need to handle this differently
        # We'll use the context directly

        # Generate request ID if not provided
        if request_id is None:
            request_id = f"req_{generate_nanoid()}"

        # Create request context
        context = RequestContext(
            id=request_id, formation_id=formation_id, user_id=user_id, session_id=session_id
        )

        # Register context with request manager for cleanup
        self.request_manager.register_context_sync(context)

        # Set context for current thread (using context.py)
        from .context import set_request_context

        set_request_context(context)

        # Emit request received event using observe() to respect context
        from . import observe

        observe(
            event_type=ConversationEvents.REQUEST_RECEIVED,
            level=EventLevel.INFO,
            data={},
            description=f"Request {context.id} received",
        )

        try:
            yield context

            # Only mark as completed if not an async request
            # Async requests will be completed by the background task
            if context.id not in self._async_requests:
                # Mark as completed
                context.complete()

                # Emit request completed event using observe() to respect context
                observe(
                    event_type=ConversationEvents.REQUEST_COMPLETED,
                    level=EventLevel.INFO,
                    data={},
                    description=f"Request {context.id} completed in {context.duration_ms}ms",
                )

        except Exception as e:
            # Mark as failed
            context.fail()

            # Emit request failed event using observe() to respect context
            observe(
                event_type=ConversationEvents.REQUEST_FAILED,
                level=EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Request {context.id} failed: {str(e)}",
            )
            raise
        finally:
            # Clear context
            from .context import _current_request_context

            _current_request_context.set(None)

            # Don't remove from async set here - let the background task handle it

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
        # Emit via traditional logger
        event_id = await self.event_logger.emit_event(
            event_type=event_type,
            level=level,
            data=data,
            request_context=request_context,
            parent_event_id=parent_event_id,
            description=description,
        )

        # Also emit via stream processor if initialized
        if self._streams_initialized:
            await self._emit_to_streams(
                event_type, level, data, request_context, parent_event_id, description, event_id
            )

        # Also emit to live stream subscribers
        if self._subscribers:
            # event_type and level are always Enum instances with .value attribute
            event_dict = {
                "event_id": event_id,
                "event_type": event_type.value,
                "level": level.value,
                "description": description or "",
                "data": data or {},
                "user_id": request_context.user_id if request_context else None,
                "session_id": request_context.session_id if request_context else None,
                "request_id": request_context.id if request_context else None,
                "timestamp": time.time(),
            }
            await self._emit_to_subscribers(event_dict)

        return event_id

    async def emit_system_event(
        self,
        event_type: SystemEvents,
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> str:
        """Emit a system infrastructure event (always routed to stdout)."""
        # Emit via traditional logger
        event_id = await self.event_logger.emit_event(
            event_type=event_type,
            level=level,
            data=data,
            request_context=None,  # System events don't have request context
            parent_event_id=None,
            description=description,
        )

        # Also emit via stream processor if initialized
        if self._streams_initialized:
            await self._emit_to_streams(event_type, level, data, None, None, description, event_id)

        # Also emit to live stream subscribers
        if self._subscribers:
            # event_type and level are always Enum instances with .value attribute
            event_dict = {
                "event_id": event_id,
                "event_type": event_type.value,
                "level": level.value,
                "description": description or "",
                "data": data or {},
                "timestamp": time.time(),
            }
            await self._emit_to_subscribers(event_dict)

        return event_id

    async def _emit_to_streams(
        self,
        event_type,
        level: EventLevel,
        data: Optional[Dict[str, Any]],
        request_context: Optional[RequestContext],
        parent_event_id: Optional[str],
        description: Optional[str],
        event_id: str,
    ) -> None:
        """Emit event to stream processor."""
        try:
            # Build event structure compatible with standard format
            event = {
                "id": event_id,
                "timestamp": int(time.time() * 1000),
                "level": level.value,
                "muxi_version": self.config.get("muxi_version", "1.0.0"),
                "server": self._get_server_id(),
                "event": event_type.value,
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

            # Add event-specific data
            if data or description:
                event["data"] = data or {}
                if description:
                    event["data"]["description"] = description

            # Emit to stream processor
            await self.stream_processor.emit_event(event)

        except Exception:
            # Silent failure to avoid disrupting main application flow
            pass

    def _get_server_id(self) -> str:
        """Get server identifier for event tracking."""
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    async def get_transport_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all transports."""
        if self._streams_initialized:
            return await self.stream_processor.get_transport_status()
        return {}

    async def close(self) -> None:
        """Close the observability manager and clean up resources."""
        if self.stream_processor:
            await self.stream_processor.close()

    async def reconfigure_streams(self, streams_config: List[Dict[str, Any]]) -> None:
        """
        Reconfigure the stream processor with new stream configurations.

        This method is called after formation config is loaded to update
        the observability system with the configured streams.

        Args:
            streams_config: List of processed stream configurations
        """
        if not streams_config:
            return

        # Initialize stream processor if not already done
        if not self.stream_processor:
            self.stream_processor = StreamProcessor()

        # Configure streams in the processor
        await self.stream_processor.configure_streams(streams_config)

        # Start the processor if not already running
        if not self.stream_processor.is_running():
            await self.stream_processor.start()

        # Update health monitoring with new destinations
        await self._start_health_monitoring()

    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary for all destinations."""
        return await self.health_api.get_health_summary()

    async def get_destination_health(self, destination: str) -> Dict[str, Any]:
        """Get health status for a specific destination."""
        return await self.health_api.get_destination_health(destination)

    async def get_unhealthy_destinations(self) -> Dict[str, Any]:
        """Get list of all unhealthy destinations."""
        return await self.health_api.get_unhealthy_destinations()

    async def force_health_check(self, destination: Optional[str] = None) -> Dict[str, Any]:
        """Force an immediate health check."""
        return await self.health_api.force_health_check(destination)

    async def reset_destination_health(self, destination: str) -> Dict[str, Any]:
        """Reset a destination's health status to healthy."""
        return await self.health_api.reset_destination_health(destination)

    async def get_health_metrics(self) -> Dict[str, Any]:
        """Get health metrics for monitoring systems."""
        return await self.health_api.get_health_metrics()
