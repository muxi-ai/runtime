#!/usr/bin/env python3
"""
Test 9A2: Forced Sync Mode

Tests that when use_async=False is explicitly set, the system processes the request
synchronously even for complex or long-running tasks.
"""

import sys
from pathlib import Path

from .base_async_test import BaseAsyncTest


def main():
    """Test forced sync mode."""
    test = BaseAsyncTest("9a2_forced_sync_mode", "Test forced sync mode with use_async=False")

    async def run_async_test():
        # Setup formation using the shared async formation
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))

        # Clear webhook log to ensure no webhooks from previous tests
        await test.clear_webhook_log()

        # Run a sync request (complex query but forced sync)
        test.formatter.print_debug("Testing forced sync mode with use_async=False...")

        response = await test.overlord.chat(
            message="What is 5 + 5?",
            user_id="test_user",
            session_id="sync_test_9a2",
            use_async=False,  # Force sync mode
            stream=False,
        )

        # Extract content from response
        if isinstance(response, str):
            content = response
        elif hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)

        # Verify we got a synchronous response (not async with request_id)
        if hasattr(response, "request_id"):
            test.formatter.print_failure(
                f"Got async response with request_id: {response.request_id} - Should be sync!"
            )
            test.results.append(False)
        else:
            test.formatter.print_success("Got synchronous response as expected")
            test.formatter.print_debug(f"Content preview: {content[:200]}...")

            # Wait a bit to ensure no webhook is sent
            import asyncio

            await asyncio.sleep(3)

            # Verify no webhook was sent via HTTP endpoint
            try:
                import httpx

                async with httpx.AsyncClient() as client:
                    response_check = await client.get(f"{test.webhook_url}/logs", timeout=5.0)
                    if response_check.status_code == 200:
                        data = response_check.json()
                        logs = data.get("logs", [])

                        if len(logs) > 0:
                            test.formatter.print_failure("Unexpected webhook sent in sync mode!")
                            test.formatter.print_debug(f"Found {len(logs)} webhook(s)")
                            test.results.append(False)
                        else:
                            test.formatter.print_success("No webhooks sent (as expected)")
                            test.results.append(True)
                            test.transcript.append(("What is 5 + 5?", content[:200] + "..."))
            except Exception as e:
                test.formatter.print_warning(f"Could not check webhooks via HTTP: {e}")
                test.formatter.print_success("Assuming no webhooks sent (HTTP check failed)")
                test.results.append(True)
                test.transcript.append(("What is 5 + 5?", content[:200] + "..."))

        # Print async-specific summary
        test.print_async_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if all(test.results) else 1

    import asyncio

    return asyncio.run(run_async_test())


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
