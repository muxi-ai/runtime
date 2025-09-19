#!/usr/bin/env python3
"""
Super simple test using Area 12's formation to test async with "tell me a dad joke".
This will help us debug the agent capability issue.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))

from src.muxi.formation.formation import Formation


async def test_async_joke():
    """Test async execution with Area 12 formation for simple joke request."""
    print("\n" + "="*60)
    print("TEST: Area 12 Formation - Async Dad Joke")
    print("="*60)

    # Use Area 12's specific formation
    formation_path = Path(__file__).parent / "tests/e2e/12_scheduling/formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading Area 12 formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Get the webhook URL from formation config
        webhook_url = overlord.formation_config.get("async", {}).get("webhook_url")
        print(f"Webhook URL: {webhook_url}")

        # Send async request
        print("\n[Test] Sending async request: 'Tell me a dad joke'")
        response = await overlord.chat(
            message="Tell me a dad joke",
            user_id="test_user",
            session_id="async_test",
            use_async=True,
            webhook_url=webhook_url,
            stream=False
        )

        # Print immediate response
        if hasattr(response, '__dict__'):
            print(f"\nAsync Response Object:")
            for key, value in response.__dict__.items():
                print(f"  {key}: {value}")
        else:
            print(f"\nAsync Response: {response}")

        # Wait for webhook to be sent
        print("\n[Waiting] Giving async request 30 seconds to complete...")
        await asyncio.sleep(30)
        print("[Waiting] Done waiting")

        # Check logs for what happened
        print("\n[Analysis] Check the logs to see:")
        print("  1. Was the request processed by an agent?")
        print("  2. Did the agent try to delegate 'joke generation'?")
        print("  3. Was there an A2A loop?")
        print("  4. What was sent in the webhook?")

        # Cleanup
        await formation.kill_overlord()

        print("\n" + "="*60)
        print("TEST COMPLETE")
        print("="*60)
        print("\nNext steps:")
        print("  - Check logs: tests/logs/test_area12_async_joke.log")
        print("  - Look for 'joke generation' capability issues")
        print("  - Check what agent was selected and why it couldn't complete the task")

        return 0

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_async_joke())
    sys.exit(exit_code)