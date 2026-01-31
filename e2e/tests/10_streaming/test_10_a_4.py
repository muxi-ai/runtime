#!/usr/bin/env python3
"""
Test 10A4: Streaming Control

Tests that streaming can be enabled/disabled via the stream parameter.
"""

import asyncio
import sys
from pathlib import Path

from base_streaming_test import BaseStreamingTest


def main():
    """Test streaming control with stream parameter."""
    test = BaseStreamingTest("10a4_streaming_control", "Test streaming enable/disable control")

    async def run_control_test():
        # Setup formation using the shared streaming formation
        formation_path = Path(__file__).parent / "formations" / "formation-streaming"
        await test.setup_formation(formation_path=str(formation_path))

        user_id = "test_user"
        session_id = "control_test_10a4"

        # Test 1: Streaming disabled (stream=False)
        print("\n" + "=" * 60)
        print("Test 1: stream=False")
        print("=" * 60)

        response_no_stream = await test.overlord.chat(
            message="What is the capital of France?",
            user_id=user_id,
            session_id=session_id + "_no_stream",
            stream=False,  # Explicitly disable streaming
        )

        # Check response type
        if hasattr(response_no_stream, "__aiter__"):
            test.formatter.print_failure("Got streaming response when stream=False")
            test1_passed = False
        else:
            test.formatter.print_success("Got non-streaming response when stream=False")
            test1_passed = True

            # Show response content
            if hasattr(response_no_stream, "content"):
                content = response_no_stream.content
            else:
                content = str(response_no_stream)

            preview = content[:100] if len(content) > 100 else content
            test.formatter.print_debug(f"Content: {preview}...")

            # Verify it contains the answer
            if "paris" in content.lower():
                test.formatter.print_success("Response contains correct answer")

        # Test 2: Streaming enabled (stream=True)
        print("\n" + "=" * 60)
        print("Test 2: stream=True")
        print("=" * 60)

        response_stream = await test.overlord.chat(
            message="What is the capital of Germany?",
            user_id=user_id,
            session_id=session_id + "_stream",
            stream=True,  # Explicitly enable streaming
        )

        # Check response type
        if hasattr(response_stream, "__aiter__"):
            test.formatter.print_success("Got streaming response when stream=True")
            test2_passed = True

            # Consume the stream
            stream_result = await test.consume_stream(response_stream, timeout=30.0)
            chunks = stream_result["events"]

            test.formatter.print_debug(f"Received {len(chunks)} chunks")

            # Extract content
            contents = []
            for chunk in chunks:
                if isinstance(chunk, dict):
                    contents.append(chunk.get("content", ""))
                else:
                    contents.append(str(chunk))

            # Verify content
            full_response = " ".join(contents)
            if "berlin" in full_response.lower():
                test.formatter.print_success("Streamed response contains correct answer")
        else:
            test.formatter.print_failure("Got non-streaming response when stream=True")
            test2_passed = False

        # Test 3: Default behavior (no stream parameter)
        print("\n" + "=" * 60)
        print("Test 3: Default behavior (no stream parameter)")
        print("=" * 60)

        response_default = await test.overlord.chat(
            message="What is the capital of Spain?",
            user_id=user_id,
            session_id=session_id + "_default",
            # No stream parameter - use formation default
        )

        # Check what we got (depends on formation config)
        if hasattr(response_default, "__aiter__"):
            test.formatter.print_debug("Default behavior: Streaming enabled")
            stream_result = await test.consume_stream(response_default, timeout=30.0)
            chunks = stream_result["events"]
            contents = []
            for chunk in chunks:
                if isinstance(chunk, dict):
                    contents.append(chunk.get("content", ""))
                else:
                    contents.append(str(chunk))
            full_response = " ".join(contents)
        else:
            test.formatter.print_debug("Default behavior: Streaming disabled")
            if hasattr(response_default, "content"):
                full_response = response_default.content
            else:
                full_response = str(response_default)

        if "madrid" in full_response.lower():
            test.formatter.print_success("Default response contains correct answer")

        # Record results
        test.results.append(test1_passed)
        test.results.append(test2_passed)

        if test1_passed and test2_passed:
            test.formatter.print_success("Streaming control test passed")
            test.formatter.print_debug("• stream=False produces non-streaming response")
            test.formatter.print_debug("• stream=True produces streaming response")
        else:
            test.formatter.print_failure("Streaming control test failed")
            if not test1_passed:
                test.formatter.print_error("• stream=False not working correctly")
            if not test2_passed:
                test.formatter.print_error("• stream=True not working correctly")

        # Print streaming summary
        test.print_streaming_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if all(test.results) else 1

    return asyncio.run(run_control_test())


if __name__ == "__main__":
    exit_code = main()
    import os; os._exit(exit_code)
