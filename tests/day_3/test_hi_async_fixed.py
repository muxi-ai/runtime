"""
Test simple 'hi' with async - fixed version that waits properly
"""

import sys
sys.path.insert(0, ".")

import asyncio
import time
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import setup_webhook_test, check_response_with_webhook
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


async def test_hi_async_fixed():
    """Simple 'hi' test with async and proper cleanup"""

    # Setup webhook testing
    setup_webhook_test()

    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("\n=== Simple 'hi' Test with Async (Fixed) ===")

    try:
        # Send simple message with explicit use_async=True
        response = await overlord.chat(
            user_id="test_hi_async_fixed",
            message="hi",
            use_async=True,  # Explicitly request async
        )

        # Handle async generator if needed
        if hasattr(response, '__aiter__'):
            chunks = []
            async for chunk in response:
                chunks.append(chunk)
            response = "".join(chunks)

        print(f"\nInitial response type: {type(response)}")

        # Use new universal checker with longer timeout
        result, was_async = check_response_with_webhook(
            response,
            expected_keywords=['hello', 'hi', 'hey', 'greet', 'assist'],
            min_keywords=1,
            min_length=10,
            timeout=120,  # Give plenty of time
            test_name="Hi Test (Async Fixed)"
        )

        print(f"\n✅ Test Results:")
        print(f"  - Processing mode: {'Async (via webhook)' if was_async else 'Synchronous'}")
        print(f"  - Response length: {len(result)} characters")
        print(f"  - Response preview: {result[:100]}...")

        if was_async:
            print("  - ✓ Async processing and webhook delivery successful!")
        else:
            print("  - ⚠️  Got sync response (formation may have overridden async request)")

        # Verify it's a greeting response
        response_lower = result.lower()
        assert any(greeting in response_lower for greeting in ['hello', 'hi', 'hey', 'how can i']), \
            "Response should contain a greeting"

        print("\n✅ Greeting verification passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise

    finally:
        # Important: Give async tasks time to complete before shutdown
        print("\n⏳ Waiting for async tasks to complete...")
        await asyncio.sleep(5)

        # Cleanup
        print("\n🧹 Shutting down overlord...")
        try:
            # Don't use timeout parameter - it's not supported
            await formation.stop_overlord()
            print("✅ Overlord shut down gracefully")
        except Exception as e:
            print(f"⚠️  Overlord shutdown error: {e}")
            print("🔨 Using kill_overlord()...")
            formation.kill_overlord()
            print("✅ Overlord killed")


if __name__ == "__main__":
    start_time = time.time()

    was_async = asyncio.run(test_hi_async_fixed())

    elapsed = time.time() - start_time
    print(f"\n🎉 Test completed in {elapsed:.2f} seconds")

    # Check final webhook status
    import requests
    try:
        response = requests.get("http://127.0.0.1:8765/logs")
        if response.ok:
            data = response.json()
            print(f"📊 Total webhooks received: {data.get('count', 0)}")
    except:
        pass

    # Force exit
    import os
    os._exit(0)
