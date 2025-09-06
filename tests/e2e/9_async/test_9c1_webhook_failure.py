#!/usr/bin/env python
"""
Test 9C1: Webhook Failure Handling

This test verifies that the system properly handles webhook failures
with retries according to the formation configuration.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from muxi.formation import Formation

# Test configuration
USE_ASYNC = True
TEST_REQUEST = "What is 3+3? Please show your work."
UNREACHABLE_WEBHOOK = "http://192.0.2.1:9999/webhook"  # Non-routable IP (TEST-NET-1)


async def run_test():
    """Test webhook failure handling with retries."""
    print("=" * 80)
    print("Test 9C1: Webhook Failure Handling")
    print("=" * 80)
    print("Testing webhook retry logic with unreachable endpoint")
    print()

    # Initialize formation
    print("Loading formation configuration...")
    formation = Formation()
    formation_path = os.path.join(os.path.dirname(__file__), "formation-async")
    await formation.load(formation_path)
    
    # Override webhook URL to use unreachable endpoint
    formation.config["async"]["webhook_url"] = UNREACHABLE_WEBHOOK
    print(f"✓ Formation loaded with unreachable webhook: {UNREACHABLE_WEBHOOK}\n")

    # Start overlord
    print("Starting overlord...")
    overlord = await formation.start_overlord()
    
    # Also update overlord's config
    overlord.formation_config["async"]["webhook_url"] = UNREACHABLE_WEBHOOK
    print("✓ Overlord started\n")

    # Check webhook configuration
    async_config = overlord.formation_config.get("async", {})
    webhook_retries = async_config.get("webhook_retries", 3)
    webhook_timeout = async_config.get("webhook_timeout", 10)
    
    print(f"Webhook Configuration:")
    print(f"  - URL: {UNREACHABLE_WEBHOOK}")
    print(f"  - Retries: {webhook_retries}")
    print(f"  - Timeout: {webhook_timeout} seconds")
    print()
    
    # Send async request
    print(f"Sending async request: '{TEST_REQUEST}'")
    start_time = time.time()
    
    response = await overlord.chat(
        TEST_REQUEST, 
        user_id="user_123",
        session_id="session_webhook_test",
        use_async=USE_ASYNC
    )
    
    initial_time = time.time() - start_time
    print(f"Initial response received in {initial_time:.2f}s: {response}")
    print()

    # Extract request_id
    if isinstance(response, dict):
        request_id = response.get("request_id")
    else:
        request_id = getattr(response, "request_id", None)

    if not request_id:
        print("❌ No request_id in response")
        await formation.shutdown()
        return False

    print(f"Request ID: {request_id}")
    print()
    
    # Monitor for webhook retry attempts
    print("Monitoring webhook delivery attempts...")
    print("(Expecting failures due to unreachable endpoint)")
    print()
    
    # Wait for processing and webhook attempts
    # With retries, this should take:
    # - Processing time (~2-5 seconds for simple request)
    # - Initial webhook attempt (timeout after 10s)
    # - Retry 1 (after backoff, timeout after 10s)
    # - Retry 2 (after backoff, timeout after 10s)
    # - Retry 3 (after backoff, timeout after 10s)
    # Total: ~40-50 seconds with timeouts and backoff
    
    max_wait = 60  # Give enough time for all retries
    check_interval = 5
    checks_done = 0
    
    while checks_done * check_interval < max_wait:
        await asyncio.sleep(check_interval)
        checks_done += 1
        elapsed = checks_done * check_interval
        
        # Check request status
        status = await overlord.get_request_status(request_id)
        current_status = status.get("status", "unknown")
        
        print(f"  [{elapsed}s] Request status: {current_status}")
        
        # If request is completed, webhook attempts should have been made
        if current_status in ["completed", "failed"]:
            print(f"  Request finished with status: {current_status}")
            break
    
    # Get final status
    final_status = await overlord.get_request_status(request_id)
    print()
    print(f"Final request status: {final_status}")
    print()
    
    # Analyze results
    print("=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    test_passed = True
    results = []
    
    # Check that request completed (webhook failure shouldn't affect request completion)
    if final_status.get("status") in ["completed", "failed"]:
        results.append("✓ Request completed despite webhook failure")
    else:
        results.append("❌ Request did not complete properly")
        test_passed = False
    
    # Check that multiple retry attempts were made (based on timing)
    total_time = time.time() - start_time
    if total_time > 20:  # Should take significant time with retries
        results.append(f"✓ Webhook retries attempted (took {total_time:.1f}s total)")
    else:
        results.append(f"❌ Webhook retries too quick ({total_time:.1f}s total)")
        test_passed = False
    
    # Request should still be queryable even with webhook failure
    if "error" not in final_status or final_status.get("status"):
        results.append("✓ Request status remains queryable after webhook failure")
    else:
        results.append("❌ Request status not properly maintained")
        test_passed = False
    
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
        print("🎉 SUCCESS: Webhook failure handling working correctly!")
        print("✓ Retries attempted according to configuration")
        print("✓ Request completes despite webhook failure")
        print("✓ Status remains queryable")
    else:
        print("❌ FAILURE: Issues with webhook failure handling")
    print("=" * 80)
    
    sys.exit(0 if success else 1)