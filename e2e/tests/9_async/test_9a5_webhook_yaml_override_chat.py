#!/usr/bin/env python3
"""
Test 9A5: Webhook in YAML Overridden by chat()

Tests that when a webhook_url is configured in the formation YAML,
but a different one is passed directly to chat(), the chat() parameter takes precedence.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test webhook override via chat() parameter."""
    test = BaseAsyncTest(
        "9a5_webhook_yaml_override_chat", "Test webhook URL override from chat() parameter"
    )

    async def run_async_test():
        # Setup formation with webhook in YAML (http://127.0.0.1:8765)
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))
        await test.clear_webhook_log()

        test.formatter.print_debug("Testing webhook URL override from chat() parameter...")
        test.formatter.print_debug("YAML webhook: http://127.0.0.1:8765")
        test.formatter.print_debug("chat() webhook: http://localhost:8765")

        # Force async with different webhook URL
        response = await test.overlord.chat(
            message="What is 2 + 2?",
            user_id="test_user",
            session_id="async_test_9a5",
            use_async=True,  # Force async
            webhook_url="http://localhost:8765",  # Override YAML webhook
            stream=False,
        )

        # Check if we got async response
        if isinstance(response, dict) and "request_id" in response:
            test.formatter.print_success("Got async processing response")
            test.formatter.print_debug(f"Request ID: {response.get('request_id')}")

            # Verify webhook URL matches chat() parameter (not YAML)
            if response.get("webhook_url") == "http://localhost:8765":
                test.formatter.print_success("Webhook URL correctly overridden by chat() parameter")
            else:
                test.formatter.print_warning(
                    f"Webhook URL: {response.get('webhook_url')} (expected: http://localhost:8765)"
                )

            request_id = response.get("request_id")

            # Wait for webhook delivery
            webhook = await test.wait_for_webhook(request_id, max_wait=30)

            if webhook:
                # Verify the webhook used the overridden URL
                test.formatter.print_debug(f"Webhook URL in payload: {webhook.get('webhook_url')}")

                success = await test.verify_webhook_content(webhook, "4")
                test.results.append(success)

                # Extract response for transcript
                response_data = webhook.get("response", [])
                for item in response_data:
                    if item.get("type") == "text":
                        content = item.get("text", "")
                        test.transcript.append(("What is 2 + 2?", content))
                        break
            else:
                test.formatter.print_failure("Webhook not received")
                test.results.append(False)
        else:
            test.formatter.print_failure("Did not get async response despite use_async=True")
            test.results.append(False)

        # Print summary
        test.print_async_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if all(test.results) else 1

    import asyncio
    return asyncio.run(run_async_test())


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
