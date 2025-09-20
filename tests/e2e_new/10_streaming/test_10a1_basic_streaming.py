#!/usr/bin/env python3
"""
Test 10A1: Basic Streaming

Tests that streaming events are properly emitted for simple requests.
"""

import sys

from .base_streaming_test import BaseStreamingTest
def main():
    """Test basic streaming functionality."""
    test = BaseStreamingTest("10a1_basic_streaming", "Test basic streaming functionality")

    async def run_streaming_test():
        # Setup formation using the shared streaming formation
        await test.setup_formation(yaml_name="formation-streaming.yaml")

        # Test basic streaming
        result = await test.test_basic_streaming(
            message="What are the key principles of quantum computing?",
            user_id="test_user",
            session_id="streaming_test_10a1",
            expected_keywords=["quantum", "computing", "principles"],
            timeout=30.0
        )

        # Record result
        test.results.append(result["success"])

        if result["success"]:
            test.formatter.print_success("Basic streaming test passed")

            # Print content analysis
            content_analysis = result["content_analysis"]
            test.formatter.print_section("Content Analysis")
            test.formatter.print_info(f"Total events: {content_analysis['total_events']}")
            test.formatter.print_info(f"Content events: {content_analysis['content_events']}")
            test.formatter.print_info(f"Total content length: {content_analysis['total_content_length']} chars")

            if content_analysis.get("found_keywords"):
                test.formatter.print_info(f"Found keywords: {content_analysis['found_keywords']}")

            # Print timing analysis
            timing_analysis = result["timing_analysis"]
            test.formatter.print_section("Timing Analysis")
            test.formatter.print_info(f"Average interval: {timing_analysis['avg_interval']:.3f}s")
            test.formatter.print_info(f"Total duration: {timing_analysis['total_duration']:.2f}s")

        else:
            test.formatter.print_failure("Basic streaming test failed")

            if not result["is_stream"]:
                test.formatter.print_error("Response was not a stream")
            else:
                content_analysis = result.get("content_analysis", {})
                if content_analysis.get("error_events", 0) > 0:
                    test.formatter.print_error(f"Stream had {content_analysis['error_events']} error events")

        # Print streaming-specific summary
        test.print_streaming_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if result["success"] else 1

    return test.run_in_event_loop(
        "10a1_basic_streaming",
        "Test basic streaming functionality",
        "10_streaming",
        [],  # We handle test cases manually
        None,  # Use pattern-based formation path
        "formation-streaming.yaml",  # Use shared formation
    )
if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
