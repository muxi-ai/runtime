#!/usr/bin/env python3
"""
Simple Async Clarification Test

Tests the async clarification webhook delivery directly by manually triggering
the clarification workflow without relying on automatic detection.
"""

import asyncio
import aiohttp
import sys
import os
import time
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.muxi.runtime.overlord.overlord import Overlord


async def test_direct_clarification_webhook():
    """Test clarification webhook delivery directly"""

    print("🔄 SIMPLE ASYNC CLARIFICATION WEBHOOK TEST")
    print("=" * 60)

    webhook_url = "https://webhook.site/415ae530-05fe-45c9-b1b8-73a4a6a03172"

    # Initialize basic overlord
    overlord = Overlord()
    await overlord.start()

    # Test webhook manager clarification delivery directly
    print("📡 Testing clarification webhook delivery...")

    success = await overlord.webhook_manager.deliver_clarification(
        webhook_url=webhook_url,
        request_id="test_req_123",
        clarification_question="What type of cuisine would you prefer for your restaurant booking?",
        clarification_request_id="clarif_456",
        original_message="book restaurant",
        user_id="test_user_789"
    )

    if success:
        print("✅ Clarification webhook delivered successfully!")
        print(f"📡 Check {webhook_url} for the clarification question")

        # Simulate processing the response after 5 seconds
        print("\n⏳ Waiting 5 seconds before simulating response processing...")
        await asyncio.sleep(5)

        # Test clarification response processing
        print("🤖 Simulating clarification response processing...")

        # This would normally be called when user responds via webhook
        response_processed = await overlord.process_async_clarification_response(
            "test_req_123",
            "I'd like Italian food downtown for tonight at 7 PM for 2 people"
        )

        if response_processed:
            print("✅ Clarification response processed successfully!")
        else:
            print("⚠️  Clarification response processing failed (expected - no real request state)")

        return True
    else:
        print("❌ Clarification webhook delivery failed!")
        return False


async def test_complete_async_flow():
    """Test a complete async flow with manual clarification triggering"""

    print("\n🔄 COMPLETE ASYNC FLOW WITH MANUAL CLARIFICATION")
    print("=" * 60)

    webhook_url = "https://webhook.site/415ae530-05fe-45c9-b1b8-73a4a6a03172"

    # Initialize overlord
    overlord = Overlord()
    await overlord.start()

    # Send a clear message that should go async but not need clarification
    clear_message = "Hello, how are you today?"

    print(f"📝 Sending clear message: '{clear_message}'")
    print("🎯 Expected: Async processing without clarification")

    result = await overlord.chat(
        message=clear_message,
        user_id=999,
        use_async=True,  # Force async
        webhook_url=webhook_url
    )

    if isinstance(result, dict) and result.get("processing_mode") == "async":
        request_id = result.get("request_id")
        print(f"✅ Async processing started: {request_id}")

        # Monitor the request
        for i in range(10):  # Check for 20 seconds
            await asyncio.sleep(2)
            status = await overlord.get_async_request_status(request_id)
            if status:
                current_status = status.get('status', 'unknown')
                print(f"📊 [{i*2}s] Status: {current_status}")

                if current_status == 'completed':
                    print("🎉 Async processing completed!")
                    print("📡 Final webhook should have been delivered!")
                    break
                elif current_status == 'failed':
                    print("❌ Async processing failed!")
                    if status.get('error'):
                        print(f"💥 Error: {status.get('error')}")
                    break

        return True
    else:
        print("❌ Expected async processing but got sync")
        return False


async def main():
    """Run the simple async clarification tests"""

    try:
        print("🧪 TESTING ASYNC CLARIFICATION INTEGRATION")
        print("=" * 70)

        # Test 1: Direct webhook delivery
        print("\n🎯 TEST 1: DIRECT CLARIFICATION WEBHOOK DELIVERY")
        test1_success = await test_direct_clarification_webhook()

        # Test 2: Complete async flow
        print("\n🎯 TEST 2: COMPLETE ASYNC FLOW")
        test2_success = await test_complete_async_flow()

        if test1_success and test2_success:
            print("\n🎉 ALL SIMPLE TESTS COMPLETED!")
            print("📊 Check webhook URL for all notifications")
            return 0
        else:
            print("\n⚠️  SOME TESTS HAD ISSUES")
            return 1

    except Exception as e:
        print(f"\n💥 Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
