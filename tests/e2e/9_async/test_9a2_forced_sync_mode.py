#!/usr/bin/env python3
"""
Test 9A2: Forced sync mode with use_async=False
Tests that when use_async=False is explicitly set, the system processes the request synchronously
even for complex or long-running tasks.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test forced sync mode."""
    print("🚀 MUXI Runtime - Test 9A2: Forced Sync Mode")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-async"
    webhook_log_path = Path.cwd() / "webhook_log.json"

    # Clear webhook log if it exists
    if webhook_log_path.exists():
        webhook_log_path.unlink()

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded")
        print("📋 Testing forced sync mode with use_async=False...")

        # Complex request but forced to sync mode
        # Note: Using a moderately complex task to avoid actual timeout
        start_time = time.time()
        response = await overlord.chat(
            message="Research the top 3 programming languages in 2024 and provide a brief summary of each one's strengths",
            user_id="test_user",
            session_id="sync_test_9a2",
            use_async=False,  # Force sync mode
            stream=False
        )
        elapsed_time = time.time() - start_time

        # Check response
        print(f"\n⏱️ Response time: {elapsed_time:.2f}s")

        # Extract content from response
        if isinstance(response, str):
            content = response
        elif hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)

        # Check if we got a synchronous response (not async)
        if hasattr(response, "request_id"):
            print(f"\n❌ Got async response with request_id: {response.request_id}")
            print("   Should have been synchronous!")
            print("\n" + "="*60)
            print("❌ Test 9A2 FAILED: Should have returned sync response")
            return False
        else:
            print("\n✅ Got synchronous response")
            print(f"   Content preview: {content[:200]}...")

            # Wait a bit to ensure no webhook is sent
            print("\n⏳ Waiting to ensure no webhook is sent...")
            await asyncio.sleep(3)

            # Check webhook log shouldn't exist or be empty
            if webhook_log_path.exists():
                with open(webhook_log_path) as f:
                    webhook_data = json.load(f)

                if webhook_data:
                    print(f"❌ Unexpected webhook received: {len(webhook_data)} entries")
                    print("   Should not send webhooks in sync mode!")
                    return False
                else:
                    print("✅ No webhooks sent (log exists but empty)")
            else:
                print("✅ No webhook log created (expected for sync mode)")

            print("\n" + "="*60)
            print("✅ Test 9A2 PASSED: Forced sync mode working correctly")
            return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if formation:
            try:
                print("\nShutting down...")
                await formation.kill_overlord()
                formation.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
