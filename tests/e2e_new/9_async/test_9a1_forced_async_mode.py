#!/usr/bin/env python3
"""
Test 9A1: Forced Async Mode

Tests that when use_async=True is explicitly set, the system processes the request
asynchronously regardless of complexity or estimated duration.
"""

import sys

from .base_async_test import BaseAsyncTest
def main():
    """Test forced async mode."""
    test = BaseAsyncTest("9a1_forced_async_mode", "Test forced async mode with use_async=True")

    # Test runs a simple math query with forced async mode

    async def run_async_test():
        # Setup formation using the shared async formation
        await test.setup_formation(yaml_name="formation-async.yaml")

        # Run the forced async test
        result = await test.test_async_request(
            message="What is 2 + 2?",
            user_id="test_user",
            session_id="async_test_9a1",
            expected_content="4",
            should_be_async=True
        )

        # Record result
        test.results.append(result["success"])

        if result["success"]:
            test.formatter.print_success("Forced async mode test passed")

            # Store transcript
            if result["webhook"]:
                response_content = ""
                response_data = result["webhook"].get('response', [])
                for item in response_data:
                    if item.get('type') == 'text':
                        response_content = item.get('text', '')
                        break

                test.transcript.append(("What is 2 + 2?", response_content))
        else:
            test.formatter.print_failure("Forced async mode test failed")

        # Print async-specific summary
        test.print_async_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if result["success"] else 1

    return test.run_in_event_loop(
        "9a1_forced_async_mode",
        "Test forced async mode with use_async=True",
        "9_async",
        [],  # We handle test cases manually in run_async_test
        None,  # Use pattern-based formation path
        "formation-async.yaml",  # Use shared formation
    )
if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
