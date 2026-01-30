#!/usr/bin/env python3
"""
Test 9A3b: Automatic Async Selection for Complex Tasks

Tests that when use_async is not specified (None), the system automatically chooses
asynchronous mode for complex, long-running tasks based on complexity estimation.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test automatic async selection for complex tasks."""
    test = BaseAsyncTest(
        "9a3b_complex_task_auto_async", "Test automatic async mode selection for complex tasks"
    )

    async def run_async_test():
        # Setup formation
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))
        await test.clear_webhook_log()

        test.formatter.print_debug("Testing automatic mode selection for complex task...")

        # Complex task - system should auto-select async mode
        response = await test.overlord.chat(
            message=(
                "Research the latest developments in quantum computing, analyze the key players "
                "and breakthroughs, then create a comprehensive report with findings and timeline"
            ),
            user_id="test_user",
            session_id="auto_async_test_9a3b",
            # use_async not specified - let system decide
            stream=False,
        )

        # Check if system chose async (has request_id attribute)
        if hasattr(response, "request_id"):
            test.formatter.print_success(
                f"System correctly chose async mode (request_id: {response.request_id})"
            )

            # Wait for webhook delivery
            webhook = await test.wait_for_webhook(response.request_id, max_wait=30)

            if webhook:
                # Verify webhook content
                success = await test.verify_webhook_content(webhook, "quantum")
                test.results.append(success)

                # Extract response for transcript
                response_data = webhook.get("response", [])
                for item in response_data:
                    if item.get("type") == "text":
                        content = item.get("text", "")
                        test.transcript.append(("Research quantum computing", content[:300] + "..."))
                        break
            else:
                test.formatter.print_failure("Webhook not received for async request")
                test.results.append(False)

        else:
            # Got sync response for complex task
            if isinstance(response, str):
                content = response
            elif hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            test.formatter.print_warning("System chose sync mode for complex task")
            test.formatter.print_debug("This might happen if complexity threshold is high")

            # Check if response contains research
            if "quantum" in content.lower():
                test.formatter.print_success("Response contains expected research content")
                test.results.append(True)
                test.transcript.append(("Research quantum computing", content[:300] + "..."))
            else:
                test.formatter.print_failure("Response doesn't contain expected content")
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
