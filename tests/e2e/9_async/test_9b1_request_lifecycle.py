#!/usr/bin/env python
"""
Test 9B1: Request Lifecycle Management

This test verifies the request status tracking and cancellation APIs
during async workflow execution. Based on test 9A3B but with lifecycle checks.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))

from muxi.formation import Formation

# Test configuration
USE_ASYNC = True
TEST_REQUEST = "What is 2+2? Please show your work."


async def run_test():
    """Test request lifecycle management during async execution."""
    print("=" * 80)
    print("Test 9B1: Request Lifecycle Management")
    print("=" * 80)
    print("Testing request status tracking and cancellation APIs")
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

    # Get webhook URL from overlord's formation config
    webhook_url = overlord.formation_config.get("async", {}).get("webhook_url")
    print(f"Webhook URL: {webhook_url}\n")
    
    # Determine expected behavior
    should_be_async = USE_ASYNC and webhook_url
    print(f"Expected behavior: {'ASYNC' if should_be_async else 'SYNC'} execution")
    print(f"  - use_async={USE_ASYNC}")
    print(f"  - webhook_url={'configured' if webhook_url else 'not configured'}")
    print()
    
    # Send chat message
    print(f"Sending request: '{TEST_REQUEST[:80]}...'")
    response = await overlord.chat(
        TEST_REQUEST, 
        user_id="user_123",
        session_id="session_456",
        use_async=USE_ASYNC
    )
    print(f"Initial response received: {response}")
    print()

    # Extract request_id from response
    if isinstance(response, dict):
        request_id = response.get("request_id")
        approval_question = response.get("clarification_question")
    else:
        # Handle MuxiResponse object
        request_id = getattr(response, "request_id", None)
        if hasattr(response, 'content'):
            content = response.content
            # Parse string representation of dict if needed
            if isinstance(content, str) and content.startswith('{'):
                try:
                    import ast
                    content_dict = ast.literal_eval(content)
                    approval_question = content_dict.get("clarification_question")
                except (ValueError, SyntaxError):
                    approval_question = None
            elif isinstance(content, dict):
                approval_question = content.get("clarification_question")
            else:
                approval_question = None
        else:
            approval_question = None

    if not request_id:
        print("❌ No request_id in response")
        await formation.shutdown()
        return False

    print(f"Request ID: {request_id}")
    
    # Check if we need approval
    if approval_question and "proceed" in approval_question.lower():
        print(f"\n📋 Approval required: {approval_question}")
        print("Approving workflow execution...")
        
        # Approve the workflow
        approval_response = await overlord.chat(
            "Yes, please proceed",
            user_id="user_123",
            session_id="session_456",
        )
        print(f"Approval response: {approval_response}\n")
        
        # Extract new request_id if provided in approval response
        if isinstance(approval_response, dict):
            new_request_id = approval_response.get("request_id")
            if new_request_id:
                request_id = new_request_id
                print(f"Updated request ID: {request_id}\n")
    
    # Now test the lifecycle management APIs
    print("=" * 40)
    print("Testing Request Lifecycle Management")
    print("=" * 40)
    
    # Test 1: Check initial status
    print("\n1. Checking initial request status...")
    status = await overlord.get_request_status(request_id)
    print(f"   Status response: {status}")
    
    if "error" in status:
        print(f"   ❌ Error getting status: {status['error']}")
    else:
        print(f"   ✓ Request status: {status.get('status')}")
        if status.get('progress'):
            print(f"   ✓ Progress: {status.get('progress')}")
    
    # Test 2: Check status during execution (if async)
    if should_be_async and status.get('status') in ['processing', 'running', 'pending']:
        print("\n2. Monitoring status during async execution...")
        
        # Check status a few times over 6 seconds
        for i in range(3):
            await asyncio.sleep(2)
            status = await overlord.get_request_status(request_id)
            print(f"   Check {i+1}: Status = {status.get('status')}, Progress = {status.get('progress')}")
            
            # If completed, break early
            if status.get('status') in ['completed', 'failed', 'cancelled']:
                break
    
    # Test 3: Test cancellation (create a new request for this)
    print("\n3. Testing request cancellation...")
    print("   Creating new async request to cancel...")
    
    cancel_response = await overlord.chat(
        "What is 5+3? Show the calculation.",
        user_id="user_123", 
        session_id="session_cancel",
        use_async=USE_ASYNC
    )
    
    # Get request_id for cancellation test
    if isinstance(cancel_response, dict):
        cancel_request_id = cancel_response.get("request_id")
    else:
        cancel_request_id = getattr(cancel_response, "request_id", None)
    
    if cancel_request_id:
        print(f"   Request to cancel: {cancel_request_id}")
        
        # Wait a moment to ensure it's processing
        await asyncio.sleep(1)
        
        # Check status before cancellation
        pre_cancel_status = await overlord.get_request_status(cancel_request_id)
        print(f"   Status before cancel: {pre_cancel_status.get('status')}")
        
        # Cancel the request
        cancel_result = await overlord.cancel_request(cancel_request_id)
        print(f"   Cancel result: {cancel_result}")
        
        # Check status after cancellation
        post_cancel_status = await overlord.get_request_status(cancel_request_id)
        print(f"   Status after cancel: {post_cancel_status.get('status')}")
        
        # Verify cancellation
        if cancel_result.get('success'):
            print("   ✓ Request successfully cancelled")
        else:
            print(f"   ⚠️ Cancel attempt: {cancel_result.get('message')}")
    else:
        print("   ⚠️ Could not get request_id for cancellation test")
    
    # Test 4: Check final status of original request (wait for completion if async)
    if should_be_async:
        print("\n4. Waiting for original request completion...")
        max_wait = 30  # Wait up to 30 seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status = await overlord.get_request_status(request_id)
            current_status = status.get('status')
            
            if current_status in ['completed', 'failed', 'cancelled']:
                print(f"   Final status: {current_status}")
                break
                
            await asyncio.sleep(2)
        else:
            print(f"   ⚠️ Request still {status.get('status')} after {max_wait} seconds")
    
    # Test 5: Test invalid request ID
    print("\n5. Testing invalid request ID...")
    invalid_status = await overlord.get_request_status("invalid_request_id_12345")
    if "error" in invalid_status:
        print(f"   ✓ Correctly returned error: {invalid_status['error']}")
    else:
        print(f"   ❌ Should have returned error but got: {invalid_status}")
    
    # Test 6: Test cancelling completed request
    print("\n6. Testing cancel on completed/invalid request...")
    cancel_completed = await overlord.cancel_request(request_id)
    if not cancel_completed.get('success'):
        print(f"   ✓ Correctly rejected: {cancel_completed.get('message')}")
    else:
        print(f"   ❌ Should have rejected but got: {cancel_completed}")
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    test_passed = True
    results = []
    
    # Check that status API works
    if "error" not in status:
        results.append("✓ Request status API working")
    else:
        results.append("❌ Request status API failed")
        test_passed = False
    
    # Check that cancel API responds appropriately
    if cancel_result:
        results.append("✓ Request cancel API responding")
    else:
        results.append("❌ Request cancel API not responding")
        test_passed = False
    
    # Check error handling
    if "error" in invalid_status:
        results.append("✓ Error handling for invalid request")
    else:
        results.append("❌ Error handling not working")
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
        print("🎉 SUCCESS: Request lifecycle management APIs are working!")
        print("✓ Status tracking operational")
        print("✓ Cancellation mechanism functional")
        print("✓ Error handling verified")
    else:
        print("❌ FAILURE: Issues with request lifecycle management")
    print("=" * 80)
    
    sys.exit(0 if success else 1)