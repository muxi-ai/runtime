"""
MUXI Observability Manager

This module contains the ObservabilityManager class which provides
the central coordination for the observability system.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, List

from .logger import EventLogger
from .request_manager import RequestContextManager
from .stream_processor import StreamProcessor
from .health import HealthMonitor, HealthStatusAPI
from .types import ConversationEvents, SystemEvents, EventLevel, RequestContext


class ObservabilityManager:
    """Central manager for the observability system."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.event_logger = self._create_event_logger()
        self.request_manager = RequestContextManager(
            cleanup_interval=self.config.get("cleanup_interval", 300)
        )
        self.stream_processor = StreamProcessor()
        self.health_monitor = HealthMonitor(
            check_interval=self.config.get("health_check_interval", 30)
        )
        self.health_api = HealthStatusAPI(self.health_monitor.health_manager)
        self._streams_initialized = False
        self._health_monitoring_started = False

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

    async def _initialize_streams(self) -> None:
        """Initialize streaming transports from configuration."""
        if self._streams_initialized:
            return

        logging_config = self.config.get("logging", {})
        streams_config = logging_config.get("streams", [])

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
            await self.emit_conversation_event(
                ConversationEvents.REQUEST_RECEIVED,
                level=EventLevel.INFO,
                request_context=context,
                description=f"Request {context.id} received",
            )

            try:
                yield context

                # Emit request completed event - context automatically available!
                await self.emit_conversation_event(
                    ConversationEvents.REQUEST_COMPLETED,
                    level=EventLevel.INFO,
                    request_context=context,
                    description=f"Request {context.id} completed in {context.duration_ms}ms",
                )

            except Exception as e:
                # Emit request failed event - context automatically available!
                await self.emit_conversation_event(
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
            await self._emit_to_streams(
                event_type, level, data, None, None, description, event_id
            )

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
            # Build event structure compatible with Phase 1 format
            event = {
                "id": event_id,
                "timestamp": int(__import__('time').time() * 1000),
                "level": level.value,
                "muxi_version": self.config.get("muxi_version", "1.0.0"),
                "server": self._get_server_id(),
                "event": event_type.value if hasattr(event_type, 'value') else str(event_type),
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
        import socket
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
