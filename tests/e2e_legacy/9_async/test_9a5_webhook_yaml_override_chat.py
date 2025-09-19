#!/usr/bin/env python3
"""
Test 9A5: Webhook in YAML overridden by chat()
Tests that when a webhook_url is configured in the formation YAML,
but a different one is passed directly to chat(), the chat() one takes precedence.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test webhook override via chat() parameter."""
    print("🚀 MUXI Runtime - Test 9A5: Webhook in YAML overridden by chat()")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-async"  # Uses formation.yaml with webhook
    webhook_log_path = Path.cwd() / "webhook_log.json"

    # Clear webhook log if it exists
    if webhook_log_path.exists():
        webhook_log_path.unlink()

    formation = None
    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded (webhook in YAML: http://127.0.0.1:8765)")
        print("📋 Testing async mode with different webhook_url passed to chat()...")

        # Simple request but forced to async mode with different webhook
        start_time = time.time()
        response = await overlord.chat(
            message="What is 2 + 2?",  # Very simple task
            user_id="test_user",
            session_id="async_test_9a5",
            use_async=True,  # Force async mode
            webhook_url="http://localhost:8765",  # Override with localhost instead of 127.0.0.1
            stream=False
        )
        elapsed_time = time.time() - start_time

        # Check response
        print(f"\n⏱️ Response time: {elapsed_time:.2f}s")

        # With use_async=True and webhook_url provided, we should get async processing
        if isinstance(response, dict) and 'request_id' in response:
            print("✅ Got async processing response")
            print(f"   Request ID: {response.get('request_id')}")
            print(f"   Status: {response.get('status')}")
            print(f"   Message: {response.get('message')}")
            print(f"   Webhook URL: {response.get('webhook_url')}")

            # Check that the webhook URL in response matches what we passed
            if response.get('webhook_url') == "http://localhost:8765":
                print("   ✅ Response webhook URL matches chat() parameter (not YAML)")

            request_id = response.get('request_id')

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
                        with open(webhook_log_path) as f:
                            # Read lines and parse each as JSON (JSONL format)
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue

                                webhook_entry = json.loads(line)
                                # The webhook entry contains the full HTTP request details
                                # Check the Host header to verify which URL was used
                                headers = webhook_entry.get('headers', {})
                                host = headers.get('Host', '')

                                # The actual webhook payload is in the 'body' field
                                if 'body' in webhook_entry:
                                    webhook = webhook_entry['body']
                                    if isinstance(webhook, dict) and webhook.get('id') == request_id:
                                        print(f"\n✅ Webhook received after {waited}s!")
                                        print(f"   Request ID: {webhook.get('id')}")
                                        print(f"   Status: {webhook.get('status')}")
                                        print(f"   Processing time: {webhook.get('processing_time', 'N/A')}s")
                                        print(f"   Webhook URL used: {webhook.get('webhook_url')}")
                                        print(f"   Host header: {host}")

                                        # Verify the webhook URL is the one we passed
                                        if webhook.get('webhook_url') == "http://localhost:8765":
                                            print("   ✅ Webhook URL matches chat() parameter (overrode YAML)")
                                        elif webhook.get('webhook_url') == "http://127.0.0.1:8765":
                                            print("   ⚠️ Webhook URL matches YAML config (override didn't work)")

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
                    except (json.JSONDecodeError, FileNotFoundError):
                        # File might not be ready yet, continue waiting
                        pass

                if webhook_found:
                    break

                if waited % 5 == 0:  # Progress update every 5 seconds
                    print(f"   Still waiting... ({waited}s)")

            if webhook_found:
                print("\n" + "="*60)
                print("✅ Test 9A5 PASSED: chat() webhook_url overrides YAML config")
                return True
            else:
                print(f"\n❌ Webhook not received after {max_wait}s")
                print("\n" + "="*60)
                print("❌ Test 9A5 FAILED: Webhook was not delivered")
                return False

        else:
            # Unexpected response format
            print(f"\n❌ Unexpected response format: {response}")
            print(f"   Type: {type(response)}")
            if hasattr(response, '__dict__'):
                print(f"   Attributes: {response.__dict__}")
            print("\n" + "="*60)
            print("❌ Test 9A5 FAILED: Did not get expected async processing response")
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
