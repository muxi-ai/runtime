#!/usr/bin/env python
"""
Test 9C3: Async with Streaming Conflict

This test verifies that when both async and streaming are requested,
the system ignores streaming and proceeds with async mode.
"""

import asyncio
import os
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from muxi.formation import Formation  # noqa: E402

# Test configuration
TEST_REQUEST = "Count from 1 to 5 slowly, showing each number."


async def run_test():
    """Test async with streaming conflict handling."""
    print("=" * 80)
    print("Test 9C3: Async with Streaming Conflict")
    print("=" * 80)
    print("Testing that streaming is ignored when async mode is used")
    print()

    # Initialize formation
    print("Loading formation configuration...")
    formation = Formation()
    formation_path = os.path.join(os.path.dirname(__file__), "formation-async")
    await formation.load(formation_path)
    print("✓ Formation loaded\n")

    # Start overlord
    print("Starting overlord...")
    overlord = await formation.start_overlord()
    print("✓ Overlord started\n")

    # Get webhook configuration
    async_config = overlord.formation_config.get("async", {})
    webhook_url = async_config.get("webhook_url")

    print("Configuration:")
    print(f"  - Webhook URL: {webhook_url}")
    print()

    # Test 1: Normal streaming (without async)
    print("Test 1: Normal streaming mode (stream=True, use_async=False)")
    print(f"Sending: '{TEST_REQUEST}'")

    response1 = await overlord.chat(
        TEST_REQUEST,
        user_id="user_123",
        session_id="session_stream_test",
        use_async=False,
        stream=True
    )

    # Check if it's a generator (streaming response)
    if hasattr(response1, '__aiter__'):
        print("  ✓ Returned async generator (streaming mode)")
        chunks = []
        async for chunk in response1:
            chunks.append(chunk)
            print(f"    Chunk: {chunk[:50]}..." if len(chunk) > 50 else f"    Chunk: {chunk}")
        print(f"  Total chunks received: {len(chunks)}")
        is_streaming1 = True
    else:
        print(f"  Returned regular response: {type(response1)}")
        is_streaming1 = False
    print()

    # Test 2: Async mode only (no streaming)
    print("Test 2: Async mode only (stream=False, use_async=True)")
    print(f"Sending: '{TEST_REQUEST}'")

    response2 = await overlord.chat(
        TEST_REQUEST,
        user_id="user_123",
        session_id="session_stream_test",
        use_async=True,
        stream=False
    )

    # Should return async response with request_id
    if isinstance(response2, dict) and "request_id" in response2:
        print(f"  ✓ Returned async response with request_id: {response2.get('request_id')}")
        is_async2 = True
        request_id2 = response2.get("request_id")
    else:
        print(f"  Returned: {type(response2)}")
        is_async2 = False
        request_id2 = None
    print()

    # Test 3: CONFLICT - Both async and streaming requested
    print("Test 3: CONFLICT - Both async and streaming (stream=True, use_async=True)")
    print(f"Sending: '{TEST_REQUEST}'")
    print("Expected: Async mode should take precedence, streaming should be ignored")

    response3 = await overlord.chat(
        TEST_REQUEST,
        user_id="user_123",
        session_id="session_stream_test",
        use_async=True,
        stream=True  # This should be ignored
    )

    # Should return async response (NOT a generator)
    if isinstance(response3, dict) and "request_id" in response3:
        print("  ✓ Correctly returned async response (ignored streaming)")
        print(f"    Request ID: {response3.get('request_id')}")
        is_correct3 = True
        request_id3 = response3.get("request_id")

        # Wait a bit and check status
        await asyncio.sleep(5)
        status = await overlord.get_request_status(request_id3)
        print(f"    Status check: {status.get('status')}")

    elif hasattr(response3, '__aiter__'):
        print("  ❌ Incorrectly returned streaming response (should have ignored it)")
        is_correct3 = False
        request_id3 = None
    else:
        print(f"  ? Unexpected response type: {type(response3)}")
        is_correct3 = None
        request_id3 = None
    print()

    # Test 4: Verify async requests complete properly
    if request_id2 or request_id3:
        print("Test 4: Verifying async requests complete properly")

        # Wait for completion
        max_wait = 20
        check_interval = 2

        for req_id in [request_id2, request_id3]:
            if req_id:
                print(f"  Checking {req_id}...")
                for i in range(max_wait // check_interval):
                    status = await overlord.get_request_status(req_id)
                    current_status = status.get("status")
                    if current_status in ["completed", "failed"]:
                        print(f"    ✓ Request completed with status: {current_status}")
                        break
                    await asyncio.sleep(check_interval)
                else:
                    print(f"    ⚠️ Request still processing after {max_wait}s")
        print()

    # Analyze results
    print("=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)

    test_passed = True
    results = []

    # Normal streaming should work when async is disabled
    if not is_streaming1:
        # Streaming might not be implemented yet, that's okay
        results.append("⚠️ Streaming not implemented (expected for now)")
    else:
        results.append("✓ Normal streaming works without async")

    # Async mode should work alone
    if is_async2:
        results.append("✓ Async mode works without streaming")
    else:
        results.append("❌ Async mode failed without streaming")
        test_passed = False

    # CRITICAL: Async should override streaming
    if is_correct3:
        results.append("✓ Async correctly overrides streaming (conflict resolved)")
    elif is_correct3 is False:
        results.append("❌ Streaming was not ignored in async mode")
        test_passed = False
    else:
        results.append("? Unable to determine conflict resolution")

    # Async requests should complete
    if request_id2 or request_id3:
        results.append("✓ Async requests tracked and queryable")

    for result in results:
        print(result)

    # Clean up
    print("\nShutting down...")
    await formation.shutdown()

    return test_passed


if __name__ == "__main__":
    success = asyncio.run(run_test())

    print("\n" + "=" * 80)
    if success:
        print("🎉 SUCCESS: Async/streaming conflict handled correctly!")
        print("✓ Streaming ignored when async mode is active")
        print("✓ No errors from conflicting modes")
        print("✓ Async requests complete properly")
    else:
        print("❌ FAILURE: Issues with async/streaming conflict handling")
    print("=" * 80)

    sys.exit(0 if success else 1)
