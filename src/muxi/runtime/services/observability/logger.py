"""
MUXI Observability Event Logger

This module contains the EventLogger class for handling event emission
with configurable outputs and routing.
"""

import atexit
import queue
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Union

import requests

from ...datatypes.observability import (
    APIEvents,
    ConversationEvents,
    ErrorEvents,
    EventLevel,
    RequestContext,
    ServerEvents,
    SystemEvents,
)
from ...utils.fastjson import json
from ...utils.id_generator import generate_nanoid
from ...utils.user_dirs import get_observability_dir
from ...utils.version import get_version


class EventLogger:
    """Central event logging component with configurable outputs.

    Two-tier logging architecture:
    - System events (SystemEvents, ErrorEvents, ServerEvents, APIEvents) -> system_destination
    - Conversation events (ConversationEvents) -> configured output (file, stdout, stream, trail)

    File and network destinations are written by a single background
    writer thread fed through a queue, so emitters never block on disk
    or HTTP. stdout destinations stay synchronous to preserve console
    ordering.
    """

    # Max events drained per write batch by the background writer
    _WRITER_BATCH_MAX = 100

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

        # Background writer state, created lazily on first non-stdout
        # write so stdout-only loggers never spawn a thread
        self._write_queue: Optional[queue.Queue] = None
        self._writer_start_lock = threading.Lock()

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
        event_type: Union[
            ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents, str
        ],
        event_type_str: str,
        level: EventLevel,
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
        if self.events is not None and "*" not in self.events and event_type_str not in self.events:
            return False

        return True

    def should_emit(
        self,
        event_type: Union[
            ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents, str
        ],
        level: EventLevel,
    ) -> bool:
        """Cheap pre-check: would ``emit_event`` emit this event?

        Exposed so hot-path callers (``observe``) can drop filtered
        events before paying for payload redaction and the background
        emission thread.
        """
        if isinstance(
            event_type, (ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents)
        ):
            event_type_str = event_type.value
        else:
            event_type_str = event_type
        return self._should_emit_event(event_type, event_type_str, level)

    def emit_event(
        self,
        event_type: Union[
            ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents, str
        ],
        level: EventLevel = EventLevel.INFO,
        data: Optional[Dict[str, Any]] = None,
        request_context: Optional[RequestContext] = None,
        parent_event_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """Emit an observability event with structured data."""
        # Handle different event types
        if isinstance(
            event_type, (ConversationEvents, SystemEvents, ErrorEvents, ServerEvents, APIEvents)
        ):
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
                # ``TokenUsage.to_dict`` emits the self-documenting
                # ``fields`` legend alongside the array values so
                # consumers know which position is total/input/output/
                # cached without reading the source. See manager.py for
                # the same fix.
                "tokens": request_context.tokens.to_dict(),
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
            elif self.output in ("file", "stream", "trail"):
                self._enqueue_write(self.output, event_line)

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

        # File path - write via the background writer
        self._enqueue_write("system_file", event_line)

    def _enqueue_write(self, kind: str, event_line: str) -> None:
        """Queue an event line for the background writer thread."""
        if self._write_queue is None:
            with self._writer_start_lock:
                if self._write_queue is None:
                    write_queue: queue.Queue = queue.Queue()
                    writer = threading.Thread(
                        target=self._writer_loop,
                        args=(write_queue,),
                        name="muxi-event-writer",
                        daemon=True,
                    )
                    # Publish the queue only after the thread exists so
                    # concurrent emitters never enqueue into a queue
                    # nothing will ever drain
                    self._write_queue = write_queue
                    writer.start()
                    atexit.register(self.flush)
        self._write_queue.put((kind, event_line))

    def _writer_loop(self, write_queue: queue.Queue) -> None:
        """Drain the write queue in batches, grouped by destination.

        A single writer thread owns all file appends and HTTP posts, so
        emitters never block on I/O, per-destination ordering is FIFO,
        and the HTTP session reuses connections across events.
        """
        session = requests.Session()
        try:
            while True:
                items = [write_queue.get()]
                while len(items) < self._WRITER_BATCH_MAX:
                    try:
                        items.append(write_queue.get_nowait())
                    except queue.Empty:
                        break

                grouped: Dict[str, List[str]] = {}
                for kind, event_line in items:
                    grouped.setdefault(kind, []).append(event_line)

                for kind, event_lines in grouped.items():
                    try:
                        self._write_batch(kind, event_lines, session)
                    except Exception:
                        # Transport failures must never disrupt the runtime
                        pass

                for _ in items:
                    write_queue.task_done()
        finally:
            # Return pooled connections/TLS sockets cleanly if the loop
            # ever exits (e.g. a non-Exception raise)
            session.close()

    def _write_batch(self, kind: str, event_lines: List[str], session: requests.Session) -> None:
        """Write one batch of JSON-L lines to a single destination."""
        payload = "\n".join(event_lines) + "\n"

        if kind == "file":
            file_path = self.output_config.get("path", f"{get_observability_dir()}/muxi.jsonl")
            with open(file_path, "a") as f:
                f.write(payload)
        elif kind == "system_file":
            try:
                with open(self.system_destination, "a") as f:
                    f.write(payload)
            except Exception:
                # Fallback to stdout if file write fails (only when server ready)
                if self._server_ready:
                    print(payload, end="", flush=True)
        elif kind == "stream":
            stream_url = self.output_config.get("url")
            if stream_url:
                session.post(
                    stream_url,
                    data=payload,
                    headers={"Content-Type": "application/x-ndjson"},
                    timeout=5,
                )
        elif kind == "trail":
            trail_config = self.output_config.get("trail", {})
            trail_url = trail_config.get("url")
            if trail_url:
                headers = {"Content-Type": "application/x-ndjson"}
                # Add authentication if configured
                if api_key := trail_config.get("api_key"):
                    headers["Authorization"] = f"Bearer {api_key}"
                session.post(trail_url, data=payload, headers=headers, timeout=10)

    def flush(self, timeout: float = 2.0) -> None:
        """Best-effort wait for queued events to reach their destination.

        Registered via atexit so tail events are not lost on shutdown;
        also useful in tests to assert on written output.
        """
        write_queue = self._write_queue
        if write_queue is None:
            return
        # Timed join: Queue.join() has no timeout parameter, so run it in
        # a short-lived helper thread and bound the wait by joining that
        # thread. Wakes as soon as the last task_done() fires.
        joiner = threading.Thread(target=write_queue.join, daemon=True)
        joiner.start()
        joiner.join(timeout=timeout)
