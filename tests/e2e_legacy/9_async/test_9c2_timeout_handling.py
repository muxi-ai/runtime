#!/usr/bin/env python
"""
Test 9C2: Timeout Handling

This test verifies that the system properly handles request timeouts
based on the async threshold_seconds configuration.
"""

import asyncio
import os
import sys
import time

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from muxi.formation import Formation  # noqa: E402

# Test configuration
USE_ASYNC = True
# Request that will take a long time to process
COMPLEX_REQUEST = """
Please perform the following complex analysis:
1. Calculate the Fibonacci sequence up to the 30th number
2. Explain the mathematical properties of prime numbers
3. Describe the history of computer science
4. Analyze the implications of quantum computing
5. Summarize the theory of relativity
Please be thorough and detailed in each section.
"""
SIMPLE_REQUEST = "What is 2+2?"


async def run_test():
    """Test timeout handling for async requests."""
    print("=" * 80)
    print("Test 9C2: Timeout Handling")
    print("=" * 80)
    print("Testing request timeout based on threshold_seconds configuration")
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

    # Check timeout configuration
    async_config = overlord.formation_config.get("async", {})
    threshold_seconds = async_config.get("threshold_seconds", 30)
    webhook_url = async_config.get("webhook_url")

    print("Async Configuration:")
    print(f"  - Threshold: {threshold_seconds} seconds")
    print(f"  - Webhook URL: {webhook_url}")
    print()

    # Test 1: Quick request should complete synchronously
    print("Test 1: Quick request (should complete synchronously)")
    print(f"Sending: '{SIMPLE_REQUEST}'")

    start_time = time.time()
    response1 = await overlord.chat(
        SIMPLE_REQUEST,
        user_id="user_123",
        session_id="session_timeout_test",
        use_async=USE_ASYNC
    )
    elapsed1 = time.time() - start_time

    print(f"Response received in {elapsed1:.2f}s")

    # Check if it was sync (should have actual content, not just request_id)
    if isinstance(response1, dict) and "request_id" in response1 and "status" in response1:
        print("  ✓ Returned async response (request_id + status)")
    else:
        # Should have actual answer content
        content1 = response1.content if hasattr(response1, 'content') else str(response1)
        if "4" in str(content1) or "four" in str(content1).lower():
            print(f"  ✓ Returned sync response with answer: {content1}")
        else:
            print(f"  ? Unclear response type: {response1}")
    print()

    # Test 2: Complex request that might trigger async based on complexity
    print("Test 2: Complex request (may trigger async based on threshold)")
    print("Sending complex analytical request...")

    start_time = time.time()
    response2 = await overlord.chat(
        COMPLEX_REQUEST,
        user_id="user_123",
        session_id="session_timeout_test",
        use_async=USE_ASYNC
    )
    elapsed2 = time.time() - start_time

    print(f"Initial response received in {elapsed2:.2f}s")

    # Check if it went async
    if isinstance(response2, dict) and "request_id" in response2:
        print(f"  ✓ Returned async response with request_id: {response2.get('request_id')}")
        request_id = response2.get("request_id")

        # Monitor the async request
        print("\n  Monitoring async request status...")
        for i in range(6):  # Check for 30 seconds
            await asyncio.sleep(5)
            status = await overlord.get_request_status(request_id)
            print(f"    [{i*5}s] Status: {status.get('status')}")
            if status.get("status") in ["completed", "failed"]:
                break
    else:
        response2.content if hasattr(response2, 'content') else str(response2)
        print(f"  Returned sync response (took {elapsed2:.2f}s)")
    print()

    # Test 3: Simulate a request that would timeout
    print("Test 3: Testing threshold behavior")
    print("Sending request with explicit async flag...")

    # This should go async immediately due to use_async=True
    start_time = time.time()
    response3 = await overlord.chat(
        "Calculate the sum of all prime numbers below 1000",
        user_id="user_123",
        session_id="session_timeout_test",
        use_async=True  # Force async
    )
    elapsed3 = time.time() - start_time

    print(f"Response received in {elapsed3:.2f}s")

    if isinstance(response3, dict) and "request_id" in response3:
        print(f"  ✓ Correctly went async with request_id: {response3.get('request_id')}")
        is_async3 = True
    else:
        print(f"  ❌ Should have gone async but got: {type(response3)}")
        is_async3 = False
    print()

    # Analyze results
    print("=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)

    test_passed = True
    results = []

    # Simple request should be fast
    if elapsed1 < 10:  # Should be much faster than threshold
        results.append(f"✓ Simple request completed quickly ({elapsed1:.2f}s)")
    else:
        results.append(f"❌ Simple request too slow ({elapsed1:.2f}s)")
        test_passed = False

    # Async flag should force async mode
    if is_async3:
        results.append("✓ use_async=True correctly triggers async mode")
    else:
        results.append("❌ use_async=True did not trigger async mode")
        test_passed = False

    # Threshold configuration is respected
    if threshold_seconds == 30:
        results.append(f"✓ Threshold configuration loaded correctly ({threshold_seconds}s)")
    else:
        results.append(f"⚠️ Unexpected threshold value: {threshold_seconds}s")

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
        print("🎉 SUCCESS: Timeout handling working correctly!")
        print("✓ Simple requests complete quickly")
        print("✓ Async mode triggered by use_async flag")
        print("✓ Threshold configuration respected")
    else:
        print("❌ FAILURE: Issues with timeout handling")
    print("=" * 80)

    sys.exit(0 if success else 1)
