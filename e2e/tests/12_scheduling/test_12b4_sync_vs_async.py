#!/usr/bin/env python3
"""
Test 12B4: Sync vs Async Dad Joke Test
Tests whether the delegation message issue is related to async processing.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_sync_vs_async():
    """Test dad joke generation in sync vs async mode."""
    print("\n" + "="*60)
    print("TEST 12B4: Sync vs Async Dad Joke Test")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Test 1: Synchronous request
        print("\n" + "="*40)
        print("TEST 1: SYNCHRONOUS REQUEST")
        print("="*40)
        print("[Request] Sending: 'tell me a dad joke' (sync)")

        sync_response = await overlord.chat(
            message="tell me a dad joke",
            user_id="sync_test",
            session_id="sync_session",
            use_async=False,
            stream=False
        )

        print(f"[Response] Sync result: {sync_response}")

        # Check if it's a delegation message
        if "delegated the task to an external agent" in str(sync_response):
            print("⚠️ SYNC: Got delegation message")
        else:
            print("✅ SYNC: Got actual response (not delegation)")

        # Test 2: Asynchronous request
        print("\n" + "="*40)
        print("TEST 2: ASYNCHRONOUS REQUEST")
        print("="*40)
        print("[Request] Sending: 'tell me a dad joke' (async)")

        async_response = await overlord.chat(
            message="tell me a dad joke",
            user_id="async_test",
            session_id="async_session",
            use_async=True,
            stream=False
        )

        print(f"[Response] Async result: {async_response}")

        # Check if it's a delegation message
        if "delegated the task to an external agent" in str(async_response):
            print("⚠️ ASYNC: Got delegation message")
        else:
            print("✅ ASYNC: Got actual response (not delegation)")

        # Wait a bit to see if async webhook fires
        print("\n[Wait] Waiting 10 seconds to see if async webhook fires...")
        await asyncio.sleep(10)

        # Cleanup
        await formation.stop_overlord()

        print("\n✅ TEST COMPLETED: Sync vs Async comparison done")
        print("\nSUMMARY:")
        print(f"- Sync response: {'delegation' if 'delegated the task' in str(sync_response) else 'actual content'}")
        print(f"- Async response: {'delegation' if 'delegated the task' in str(async_response) else 'actual content'}")
        print("\nCheck webhook_log.json for any async webhook responses")

        return 0

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_sync_vs_async())
    import os; os._exit(exit_code)
