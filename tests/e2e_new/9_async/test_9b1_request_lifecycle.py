#!/usr/bin/env python3
"""
Test 9B1: Request Lifecycle Management

This test verifies the request status tracking and cancellation APIs
during async workflow execution.
"""

import sys

from .base_async_test import BaseAsyncTest


def main():
    """Test request lifecycle management."""
    test = BaseAsyncTest("9b1_request_lifecycle", "Test request lifecycle management APIs")

    async def run_lifecycle_test():
        # Setup formation using the shared async formation
        await test.setup_formation(yaml_name="formation-async.yaml")

        # First, create an async request to test lifecycle on
        result = await test.test_async_request(
            message="What is 2+2? Please show your work.",
            user_id="user_123",
            session_id="session_456",
            expected_content="4",
            should_be_async=True,
        )

        success = result["success"]
        request_id = result.get("request_id")

        if request_id:
            # Test the lifecycle management APIs
            lifecycle_results = await test.test_request_lifecycle(request_id)

            # Add lifecycle test results
            success = success and all(lifecycle_results.values())

            test.formatter.print_section("Lifecycle Test Results")
            for test_name, passed in lifecycle_results.items():
                status = "PASSED" if passed else "FAILED"
                test.formatter.print_info(f"  {test_name}: {status}")

        # Record result
        test.results.append(success)

        # Store transcript for the main request
        if result["webhook"]:
            response_content = ""
            response_data = result["webhook"].get("response", [])
            for item in response_data:
                if item.get("type") == "text":
                    response_content = item.get("text", "")
                    break

            test.transcript.append(("What is 2+2? Please show your work.", response_content))

        # Print async-specific summary
        test.print_async_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if success else 1

    return test.run_in_event_loop(
        "9b1_request_lifecycle",
        "Test request lifecycle management APIs",
        "9_async",
        [],  # We handle test cases manually
        None,  # Use pattern-based formation path
        "formation-async.yaml",  # Use shared formation
    )


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
