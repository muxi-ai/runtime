"""
Base test class for Area 10 - Streaming tests.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncIterator

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.base import BaseE2ETest  # noqa: E402


class BaseStreamingTest(BaseE2ETest):
    """
    Base class for streaming tests.

    Provides:
    - Stream consumption and analysis
    - Event timing and ordering verification
    - Content quality assessment
    - Progress tracking validation
    - Stream interruption testing
    """

    def __init__(self, test_name: str, test_description: str):
        super().__init__(test_name, test_description, "10_streaming")

        # Streaming-specific state
        self.stream_events = []
        self.stream_timing = []
        self.stream_errors = []

    async def consume_stream(
        self,
        stream: AsyncIterator,
        max_events: Optional[int] = None,
        timeout: Optional[float] = 30.0,
    ) -> Dict[str, Any]:
        """
        Consume a stream and analyze its events.

        Args:
            stream: The async iterator stream
            max_events: Maximum number of events to consume
            timeout: Total timeout for stream consumption

        Returns:
            Dict with stream analysis results
        """
        events = []
        timing = []
        start_time = time.time()

        self.formatter.print_debug("Starting stream consumption...")

        try:
            # Python 3.10 compatible timeout handling
            async def consume_with_timeout():
                async for chunk in stream:
                    event_time = time.time()
                    events.append(chunk)
                    timing.append(event_time - start_time)

                    # Print first few chunks for debugging
                    if len(events) <= 3:
                        if isinstance(chunk, dict):
                            preview = f"{chunk.get('type', 'unknown')} - {chunk.get('content', str(chunk)[:50])}"
                        else:
                            preview = str(chunk)[:50]
                        self.formatter.print_debug(f"Stream chunk {len(events)}: {preview}")

                    # Stop if we hit max events
                    if max_events and len(events) >= max_events:
                        break

            if timeout:
                await asyncio.wait_for(consume_with_timeout(), timeout=timeout)
            else:
                await consume_with_timeout()

        except asyncio.TimeoutError:
            self.formatter.print_warning(f"Stream consumption timed out after {timeout}s")
        except Exception as e:
            self.formatter.print_error(f"Stream consumption error: {e}")
            self.stream_errors.append(str(e))

        end_time = time.time()
        duration = end_time - start_time

        # Store for analysis
        self.stream_events.extend(events)
        self.stream_timing.extend(timing)

        result = {
            "events": events,
            "timing": timing,
            "duration": duration,
            "event_count": len(events),
            "errors": self.stream_errors.copy(),
        }

        self.formatter.print_success(f"Consumed {len(events)} stream events in {duration:.2f}s")
        return result

    def analyze_stream_content(
        self, events: List[Any], expected_keywords: List[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze stream content for quality and completeness.

        Args:
            events: List of stream events
            expected_keywords: Optional keywords to look for in content

        Returns:
            Dict with content analysis results
        """
        analysis = {
            "total_events": len(events),
            "content_events": 0,
            "progress_events": 0,
            "error_events": 0,
            "total_content_length": 0,
            "contains_keywords": False,
            "event_types": {},
        }

        full_content = ""

        for event in events:
            if isinstance(event, dict):
                event_type = event.get("type", "unknown")
                analysis["event_types"][event_type] = analysis["event_types"].get(event_type, 0) + 1

                # Content can come in multiple event types:
                # - "content": Direct content streaming
                # - "text": Text content
                # - "completed": Final response (contains full answer)
                if event_type in ("content", "text", "completed"):
                    analysis["content_events"] += 1
                    content = event.get("content", "") or event.get("text", "")
                    full_content += content
                    analysis["total_content_length"] += len(content)
                elif event_type == "progress":
                    analysis["progress_events"] += 1
                elif event_type == "error":
                    analysis["error_events"] += 1
            else:
                # Non-dict events, treat as content
                content = str(event)
                full_content += content
                analysis["total_content_length"] += len(content)
                analysis["content_events"] += 1

        # Check for expected keywords
        if expected_keywords:
            found_keywords = [kw for kw in expected_keywords if kw.lower() in full_content.lower()]
            analysis["contains_keywords"] = len(found_keywords) > 0
            analysis["found_keywords"] = found_keywords

        analysis["full_content"] = full_content
        return analysis

    def analyze_stream_timing(self, timing: List[float]) -> Dict[str, Any]:
        """
        Analyze stream timing for performance and consistency.

        Args:
            timing: List of event timestamps

        Returns:
            Dict with timing analysis
        """
        if not timing:
            return {"intervals": [], "avg_interval": 0, "max_interval": 0, "min_interval": 0}

        # Calculate intervals between events
        intervals = []
        for i in range(1, len(timing)):
            intervals.append(timing[i] - timing[i - 1])

        analysis = {
            "intervals": intervals,
            "avg_interval": sum(intervals) / len(intervals) if intervals else 0,
            "max_interval": max(intervals) if intervals else 0,
            "min_interval": min(intervals) if intervals else 0,
            "total_duration": timing[-1] - timing[0] if len(timing) > 1 else 0,
        }

        return analysis

    async def test_basic_streaming(
        self,
        message: str,
        user_id: str = "test_user",
        session_id: str = "test_session",
        expected_keywords: List[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Test basic streaming functionality.

        Args:
            message: Message to send
            user_id: User ID for the request
            session_id: Session ID for the request
            expected_keywords: Optional keywords to verify in content
            timeout: Timeout for stream consumption

        Returns:
            Dict with test results
        """
        self.formatter.print_test_case("Basic Streaming Test", message)

        # Send request with streaming enabled
        response = await self.overlord.chat(
            message=message,
            user_id=user_id,
            session_id=session_id,
            use_async=False,
            stream=True,
        )

        result = {
            "success": False,
            "is_stream": False,
            "content_analysis": {},
            "timing_analysis": {},
            "response_type": type(response).__name__,
        }

        # Check if response is a stream
        if hasattr(response, "__aiter__"):
            result["is_stream"] = True
            self.formatter.print_success("Response is an async iterator (stream)")

            # Consume the stream
            stream_result = await self.consume_stream(response, timeout=timeout)
            events = stream_result["events"]

            # Analyze content
            content_analysis = self.analyze_stream_content(events, expected_keywords)
            result["content_analysis"] = content_analysis

            # Analyze timing
            timing_analysis = self.analyze_stream_timing(stream_result["timing"])
            result["timing_analysis"] = timing_analysis

            # Determine success
            # Now that we properly extract content from "completed" events,
            # we should have actual content to validate
            success_criteria = [
                len(events) > 0,  # Got some events
                content_analysis["total_content_length"] > 0,  # Got actual content
                content_analysis["error_events"] == 0,  # No errors
            ]

            # Check keywords if provided
            if expected_keywords:
                success_criteria.append(content_analysis["contains_keywords"])

            result["success"] = all(success_criteria)

            # Store transcript with full content
            self.transcript.append((message, content_analysis["full_content"]))

        else:
            self.formatter.print_failure(f"Response is not a stream: {type(response)}")
            # Still store transcript if we got a response
            content = response.content if hasattr(response, "content") else str(response)
            self.transcript.append((message, content))

        return result

    async def test_stream_interruption(
        self,
        message: str,
        interrupt_after: float = 2.0,
        user_id: str = "test_user",
        session_id: str = "test_session",
    ) -> Dict[str, Any]:
        """
        Test stream interruption behavior.

        Args:
            message: Message to send
            interrupt_after: Time to wait before interrupting (seconds)
            user_id: User ID for the request
            session_id: Session ID for the request

        Returns:
            Dict with interruption test results
        """
        self.formatter.print_test_case(
            "Stream Interruption Test", f"Interrupt after {interrupt_after}s"
        )

        # Send request with streaming enabled
        response = await self.overlord.chat(
            message=message,
            user_id=user_id,
            session_id=session_id,
            use_async=False,
            stream=True,
        )

        result = {
            "success": False,
            "interrupted": False,
            "events_before_interrupt": 0,
            "graceful_handling": False,
        }

        if hasattr(response, "__aiter__"):
            events = []
            start_time = time.time()

            try:
                async for chunk in response:
                    events.append(chunk)
                    current_time = time.time()

                    if current_time - start_time >= interrupt_after:
                        # Simulate interruption by breaking
                        result["interrupted"] = True
                        break

                result["events_before_interrupt"] = len(events)
                result["graceful_handling"] = True  # No exception during interruption
                result["success"] = result["interrupted"] and result["graceful_handling"]

                self.formatter.print_success(f"Stream interrupted after {len(events)} events")

            except Exception as e:
                self.formatter.print_error(f"Stream interruption error: {e}")
                result["graceful_handling"] = False

        return result

    def print_streaming_summary(self):
        """Print summary specific to streaming tests."""
        print("\n" + "=" * 60)
        print("Streaming Test Summary")
        print("=" * 60)

        if self.stream_events:
            self.formatter.print_debug(f"Total stream events: {len(self.stream_events)}")

            # Analyze event types
            event_types = {}
            for event in self.stream_events:
                if isinstance(event, dict):
                    event_type = event.get("type", "unknown")
                    event_types[event_type] = event_types.get(event_type, 0) + 1

            if event_types:
                self.formatter.print_debug("Event type distribution:")
                for event_type, count in event_types.items():
                    self.formatter.print_debug(f"  {event_type}: {count}")

        if self.stream_timing:
            avg_interval = (
                sum(self.stream_timing[1:]) / (len(self.stream_timing) - 1)
                if len(self.stream_timing) > 1
                else 0
            )
            self.formatter.print_debug(f"Average event interval: {avg_interval:.3f}s")

        if self.stream_errors:
            self.formatter.print_warning(f"Stream errors encountered: {len(self.stream_errors)}")
            for error in self.stream_errors:
                self.formatter.print_debug(f"  Error: {error}")
