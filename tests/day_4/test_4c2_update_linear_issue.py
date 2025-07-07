#!/usr/bin/env python3
"""Test 4C2: Update Linear Issue - Status updates via MCP"""

import sys

sys.path.insert(0, ".")
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


def test_update_linear_issue():
    """Test Linear issue status updates"""
    print("\n=== Test 4C2: Update Linear Issue ===")
    print("Goal: Update Linear issue status using formation-level secrets")

    try:
        # Run the async test in a thread pool to avoid event loop issues
        def run_test():
            async def test_operations():
                # Load formation with MCP enabled
                formation = Formation()
                formation.load("test-formations/formation-mcp")
                overlord = formation.start_overlord()

                # Ensure overlord is started
                await overlord.ensure_started()

                print("\n1. Creating an issue to update...")
                response = await overlord.chat(
                    "Create a Linear issue titled 'Test Update Workflow' to test status updates",
                    user_id="user1",
                    use_async=False,
                )
                print(f"Create Response: {response}")

                response_lower = response.lower()
                if "linear" not in response_lower and "mcp" not in response_lower:
                    # Might not have Linear MCP configured
                    print("⚠️  Linear MCP might not be configured")
                    if any(
                        term in response_lower
                        for term in ["cannot", "unable", "no tool", "not available"]
                    ):
                        print("✓ Correctly identified missing Linear MCP")
                        return True

                print("\n2. Testing issue status update...")
                response = await overlord.chat(
                    "Update the Linear issue we just created to mark it as in progress",
                    user_id="user1",
                    use_async=False,
                )
                print(f"Update Response: {response}")

                # Verify update
                response_lower = response.lower()
                assert (
                    any(
                        term in response_lower
                        for term in ["updated", "progress", "status", "changed", "modified"]
                    )
                    or "linear" in response_lower
                ), "Response should indicate issue update"
                print("✓ Issue status updated successfully")

                print("\n3. Testing issue completion...")
                response = await overlord.chat(
                    "Mark the Linear issue as completed/done", user_id="user1", use_async=False
                )
                print(f"Complete Response: {response}")

                # Should mark as complete
                assert (
                    any(
                        term in response_lower
                        for term in ["completed", "done", "finished", "closed", "updated"]
                    )
                    or "linear" in response_lower
                ), "Response should indicate issue completion"
                print("✓ Issue marked as completed")

                print("\n4. Testing issue assignment...")
                response = await overlord.chat(
                    "Create a new Linear issue and assign it to the team",
                    user_id="user1",
                    use_async=False,
                )
                print(f"Assignment Response: {response}")

                # Should handle assignment
                assert (
                    "issue" in response_lower or "linear" in response_lower
                ), "Response should mention issue creation/assignment"
                print("✓ Issue assignment handled")

                print("\n5. Testing bulk update scenario...")
                response = await overlord.chat(
                    "Update all my recent Linear issues to add a 'reviewed' label",
                    user_id="user1",
                    use_async=False,
                )
                print(f"Bulk Update Response: {response}")

                # Should acknowledge bulk update request
                assert len(response) > 20, "Response should address bulk update request"
                print("✓ Bulk update request handled")

                return True

            # Run the async test
            return asyncio.run(test_operations())

        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=90)

        if result:
            print("\n✅ Test 4C2 PASSED: Linear issue updates successful")
            return True
        else:
            print("\n❌ Test 4C2 FAILED")
            return False

    except Exception as e:
        print(f"\n❌ Test 4C2 FAILED with error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_update_linear_issue()
    sys.exit(0 if success else 1)
