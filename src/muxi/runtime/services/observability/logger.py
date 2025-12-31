"""
MUXI Observability Event Logger

This module contains the EventLogger class for handling event emission
with configurable outputs and routing.
"""

import json
import socket
import time
from typing import Any, Dict, List, Optional, Union

import requests

from ...datatypes.observability import (
    ConversationEvents,
    SystemEvents,
    ErrorEvents,
    ServerEvents,
    APIEvents,
    EventLevel,
    RequestContext,
)
from ...utils.user_dirs import get_observability_dir
from ...utils.id_generator import generate_nanoid
from ...utils.version import get_version


class EventLogger:
    """Central event logging component with configurable outputs.

    Two-tier logging architecture:
    - System events (SystemEvents, ErrorEvents, ServerEvents, APIEvents) -> system_destination
    - Conversation events (ConversationEvents) -> configured output (file, stdout, stream, trail)
    """

    def __init__(
        self,
        level: EventLevel = EventLevel.INFO,
        output: str = "stdout",
        output_config: Optional[Dict[str, Any]] = None,
        events: Optional[List[str]] = None,
        system_level: str = "debug",
        system_destination: str = "stdout",
    ):
        # Conversation event configuration
        self.level = level
        self.output = output
        self.output_config = output_config or {}
        self.events = set(events) if events else None

        # System event configuration
        self.system_level = self._parse_level(system_level)
        self.system_destination = system_destination
        self._system_file_handle = None

        # Server ready flag - when False, skip JSONL output to stdout
        # This prevents cluttering console during startup
        self._server_ready = False

        self.muxi_version = get_version()
        self._server_id = self._get_server_id()

    def set_server_ready(self, ready: bool = True) -> None:
        """Mark server as ready to enable JSONL output to stdout."""
        self._server_ready = ready

    def _parse_level(self, level_str: str) -> EventLevel:
        """Parse level string to EventLevel enum."""
        level_map = {
            "debug": EventLevel.DEBUG,
            "info": EventLevel.INFO,
            "warning": EventLevel.WARNING,
            "warn": EventLevel.WARNING,
            "error": EventLevel.ERROR,
        }
        return level_map.get(level_str.lower(), EventLevel.DEBUG)

    def _get_server_id(self) -> str:
        """Get server identifier for event tracking."""
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def _should_emit_event(
        self,
        event_type: Union[ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents, str],
        event_type_str: str,
        level: EventLevel
    ) -> bool:
        """Check if event should be emitted based on configuration.

        Uses different level checks for system vs conversation events:
        - System events: Check against system_level
        - Conversation events: Check against self.level and events filter
        """
        level_priority = {
            EventLevel.DEBUG: 0,
            EventLevel.INFO: 1,
            EventLevel.WARNING: 2,
            EventLevel.ERROR: 3,
        }

        # System events use system_level
        if isinstance(event_type, (SystemEvents, ErrorEvents, ServerEvents, APIEvents)):
            if level_priority[level] < level_priority[self.system_level]:
                return False
            return True

        # Conversation events use conversation level and events filter
        if level_priority[level] < level_priority[self.level]:
            return False

        # Check specific event filter (wildcard '*' allows all events)
        if self.events is not None and '*' not in self.events and event_type_str not in self.events:
            return False

        return True

    def emit_event(
        self,
        event_type: Union[ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents, str],
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        request_context: Optional[RequestContext] = None,
        parent_event_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """Emit an observability event with structured data."""
        # Handle different event types
        if isinstance(event_type, (ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents)):
            event_type_str = event_type.value
        else:
            event_type_str = event_type

        if not self._should_emit_event(event_type, event_type_str, level):
            return ""

        # Generate event ID
        event_id = f"evt_{generate_nanoid()}"

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
            event["session_id"] = request_context.session_id or None
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
        self._emit_to_output(event, event_type)

        return event_id

    def _emit_to_output(
        self,
        event: Dict[str, Any],
        event_type: Union[
            ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents, str
        ],
    ) -> None:
        """Emit event to the configured output destination.

        Two-tier routing:
        - SystemEvents, ErrorEvents, ServerEvents, APIEvents -> system_destination
        - ConversationEvents -> configured output (file, stdout, stream, trail)
        """
        try:
            # JSON-L format for easy parsing
            event_line = json.dumps(event, separators=(",", ":"))

            # Route SystemEvents, ServerEvents, APIEvents and ErrorEvents to system_destination
            if isinstance(event_type, (SystemEvents, ErrorEvents, ServerEvents, APIEvents)):
                self._emit_to_system(event_line)
                return

            # Route ConversationEvents to configured output
            if self.output == "stdout":
                print(event_line, flush=True)
            elif self.output == "file":
                self._emit_to_file(event_line)
            elif self.output == "stream":
                self._emit_to_stream(event_line)
            elif self.output == "trail":
                self._emit_to_trail(event_line)

        except Exception:
            # Silent failures to avoid disrupting main application flow
            pass

    def _emit_to_system(self, event_line: str) -> None:
        """Emit system event to system_destination (stdout or file path).

        When system_destination is stdout:
        - Skip JSONL output during startup (before server is ready)
        - Once server is ready, emit JSONL to stdout normally

        This prevents cluttering console during initialization while
        still providing full observability after server starts.
        """
        if self.system_destination == "stdout":
            # Only emit to stdout after server is ready
            if self._server_ready:
                print(event_line, flush=True)
            return

        # File path - write to system log file
        try:
            with open(self.system_destination, "a") as f:
                f.write(event_line + "\n")
                f.flush()
        except Exception:
            # Fallback to stdout if file write fails (only when server ready)
            if self._server_ready:
                print(event_line, flush=True)

    def _emit_to_file(self, event_line: str) -> None:
        """Emit event to file output."""
        file_path = self.output_config.get("path", f"{get_observability_dir()}/muxi.jsonl")
        with open(file_path, "a") as f:
            f.write(event_line + "\n")
            f.flush()  # Ensure immediate write

    def _emit_to_stream(self, event_line: str) -> None:
        """Emit event to stream output."""
        stream_url = self.output_config.get("url")
        if not stream_url:
            return

        try:
            requests.post(
                stream_url,
                data=event_line + "\n",
                headers={"Content-Type": "application/x-ndjson"},
                timeout=5,
            )
        except Exception:
            # Silent failure for external stream connectivity issues
            pass

    def _emit_to_trail(self, event_line: str) -> None:
        """Emit event to MUXI trail output."""
        trail_config = self.output_config.get("trail", {})
        trail_url = trail_config.get("url")

        if not trail_url:
            return

        try:
            headers = {"Content-Type": "application/x-ndjson"}

            # Add authentication if configured
            if api_key := trail_config.get("api_key"):
                headers["Authorization"] = f"Bearer {api_key}"

            requests.post(
                trail_url,
                data=event_line + "\n",
                headers=headers,
                timeout=10,
            )
        except Exception:
            # Silent failure for external trail connectivity issues
            pass
