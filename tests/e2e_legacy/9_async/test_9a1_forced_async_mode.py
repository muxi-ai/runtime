#!/usr/bin/env python3
"""
Test 9A1: Forced async mode with use_async=True
Tests that when use_async=True is explicitly set, the system processes the request asynchronously
regardless of complexity or estimated duration.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test forced async mode."""
    print("🚀 MUXI Runtime - Test 9A1: Forced Async Mode")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-async"
    webhook_log_path = Path.cwd() / "webhook_log.json"

    # Clear webhook log if it exists
    if webhook_log_path.exists():
        webhook_log_path.unlink()
    # Small delay to ensure file is fully deleted
    await asyncio.sleep(0.1)

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded")
        print("📋 Testing forced async mode with use_async=True...")

        # Simple request but forced to async mode
        start_time = time.time()
        response = await overlord.chat(
            message="What is 2 + 2?",  # Very simple task
            user_id="test_user",
            session_id="async_test_9a1",
            use_async=True,  # Force async mode
            stream=False
        )
        elapsed_time = time.time() - start_time

        # Check response
        print(f"\n⏱️ Response time: {elapsed_time:.2f}s")

        # With use_async=True, we should get a sync response with async info
        if isinstance(response, dict) and 'request_id' in response:
            print("✅ Got async processing response")
            print(f"   Request ID: {response.get('request_id')}")
            print(f"   Status: {response.get('status')}")
            print(f"   Message: {response.get('message')}")
            print(f"   Webhook URL: {response.get('webhook_url')}")

            request_id = response.get('request_id')
            print(f"   Looking for request ID: {request_id}")

            # Wait for webhook to be delivered
            print("\n⏳ Waiting for webhook delivery...")
            max_wait = 30  # Maximum wait time in seconds
            check_interval = 1  # Check every second
            waited = 0
            webhook_found = False

            while waited < max_wait:
                await asyncio.sleep(check_interval)
                waited += check_interval

                # Check if webhook has been received
                if webhook_log_path.exists():
                    try:
                        with open(webhook_log_path, 'r') as f:
                            content = f.read()
                            if not content:
                                continue  # File exists but empty, wait more

                            # Read lines and parse each as JSON (JSONL format)
                            for line in content.splitlines():
                                line = line.strip()
                                if not line:
                                    continue

                                try:
                                    webhook_entry = json.loads(line)
                                    # The webhook entry contains the full HTTP request details
                                    # The actual webhook payload is in the 'body' field
                                    if 'body' in webhook_entry:
                                        webhook = webhook_entry['body']
                                        webhook_id = webhook.get('id') if isinstance(webhook, dict) else None
                                        if waited <= 2:  # Only show debug for first 2 seconds
                                            print(f"   Found webhook with ID: {webhook_id} (looking for {request_id})")
                                        if isinstance(webhook, dict) and webhook.get('id') == request_id:
                                            print(f"\n✅ Webhook received after {waited}s!")
                                            print(f"   Request ID: {webhook.get('id')}")
                                            print(f"   Status: {webhook.get('status')}")
                                            print(f"   Processing time: {webhook.get('processing_time', 'N/A')}s")

                                            # Get the response content
                                            response_data = webhook.get('response', [])
                                            if response_data and isinstance(response_data, list):
                                                for item in response_data:
                                                    if item.get('type') == 'text':
                                                        content = item.get('text', '')
                                                        print(f"   Content preview: {content[:100]}...")

                                                        # Verify the content is correct
                                                        if '4' in content.lower() or 'four' in content.lower():
                                                            print("   ✅ Result contains correct answer (4)")

                                            webhook_found = True
                                            break
                                except json.JSONDecodeError:
                                    # Single line failed to parse, continue with next
                                    continue
                    except (IOError, OSError):
                        # File might not be ready yet, continue waiting
                        pass

                if webhook_found:
                    break

                if waited % 5 == 0:  # Progress update every 5 seconds
                    print(f"   Still waiting... ({waited}s)")

            if webhook_found:
                print("\n" + "="*60)
                print("✅ Test 9A1 PASSED: Forced async mode working correctly")
                return True
            else:
                print(f"\n❌ Webhook not received after {max_wait}s")
                print("\n" + "="*60)
                print("❌ Test 9A1 FAILED: Webhook was not delivered")
                return False

        else:
            # Unexpected response format
            print(f"\n❌ Unexpected response format: {response}")
            print(f"   Type: {type(response)}")
            if hasattr(response, '__dict__'):
                print(f"   Attributes: {response.__dict__}")
            print("\n" + "="*60)
            print("❌ Test 9A1 FAILED: Did not get expected async processing response")
            return False

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

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
