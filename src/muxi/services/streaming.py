"""
Streaming Events System for MUXI Runtime

Provides real-time event streaming with owner-based security and clean separation
between event storage and subscription/transport mechanisms.
"""

import asyncio
import time
from typing import Dict


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


# Global instance
streaming_manager = StreamingManager()


# Simple synchronous streaming emission (no multitasking needed)
def stream(event_type: str, content: str, **metadata):
    """
    Simple streaming emission - just in-memory operations.
    Call from anywhere, just like observability.observe()
    Automatically gets request_id from context.
    """
    try:
        # Get request_id from context
        from ..observability.context import get_current_request_context
        context = get_current_request_context()

        # Only emit if we have a request_id in context
        if context and hasattr(context, 'request_id'):
            streaming_manager.emit_event(context.request_id, event_type, content, **metadata)
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
