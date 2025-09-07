"""
Streaming Events System for MUXI Runtime

Provides real-time event streaming with owner-based security and clean separation
between event storage and subscription/transport mechanisms.
"""

import asyncio
import time
import threading
import signal
from typing import Dict, Optional, Any
import multitasking

# Set multitasking to thread mode for shared memory access
multitasking.set_engine("thread")

# Kill all tasks on ctrl-c for clean shutdown
# Only register signal handlers in main thread to avoid errors in tests
try:
    signal.signal(signal.SIGINT, multitasking.killall)
except ValueError:
    # Signal handlers can only be registered in main thread
    # This is expected in tests or when imported from threads
    pass


class StreamingManager:
    """Pure event storage with owner-based security"""

    def __init__(self):
        # Key: request_id, Value: owner + events
        self.event_streams: Dict[str, Dict] = {}

    def enable_streaming(self, request_id: str, user_id: str, session_id: str):
        """Enable streaming with ownership tracking"""
        if request_id not in self.event_streams:
            self.event_streams[request_id] = {
                "owner": (user_id, session_id),
                "events": []
            }

    def emit_event(self, request_id: str, event_type: str, content: str, **metadata):
        """Simple event storage - just in-memory dict/list operations"""
        if request_id not in self.event_streams:
            return  # Not streaming-enabled

        stream_data = self.event_streams[request_id]
        user_id, session_id = stream_data["owner"]

        event = {
            "request_id": request_id,
            "user_id": user_id,
            "session_id": session_id,
            "type": event_type,
            "content": content,
            "timestamp": time.time(),
            **metadata
        }

        # Just append to events list (fast in-memory operation)
        stream_data["events"].append(event)

    async def subscribe(self, request_id: str, user_id: str, session_id: str):
        """
        Generator that yields NEW events only.
        Real-time streaming - no replay of existing events.
        """
        # Validate access
        if request_id not in self.event_streams:
            return

        stream_data = self.event_streams[request_id]
        if stream_data["owner"] != (user_id, session_id):
            return  # Unauthorized

        # Start watching from NOW (ignore existing events)
        last_seen = len(stream_data["events"])

        # Yield only NEW events as they arrive
        while request_id in self.event_streams:
            current_events = self.event_streams[request_id]["events"]
            if len(current_events) > last_seen:
                # New events since last check
                for event in current_events[last_seen:]:
                    yield event
                last_seen = len(current_events)

            await asyncio.sleep(0.1)  # Brief polling

    def disable_streaming(self, request_id: str):
        """Cleanup when request completes"""
        if request_id in self.event_streams:
            del self.event_streams[request_id]

    def is_streaming_enabled(self, request_id: str) -> bool:
        """Check if streaming is enabled for a request"""
        return request_id in self.event_streams


# ===================================================================
# GLOBAL STREAMING CONFIGURATION
# ===================================================================

# Global instance
streaming_manager = StreamingManager()

# Global runtime variable to store LLM configuration for streaming
_streaming_llm_config: Optional[Dict[str, Any]] = None
_streaming_llm_config_lock = threading.Lock()


def set_streaming_llm_config(config: Dict[str, Any]) -> None:
    """Set the streaming LLM configuration for global access."""
    global _streaming_llm_config
    with _streaming_llm_config_lock:
        _streaming_llm_config = config


def get_streaming_llm_config() -> Optional[Dict[str, Any]]:
    """Get the streaming LLM configuration."""
    with _streaming_llm_config_lock:
        return _streaming_llm_config


# ===================================================================
# STREAMING API
# ===================================================================

def stream(event_type: str, content: str, **metadata):
    """
    Emit a streaming event (non-blocking).

    This function captures the request context before spawning a background
    thread to ensure context is properly passed to the thread.

    Args:
        event_type: Type of event (thinking, planning, progress, etc.)
        content: Event content/message
        **metadata: Additional event metadata
    """
    try:
        # Get request context
        from ..observability.context import get_current_request_context
        request_context = get_current_request_context()

        # Only emit if we have a request_id in context
        if not (request_context and hasattr(request_context, 'request_id')):
            return

        # Check if streaming is enabled for this request
        # This prevents unnecessary LLM calls and event emissions
        if not streaming_manager.is_streaming_enabled(request_context.request_id):
            return

        # Get the streaming configuration (for future LLM rephrasing)
        llm_config = get_streaming_llm_config()

        @multitasking.task
        def _emit_in_background(manager, req_id, evt_type, evt_content, evt_metadata, config):
            try:
                # Phase 1: Direct emission (current implementation)
                # Use all parameters passed explicitly - no closure dependencies
                manager.emit_event(req_id, evt_type, evt_content, **evt_metadata)

                # Phase 2: LLM rephrasing will go here
                # if config and config.get('enabled'):
                #     rephrased = await rephrase_with_llm(evt_content, config)
                #     manager.emit_event(req_id, evt_type, rephrased, **evt_metadata)

            except Exception:
                # Silent failure like observability
                pass

        # Start the background task with all parameters explicit
        _emit_in_background(
            streaming_manager,
            request_context.request_id,
            event_type,
            content,
            metadata,
            llm_config
        )

    except Exception:
        # Silent failure like observability
        pass


# Helper functions
def enable_streaming(request_id: str, user_id: str, session_id: str):
    """Enable streaming for a request"""
    streaming_manager.enable_streaming(request_id, user_id, session_id)


def disable_streaming(request_id: str):
    """Disable streaming and cleanup"""
    streaming_manager.disable_streaming(request_id)


async def subscribe(request_id: str, user_id: str, session_id: str):
    """Subscribe to real-time events"""
    async for event in streaming_manager.subscribe(request_id, user_id, session_id):
        yield event
