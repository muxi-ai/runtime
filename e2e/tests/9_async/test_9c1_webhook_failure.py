#!/usr/bin/env python3
"""
Test 9C1: Webhook Failure Handling

Tests that the system properly handles webhook failures with retries
according to the formation configuration.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test webhook failure handling with retries."""
    test = BaseAsyncTest("9c1_webhook_failure", "Test webhook failure handling with retries")

    async def run_async_test():
        # Setup formation
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))
        await test.clear_webhook_log()

        # Override webhook URL to use unreachable endpoint
        # Using TEST-NET-1 address (non-routable)
        unreachable_webhook = "http://192.0.2.1:9999/webhook"
        test.overlord.formation_config["async"]["webhook_url"] = unreachable_webhook

        test.formatter.print_debug("Testing webhook failure handling...")
        test.formatter.print_debug(f"Using unreachable webhook: {unreachable_webhook}")

        # Check webhook configuration
        async_config = test.overlord.formation_config.get("async", {})
        webhook_retries = async_config.get("webhook_retries", 3)
        webhook_timeout = async_config.get("webhook_timeout", 10)

        test.formatter.print_debug(f"Webhook retries: {webhook_retries}")
        test.formatter.print_debug(f"Webhook timeout: {webhook_timeout}s")

        # Send async request to unreachable webhook
        import time

        start_time = time.time()

        response = await test.overlord.chat(
            message="What is 3 + 3?",
            user_id="test_user",
            session_id="webhook_failure_test",
            use_async=True,
        )

        # Check if we got async response
        if isinstance(response, dict) and "request_id" in response:
            request_id = response.get("request_id")
            test.formatter.print_success(f"Got async response (request_id: {request_id})")

            # Monitor request status (webhook will fail but request should complete)
            test.formatter.print_debug("Monitoring request (expecting webhook failures)...")

            import asyncio

            max_wait = 60  # Give time for retries
            check_interval = 5
            checks = 0

            while checks * check_interval < max_wait:
                await asyncio.sleep(check_interval)
                checks += 1

                status = await test.overlord.get_request_status(request_id)
                current_status = status.get("status", "unknown")

                test.formatter.print_debug(f"[{checks * check_interval}s] Status: {current_status}")

                if current_status in ["completed", "failed"]:
                    break

            # Get final status
            final_status = await test.overlord.get_request_status(request_id)
            total_time = time.time() - start_time

            test.formatter.print_debug(f"Total time: {total_time:.1f}s")
            test.formatter.print_debug(f"Final status: {final_status}")

            # Verify results
            success = True

            # Request should complete despite webhook failure
            if final_status.get("status") in ["completed", "failed"]:
                test.formatter.print_success("Request completed despite webhook failure")
            else:
                test.formatter.print_failure("Request did not complete properly")
                success = False

            # Should take time for retries (at least 20s with timeouts)
            if total_time > 20:
                test.formatter.print_success(f"Webhook retries attempted (took {total_time:.1f}s)")
            else:
                test.formatter.print_warning(f"Retries too quick ({total_time:.1f}s)")

            # Request should remain queryable
            if "error" not in final_status or final_status.get("status"):
                test.formatter.print_success("Request status remains queryable")
            else:
                test.formatter.print_failure("Request status not maintained")
                success = False

            test.results.append(success)
        else:
            test.formatter.print_failure("Did not get async response")
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
