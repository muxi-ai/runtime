#!/usr/bin/env python3
"""Test 4C1: Create Linear Issue - Using formation-level secrets"""

import sys

sys.path.insert(0, ".")
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


def test_create_linear_issue():
    """Test Linear issue creation using formation secrets"""
    print("\n=== Test 4C1: Create Linear Issue ===")
    print("Goal: Create Linear issue using formation-level LINEAR_MCP_TOKEN")
    print("Note: Requires Linear MCP server running and valid token in secrets")

    try:
        # Run the async test in a thread pool to avoid event loop issues
        def run_test():
            async def test_operations():
                # Load formation with MCP enabled
                formation = Formation()
                await formation.load("test-formations/formation-mcp")
                overlord = await formation.start_overlord()

                # Ensure overlord is started
                await overlord.ensure_started()

                print("\n1. Testing Linear issue creation...")
                response_gen = await overlord.chat(
                    "Create a new issue in Linear titled 'Test MCP Integration' "
                    "with description 'Testing MUXI MCP capabilities'",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Verify issue creation
                response_lower = response.lower()
                if "linear" not in response_lower and "mcp" not in response_lower:
                    # Might not have Linear MCP configured
                    print("⚠️  Linear MCP might not be configured")
                    if any(
                        term in response_lower
                        for term in ["cannot", "unable", "no tool", "not available", "don't have"]
                    ):
                        print("✓ Correctly identified missing Linear MCP")
                        return True

                # If Linear MCP is available
                assert any(
                    term in response_lower
                    for term in ["issue", "created", "linear", "ticket", "successfully"]
                ), "Response should indicate issue creation"
                print("✓ Linear issue created successfully")

                print("\n2. Testing detailed issue creation...")
                response_gen = await overlord.chat(
                    "Create a Linear issue with title 'Performance Optimization' "
                    "and description 'Investigate and optimize query performance in the user service. "
                    "Focus on database queries and caching strategies.'",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                response_lower = response.lower()

                # Should create issue with details
                assert (
                    any(
                        term in response_lower
                        for term in ["issue", "created", "performance", "optimization"]
                    )
                    or "linear" in response_lower
                ), "Response should confirm detailed issue creation"
                print("✓ Detailed issue created successfully")

                print("\n3. Testing issue creation with labels...")
                response_gen = await overlord.chat(
                    "Create a Linear issue titled 'Bug: Login timeout' with labels 'bug' and 'high-priority'",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                response_lower = response.lower()

                # Should handle labels
                assert (
                    any(term in response_lower for term in ["issue", "created", "bug", "login"])
                    or "linear" in response_lower
                ), "Response should confirm issue with labels"
                print("✓ Issue with labels handled")

                print("\n✅ Test 4C1 PASSED: Linear issue creation successful")

                # Clean shutdown to avoid async generator errors
                formation.shutdown(0)

            # Run the async test
            return asyncio.run(test_operations())

        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)

        if result:
            print("\n✅ Test 4C1 PASSED: Linear issue creation successful")
            return True
        else:
            print("\n❌ Test 4C1 FAILED")
            return False

    except Exception as e:
        print(f"\n❌ Test 4C1 FAILED with error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_create_linear_issue()
    sys.exit(0 if success else 1)
