#!/usr/bin/env python3
"""
Test 10A6: Clarification Streaming

Tests that streaming events work correctly during clarification flow.
"""

import asyncio
import sys
from pathlib import Path

from base_streaming_test import BaseStreamingTest


def main():
    """Test streaming with clarification flow."""
    test = BaseStreamingTest("10a6_clarification_streaming", "Test streaming with clarification")

    async def run_clarification_test():
        # Setup formation using the shared streaming formation
        formation_path = Path(__file__).parent / "formations" / "formation-streaming"
        await test.setup_formation(formation_path=str(formation_path))

        user_id = "test_user"
        session_id = "streaming_clarification_test"

        # First request - incomplete, should trigger clarification
        print("\n" + "=" * 60)
        print("Test 1: Incomplete request (should trigger clarification)")
        print("=" * 60)

        response1 = await test.overlord.chat(
            message="Help me with",
            user_id=user_id,
            session_id=session_id,
            use_async=False,
            stream=True,
        )

        # Consume the first stream (should ask for clarification)
        stream1_events = []
        if hasattr(response1, "__aiter__"):
            stream_result1 = await test.consume_stream(response1, timeout=30.0)
            stream1_events = stream_result1["events"]

            # Show first few events
            for i, chunk in enumerate(stream1_events[:3], 1):
                if isinstance(chunk, dict):
                    preview = f"{chunk.get('type', 'unknown')} - {chunk.get('content', '')[:100]}"
                else:
                    preview = str(chunk)[:100]
                test.formatter.print_debug(f"Event {i}: {preview}")

        test.formatter.print_debug(f"Total events from first request: {len(stream1_events)}")

        # Check if we got a clarification request
        clarification_found = False
        for event in stream1_events:
            if isinstance(event, dict):
                content = event.get("content", "")
            else:
                content = str(event)

            # Check for clarification patterns
            if any(
                phrase in content.lower()
                for phrase in [
                    "what would you like",
                    "help you with what",
                    "can you be more specific",
                    "what do you need",
                    "could you clarify",
                    "more details",
                ]
            ):
                clarification_found = True
                test.formatter.print_success("Clarification request detected")
                break

        if not clarification_found:
            test.formatter.print_warning(
                "No explicit clarification patterns found - may have different response"
            )

        # Second request - provide clarification
        print("\n" + "=" * 60)
        print("Test 2: Providing clarification")
        print("=" * 60)

        response2 = await test.overlord.chat(
            message="debugging Python code",
            user_id=user_id,
            session_id=session_id,
            use_async=False,
            stream=True,
        )

        # Consume the second stream (should provide actual help)
        stream2_events = []
        if hasattr(response2, "__aiter__"):
            stream_result2 = await test.consume_stream(response2, timeout=30.0)
            stream2_events = stream_result2["events"]

            # Show first few events
            for i, chunk in enumerate(stream2_events[:3], 1):
                if isinstance(chunk, dict):
                    preview = f"{chunk.get('type', 'unknown')} - {chunk.get('content', '')[:100]}"
                else:
                    preview = str(chunk)[:100]
                test.formatter.print_debug(f"Event {i}: {preview}")

        test.formatter.print_debug(f"Total events from clarification response: {len(stream2_events)}")

        # Check if we got a helpful response about debugging
        helpful_response = False
        for event in stream2_events:
            if isinstance(event, dict):
                content = event.get("content", "")
            else:
                content = str(event)

            if any(
                word in content.lower()
                for word in ["debug", "python", "code", "error", "breakpoint", "trace", "print"]
            ):
                helpful_response = True
                test.formatter.print_success("Helpful debugging response detected")
                break

        # Results
        print("\n" + "=" * 60)
        print("Results")
        print("=" * 60)
        test.formatter.print_debug(f"First request events: {len(stream1_events)}")
        test.formatter.print_debug(f"Clarification detected: {'✅' if clarification_found else '⚠️'}")
        test.formatter.print_debug(f"Second request events: {len(stream2_events)}")
        test.formatter.print_debug(f"Helpful response: {'✅' if helpful_response else '❌'}")

        # Test passes if we got streaming events for both requests
        success = len(stream1_events) > 0 and len(stream2_events) > 0

        test.results.append(success)

        if success:
            test.formatter.print_success("Clarification streaming test passed")
            test.formatter.print_debug("• Both requests produced streaming events")
            test.formatter.print_debug("• Streaming works during clarification flow")
        else:
            test.formatter.print_failure("Clarification streaming test failed")
            if len(stream1_events) == 0:
                test.formatter.print_error("• First request did not stream")
            if len(stream2_events) == 0:
                test.formatter.print_error("• Second request did not stream")

        # Print streaming summary
        test.print_streaming_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if success else 1

    return asyncio.run(run_clarification_test())


if __name__ == "__main__":
    import os
    exit_code = main()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
