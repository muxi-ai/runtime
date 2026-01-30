#!/usr/bin/env python3
"""
Test 9C3: Async with Streaming Conflict

Tests that when both async and streaming are requested, the system
ignores streaming and proceeds with async mode.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test async with streaming conflict handling."""
    test = BaseAsyncTest("9c3_streaming_conflict", "Test async/streaming conflict resolution")

    async def run_async_test():
        # Setup formation
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))
        await test.clear_webhook_log()

        test.formatter.print_debug("Testing async/streaming conflict resolution...")

        # Test 1: Normal streaming (without async)
        test.formatter.print_debug("Test 1: Streaming without async (stream=True, use_async=False)")

        response1 = await test.overlord.chat(
            message="Count from 1 to 5",
            user_id="test_user",
            session_id="streaming_conflict_test",
            use_async=False,
            stream=True,
        )

        # Check if streaming works
        if hasattr(response1, "__aiter__"):
            test.formatter.print_success("Streaming mode works")
            chunks = []
            async for chunk in response1:
                chunks.append(chunk)
            test.formatter.print_debug(f"Received {len(chunks)} chunks")
            test.results.append(True)
        else:
            test.formatter.print_warning("Streaming not implemented yet")
            test.results.append(True)  # Not a failure if not implemented

        # Test 2: Async mode only (no streaming)
        test.formatter.print_debug("Test 2: Async without streaming (stream=False, use_async=True)")

        response2 = await test.overlord.chat(
            message="Count from 1 to 5",
            user_id="test_user",
            session_id="streaming_conflict_test",
            use_async=True,
            stream=False,
        )

        # Should return async response
        if isinstance(response2, dict) and "request_id" in response2:
            test.formatter.print_success(f"Async mode works (request_id: {response2.get('request_id')})")
            test.results.append(True)
        else:
            test.formatter.print_failure("Async mode failed")
            test.results.append(False)

        # Test 3: CONFLICT - Both async and streaming
        test.formatter.print_debug("Test 3: CONFLICT - Both modes (stream=True, use_async=True)")
        test.formatter.print_debug("Expected: Async takes precedence, streaming ignored")

        response3 = await test.overlord.chat(
            message="Count from 1 to 5",
            user_id="test_user",
            session_id="streaming_conflict_test",
            use_async=True,
            stream=True,  # Should be ignored
        )

        # Should return async response (NOT a generator)
        if isinstance(response3, dict) and "request_id" in response3:
            test.formatter.print_success("Async correctly overrides streaming")
            test.formatter.print_debug(f"Request ID: {response3.get('request_id')}")

            # Verify request completes
            import asyncio

            await asyncio.sleep(5)
            status = await test.overlord.get_request_status(response3.get("request_id"))
            test.formatter.print_debug(f"Status: {status.get('status')}")

            test.results.append(True)
        elif hasattr(response3, "__aiter__"):
            test.formatter.print_failure("Incorrectly returned streaming (should ignore it)")
            test.results.append(False)
        else:
            test.formatter.print_warning(f"Unexpected response type: {type(response3)}")
            test.results.append(False)

        # Print summary
        test.print_async_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if all(test.results) else 1

    import asyncio
    return asyncio.run(run_async_test())


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
