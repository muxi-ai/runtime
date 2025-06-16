"""
MUXI Observability Manager

This module contains the ObservabilityManager class which provides
the central coordination for the observability system.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from .logger import EventLogger
from .request_manager import RequestContextManager
from .types import ConversationEvents, SystemEvents, EventLevel, RequestContext


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
            await self.event_logger.observe(
                ConversationEvents.REQUEST_RECEIVED,
                level=EventLevel.INFO,
                request_context=context,
                description=f"Request {context.id} received",
            )

            try:
                yield context

                # Emit request completed event - context automatically available!
                await self.event_logger.observe(
                    ConversationEvents.REQUEST_COMPLETED,
                    level=EventLevel.INFO,
                    request_context=context,
                    description=f"Request {context.id} completed in {context.duration_ms}ms",
                )

            except Exception as e:
                # Emit request failed event - context automatically available!
                await self.event_logger.observe(
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
        return await self.event_logger.observe(
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
        return await self.event_logger.observe(
            event_type=event_type,
            level=level,
            data=data,
            request_context=None,  # System events don't have request context
            parent_event_id=None,
            description=description,
        )
