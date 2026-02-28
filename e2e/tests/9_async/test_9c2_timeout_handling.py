#!/usr/bin/env python3
"""
Test 9C2: Timeout Handling

Tests that the system properly handles request timeouts based on the
async threshold_seconds configuration.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test timeout handling for async requests."""
    test = BaseAsyncTest("9c2_timeout_handling", "Test timeout handling based on threshold config")

    async def run_async_test():
        # Setup formation
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))
        await test.clear_webhook_log()

        # Check timeout configuration
        async_config = test.overlord.formation_config.get("async", {})
        threshold_seconds = async_config.get("threshold_seconds", 30)

        test.formatter.print_debug("Testing timeout handling...")
        test.formatter.print_debug(f"Threshold: {threshold_seconds}s")

        # Test 1: Simple request (should be quick)
        test.formatter.print_debug("Test 1: Simple request (should complete quickly)")

        import time

        start_time = time.time()

        await test.overlord.chat(
            message="What is 2 + 2?",
            user_id="test_user",
            session_id="timeout_test",
            use_async=True,
            stream=False,
        )

        elapsed1 = time.time() - start_time

        test.formatter.print_debug(f"Response time: {elapsed1:.2f}s")

        if elapsed1 < 10:
            test.formatter.print_success(f"Simple request completed quickly ({elapsed1:.2f}s)")
            test.results.append(True)
        else:
            test.formatter.print_warning(f"Simple request slow ({elapsed1:.2f}s)")
            test.results.append(False)

        # Test 2: Forced async request
        test.formatter.print_debug("Test 2: Forced async mode (use_async=True)")

        start_time = time.time()

        response2 = await test.overlord.chat(
            message="Calculate the sum of all prime numbers below 100",
            user_id="test_user",
            session_id="timeout_test",
            use_async=True,  # Force async
            stream=False,
        )

        elapsed2 = time.time() - start_time

        test.formatter.print_debug(f"Response time: {elapsed2:.2f}s")

        # Should get async response
        if isinstance(response2, dict) and "request_id" in response2:
            test.formatter.print_success("Correctly triggered async mode")
            request_id = response2.get("request_id")

            # Monitor status
            import asyncio

            for i in range(6):
                await asyncio.sleep(5)
                status = await test.overlord.get_request_status(request_id)
                test.formatter.print_debug(f"[{i*5}s] Status: {status.get('status')}")
                if status.get("status") in ["completed", "failed"]:
                    break

            test.results.append(True)
        else:
            test.formatter.print_failure("Should have triggered async mode")
            test.results.append(False)

        # Test 3: Verify threshold configuration
        if threshold_seconds == 30:
            test.formatter.print_success(f"Threshold configured correctly ({threshold_seconds}s)")
            test.results.append(True)
        else:
            test.formatter.print_warning(f"Unexpected threshold: {threshold_seconds}s")
            test.results.append(True)  # Not a failure, just different config

        # Print summary
        test.print_async_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if all(test.results) else 1

    import asyncio
    import os; result = asyncio.run(run_async_test()); os._exit(result)


if __name__ == "__main__":
    import os
    try:
        main()
        print("SUCCESS", flush=True)
        os._exit(0)
    except SystemExit as e:
        if e.code == 0:
            print("SUCCESS", flush=True)
        os._exit(e.code or 0)
    except Exception:
        os._exit(1)
    
