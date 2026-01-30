#!/usr/bin/env python3
"""
Test 9A4: No Webhook in YAML but Passed to chat()

Tests that when no webhook_url is configured in the formation YAML,
but one is passed directly to chat(), async mode works correctly.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test webhook passed to chat() when not in YAML."""
    test = BaseAsyncTest(
        "9a4_no_webhook_yaml_passed_chat", "Test webhook passed to chat() without YAML config"
    )

    async def run_async_test():
        # Setup formation with NO webhook in YAML
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path), yaml_name="formation-no-webhook.yaml")
        await test.clear_webhook_log()

        test.formatter.print_debug("Testing async mode with webhook passed to chat()...")

        # Force async with webhook passed directly
        response = await test.overlord.chat(
            message="What is 2 + 2?",
            user_id="test_user",
            session_id="async_test_9a4",
            use_async=True,  # Force async
            webhook_url="http://localhost:8765",  # Pass webhook directly
            stream=False,
        )

        # Check if we got async response
        if isinstance(response, dict) and "request_id" in response:
            test.formatter.print_success("Got async processing response")
            test.formatter.print_debug(f"Request ID: {response.get('request_id')}")
            test.formatter.print_debug(f"Webhook URL: {response.get('webhook_url')}")

            # Verify webhook URL matches what we passed
            if response.get("webhook_url") == "http://localhost:8765":
                test.formatter.print_success("Webhook URL matches chat() parameter")

            request_id = response.get("request_id")

            # Wait for webhook delivery
            webhook = await test.wait_for_webhook(request_id, max_wait=30)

            if webhook:
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
    import os; result = asyncio.run(run_async_test()); os._exit(result)


if __name__ == "__main__":
    main()
    
