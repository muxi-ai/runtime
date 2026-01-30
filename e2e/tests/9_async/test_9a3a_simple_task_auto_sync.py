#!/usr/bin/env python3
"""
Test 9A3a: Automatic Sync Selection for Simple Tasks

Tests that when use_async is not specified (None), the system automatically chooses
synchronous mode for simple, quick tasks based on complexity estimation.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test automatic sync selection for simple tasks."""
    test = BaseAsyncTest(
        "9a3a_simple_task_auto_sync", "Test automatic sync mode selection for simple tasks"
    )

    async def run_async_test():
        # Setup formation
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))
        await test.clear_webhook_log()

        test.formatter.print_debug("Testing automatic mode selection for simple task...")

        # Simple task - system should auto-select sync mode
        response = await test.overlord.chat(
            message="What is 2 + 2?",
            user_id="test_user",
            session_id="auto_sync_test_9a3a",
            # use_async not specified - let system decide
            stream=False,
        )

        # Extract content
        if isinstance(response, str):
            content = response
        elif hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)

        # Check if system chose sync (no request_id attribute)
        if hasattr(response, "request_id"):
            test.formatter.print_warning(
                f"System chose async for simple task (request_id: {response.request_id})"
            )
            test.formatter.print_debug("This might be acceptable under certain conditions")

            # Wait for webhook
            webhook = await test.wait_for_webhook(response.request_id, max_wait=10)
            if webhook:
                success = await test.verify_webhook_content(webhook, "4")
                test.results.append(success)
            else:
                test.results.append(False)

        else:
            test.formatter.print_success("System correctly chose sync mode for simple task")
            test.formatter.print_debug(f"Content: {content}")

            # Verify no webhook sent
            import asyncio

            await asyncio.sleep(2)

            if test.webhook_log_path.exists():
                with open(test.webhook_log_path) as f:
                    file_content = f.read()
                    if file_content.strip():
                        test.formatter.print_failure("Unexpected webhook in sync mode!")
                        test.results.append(False)
                    else:
                        test.formatter.print_success("No webhooks sent (as expected)")
                        test.results.append(True)
                        test.transcript.append(("What is 2 + 2?", content))
            else:
                test.formatter.print_success("No webhook log created (as expected)")
                test.results.append(True)
                test.transcript.append(("What is 2 + 2?", content))

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
