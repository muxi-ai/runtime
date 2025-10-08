#!/usr/bin/env python3
"""
Test 10A1: Basic Streaming

Tests that streaming events are properly emitted for simple requests.
"""

import asyncio
import sys
from pathlib import Path

from .base_streaming_test import BaseStreamingTest


def main():
    """Test basic streaming functionality."""
    test = BaseStreamingTest("10a1_basic_streaming", "Test basic streaming functionality")

    async def run_streaming_test():
        # Setup formation using the shared streaming formation
        formation_path = Path(__file__).parent / "formations" / "formation-streaming"
        await test.setup_formation(formation_path=str(formation_path))

        # Test basic streaming
        # Now that we properly extract content from "completed" events,
        # we should get actual answer content with relevant keywords
        result = await test.test_basic_streaming(
            message="What are the key principles of quantum computing?",
            user_id="test_user",
            session_id="streaming_test_10a1",
            expected_keywords=["quantum"],  # Just check for quantum (lenient like original)
            timeout=60.0,  # Allow time for full stream including content
        )

        # Record result
        test.results.append(result["success"])

        if result["success"]:
            test.formatter.print_success("Basic streaming test passed")

            # Print content analysis
            content_analysis = result["content_analysis"]
            print("\n" + "=" * 60); print("Content Analysis"); print("=" * 60)
            test.formatter.print_debug(f"Total events: {content_analysis['total_events']}")
            test.formatter.print_debug(f"Content events: {content_analysis['content_events']}")
            test.formatter.print_debug(
                f"Total content length: {content_analysis['total_content_length']} chars"
            )

            if content_analysis.get("found_keywords"):
                test.formatter.print_debug(f"Found keywords: {content_analysis['found_keywords']}")

            # Print timing analysis
            timing_analysis = result["timing_analysis"]
            print("\n" + "=" * 60); print("Timing Analysis"); print("=" * 60)
            test.formatter.print_debug(f"Average interval: {timing_analysis['avg_interval']:.3f}s")
            test.formatter.print_debug(f"Total duration: {timing_analysis['total_duration']:.2f}s")

        else:
            test.formatter.print_failure("Basic streaming test failed")

            if not result["is_stream"]:
                test.formatter.print_error("Response was not a stream")
            else:
                content_analysis = result.get("content_analysis", {})
                if content_analysis.get("error_events", 0) > 0:
                    test.formatter.print_error(
                        f"Stream had {content_analysis['error_events']} error events"
                    )

        # Print streaming-specific summary
        test.print_streaming_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if result["success"] else 1

    return asyncio.run(run_streaming_test())


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
