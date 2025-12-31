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
        # Thread safety lock for event_streams access
        self._lock = threading.Lock()

    def enable_streaming(self, request_id: str, user_id: str, session_id: str):
        """Enable streaming with ownership tracking"""
        with self._lock:
            if request_id not in self.event_streams:
                self.event_streams[request_id] = {
                    "owner": (user_id, session_id),
                    "events": []
                }

    def emit_event(self, request_id: str, event_type: str, content: str, **metadata):
        """Simple event storage - just in-memory dict/list operations"""
        with self._lock:
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
        # Validate access and get initial state under lock
        with self._lock:
            if request_id not in self.event_streams:
                return

            stream_data = self.event_streams[request_id]
            if stream_data["owner"] != (user_id, session_id):
                return  # Unauthorized

            # Start watching from NOW (ignore existing events)
            last_seen = len(stream_data["events"])

        # Yield only NEW events as they arrive
        while True:
            # Copy new events to local list under lock
            new_events_to_yield = []
            terminal_event_seen = False

            with self._lock:
                # Check if stream still exists
                if request_id not in self.event_streams:
                    return

                current_events = self.event_streams[request_id]["events"]
                if len(current_events) > last_seen:
                    # Copy new events to local list
                    new_events_to_yield = current_events[last_seen:].copy()
                    last_seen = len(current_events)

                    # Check for terminal events
                    for event in new_events_to_yield:
                        event_type = event.get("type")
                        if event_type in ("completed", "failed", "cancelled"):
                            terminal_event_seen = True
                            break

            # Yield events outside the lock to avoid blocking
            for event in new_events_to_yield:
                yield event

            # Clean up after terminal event
            if terminal_event_seen:
                self.disable_streaming(request_id)
                return

            await asyncio.sleep(0.1)  # Brief polling

    def disable_streaming(self, request_id: str):
        """Cleanup when request completes"""
        with self._lock:
            if request_id in self.event_streams:
                del self.event_streams[request_id]

    def is_streaming_enabled(self, request_id: str) -> bool:
        """Check if streaming is enabled for a request"""
        with self._lock:
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
# LLM REPHRASING
# ===================================================================

async def rephrase_with_llm(
    event_type: str,
    content: str,
    metadata: Dict[str, Any],
    llm_config: Dict[str, Any]
) -> str:
    """
    Rephrase streaming events using LLM for better user experience.

    Returns rephrased content as internal monologue in user's language.

    TODO: Future enhancement - consider streaming LLM tokens as they arrive instead
    of waiting for complete response. This would make the system feel more
    responsive, especially for longer rephrased messages. Would require:
    - Switching to streaming LLM generation
    - Emitting incremental events for each token chunk
    - Client-side handling of incremental updates
    """
    try:
        from ..services.llm import LLM

        # Extract context from metadata
        stage = metadata.get('stage', '')
        original_message = metadata.get('original_message', '')

        # Build context-aware prompt
        # For planning events (especially decomposition), we want full detail
        if event_type == "planning" and metadata.get("stage") == "decomposition_complete":
            prompt = (
                "You are an AI assistant's internal thought process. "
                "Rephrase the following task decomposition plan as an internal monologue.\n\n"
                "CRITICAL RULES:\n"
                "1. Write as if thinking to yourself (first person: \"I need to...\", \"Let me...\")\n"
                "2. Communicate the FULL plan - this is important information for the user\n"
                "3. Match the user's language (detect from their message if available)\n"
                "4. Sound natural and conversational, not robotic\n"
                "5. Preserve all task details and structure\n\n"
            )
        else:
            prompt = (
                "You are an AI assistant's internal thought process. "
                "Rephrase the following progress update as a brief internal monologue.\n\n"
                "CRITICAL RULES:\n"
                "1. Write as if thinking to yourself (first person: \"I need to...\", \"Let me...\")\n"
                "2. Be concise - maximum 1-2 paragraphs\n"
                "3. Match the user's language (detect from their message if available)\n"
                "4. Sound natural and conversational, not robotic\n"
                "5. Use the metadata context to be specific when possible\n\n"
            )

        prompt += (
            f"Event Type: {event_type}\n"
            f"Stage: {stage}\n"
            f"Original Update: {content}\n"
            f"User's Message: {original_message[:500] if original_message else 'Not available'}\n\n"
            "Additional Context:\n"
        )

        # Add relevant metadata to prompt
        if metadata.get('task_count'):
            prompt += f"- Breaking down into {metadata['task_count']} tasks\n"
        if metadata.get('agent_name'):
            prompt += f"- Using agent: {metadata['agent_name']}\n"
        if metadata.get('service'):
            prompt += f"- Using service: {metadata['service']}\n"
        if metadata.get('complexity_score'):
            prompt += f"- Complexity: {metadata['complexity_score']}/10\n"
        if metadata.get('selected_agent'):
            prompt += f"- Selected: {metadata['selected_agent']}\n"

        # Different ending for decomposition vs other events
        if event_type == "planning" and metadata.get("stage") == "decomposition_complete":
            prompt += "\nRephrase as an internal monologue explaining the full plan:"
        else:
            prompt += "\nRephrase as a brief internal monologue:"

        # Initialize LLM with streaming model config
        llm = LLM(
            model=llm_config['model'],
            api_key=llm_config.get('api_key'),
            **llm_config.get('settings', {})
        )

        # Adjust max_tokens based on event type
        # Planning events (especially decomposition) need more tokens for full details
        max_tokens = 500 if (event_type == "planning" and metadata.get("stage") == "decomposition_complete") else 50

        # Generate rephrased content
        rephrased = await llm.generate_text(
            prompt,
            max_tokens=max_tokens,
            temperature=0.7
        )

        # Clean up the response
        rephrased = rephrased.strip()

        return rephrased

    except Exception:
        # On any error, return original content
        # This ensures streaming continues even if LLM fails
        return content


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
        from .observability.context import get_current_request_context
        request_context = get_current_request_context()

        # Only emit if we have a request_id in context
        if not (request_context and hasattr(request_context, 'id')):
            return

        # Check if streaming is enabled for this request
        # This prevents unnecessary LLM calls and event emissions
        if not streaming_manager.is_streaming_enabled(request_context.id):
            return

        # Get the streaming configuration (for future LLM rephrasing)
        llm_config = get_streaming_llm_config()

        # Check if progress events are disabled (only stream final content)
        if llm_config and not llm_config.get('progress', True):
            # When progress is false, only emit terminal events (final response)
            # Allow: completed, content, finalizing (events with actual response)
            # Block: progress, thinking, planning (intermediate progress events)
            terminal_events = ('completed', 'content', 'finalizing', 'failed', 'cancelled')
            if event_type not in terminal_events:
                return  # Skip all progress/thinking/planning events to save on LLM costs

        @multitasking.task
        def _emit_in_background(manager, req_id, evt_type, evt_content, evt_metadata, config):
            try:
                # Check if LLM rephrasing is enabled
                # NEVER rephrase final content events - these should be passed through unchanged
                # Also skip rephrasing if explicitly requested via metadata
                # Skip 'progress' and 'planning' events to avoid semantic cache returning same content
                # Only 'thinking' events get rephrased (the first contextual event)
                skip_rephrase = evt_metadata.get('skip_rephrase', False)
                exclude_types = ('completed', 'content', 'finalizing', 'progress', 'planning')
                if config and config.get('enabled', False) and evt_type not in exclude_types and not skip_rephrase:
                    # Phase 2: LLM rephrasing for progress/thinking events only
                    # Run async function in sync context
                    rephrased = evt_content  # Default to original content

                    try:
                        # Check if there's already an event loop running
                        try:
                            loop = asyncio.get_running_loop()
                            # If we're in an async context, this shouldn't happen in our thread
                            # but handle it gracefully
                            rephrased = evt_content
                        except RuntimeError:
                            # No event loop running, create one for this thread
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                            try:
                                # Run the coroutine in the new event loop
                                # Directly pass the coroutine to run_until_complete
                                result = loop.run_until_complete(
                                    rephrase_with_llm(evt_type, evt_content, evt_metadata, config)
                                )

                                if result:  # Only use result if it's not None/empty
                                    rephrased = result

                            except Exception:
                                # Rephrasing failed, keep default
                                pass
                            finally:
                                # Clean up the event loop
                                loop.close()
                                asyncio.set_event_loop(None)

                    except Exception:
                        # Any other exception, use default
                        pass

                    # Emit rephrased content (either rephrased or original)
                    manager.emit_event(req_id, evt_type, rephrased, **evt_metadata)
                else:
                    # Phase 1: Direct emission (no rephrasing)
                    manager.emit_event(req_id, evt_type, evt_content, **evt_metadata)

            except Exception:
                # Silent failure like observability
                pass

        # Start the background task with all parameters explicit (NOW SYNCHRONOUS)
        _emit_in_background(
            streaming_manager,
            request_context.id,
            event_type,
            content,
            metadata,
            llm_config
        )

    except Exception:  # as e:
        # Show the actual exception for debugging
        # print(f"[STREAM ERROR DEBUG] Exception in stream(): {e}")
        # import traceback
        # print(f"[STREAM ERROR DEBUG] Traceback: {traceback.format_exc()}")
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
