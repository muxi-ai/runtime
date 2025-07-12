"""
Test simple 'hi' with async - wait for webhook before shutting down
"""

import sys
sys.path.insert(0, ".")

import asyncio
import time
import requests
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import setup_webhook_test, check_response_with_webhook
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


async def test_hi_async_wait():
    """Simple 'hi' test with async - waits for webhook completion"""

    # Setup webhook testing
    setup_webhook_test()

    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("\n=== Simple 'hi' Test with Async (Wait for Webhook) ===")

    # Track task to keep overlord alive
    webhook_received = False
    result_text = None

    try:
        # Send simple message with explicit use_async=True
        response = await overlord.chat(
            user_id="test_hi_async_wait",
            message="hi",
            use_async=True,  # Explicitly request async
        )

        print(f"\nInitial response type: {type(response)}")
        print(f"Response: {response}")

        # Create task for webhook checking
        async def check_webhook():
            nonlocal webhook_received, result_text
            try:
                result, was_async = check_response_with_webhook(
                    response,
                    expected_keywords=['hello', 'hi', 'hey', 'greet', 'assist'],
                    min_keywords=1,
                    min_length=10,
                    timeout=60,  # Wait up to 60 seconds
                    test_name="Hi Test (Async Wait)"
                )
                webhook_received = True
                result_text = result
                return result, was_async
            except Exception as e:
                print(f"Webhook check error: {e}")
                raise

        # Run webhook check as a task
        webhook_task = asyncio.create_task(check_webhook())

        # Wait for webhook with timeout
        try:
            result, was_async = await asyncio.wait_for(webhook_task, timeout=70)

            print(f"\n✅ Test Results:")
            print(f"  - Processing mode: {'Async (via webhook)' if was_async else 'Synchronous'}")
            print(f"  - Response length: {len(result)} characters")
            print(f"  - Response preview: {result[:100]}...")

            if was_async:
                print("  - ✓ Async processing and webhook delivery successful!")
            else:
                print("  - ⚠️  Got sync response despite async request")

            # Verify it's a greeting response
            response_lower = result.lower()
            assert any(greeting in response_lower for greeting in ['hello', 'hi', 'hey', 'how can i']), \
                "Response should contain a greeting"

            print("\n✅ Greeting verification passed!")

        except asyncio.TimeoutError:
            print("\n❌ Webhook timeout - no webhook received within 70 seconds")
            raise

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise

    finally:
        # Give a moment for any cleanup
        await asyncio.sleep(2)

        # Cleanup
        print("\n🧹 Shutting down overlord...")
        try:
            await formation.stop_overlord()
            print("✅ Overlord shut down gracefully")
        except Exception as e:
            print(f"⚠️  Overlord shutdown error: {e}")
            print("🔨 Using kill_overlord()...")
            formation.kill_overlord()
            print("✅ Overlord killed")


if __name__ == "__main__":
    start_time = time.time()

    asyncio.run(test_hi_async_wait())

    elapsed = time.time() - start_time
    print(f"\n🎉 Test completed in {elapsed:.2f} seconds")

    # Check final webhook status
    try:
        response = requests.get("http://127.0.0.1:8765/logs")
        if response.ok:
            data = response.json()
            count = data.get('count', 0)
            print(f"📊 Total webhooks received: {count}")

            if count > 0:
                print("\n📋 Webhook details:")
                for i, webhook in enumerate(data.get('logs', [])):
                    print(f"\nWebhook {i+1}:")
                    body = webhook.get('body', {})
                    if isinstance(body, dict):
                        print(f"  ID: {body.get('id')}")
                        print(f"  Status: {body.get('status')}")
                        print(f"  Object: {body.get('object')}")
    except:
        pass

    # Force exit
    import os
    os._exit(0)
