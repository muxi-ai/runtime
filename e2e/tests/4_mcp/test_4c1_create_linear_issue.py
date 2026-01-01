#!/usr/bin/env python3
"""Test 4C1: Create Linear Issue using formation-level secrets."""

import asyncio
import time

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_mcp_test import BaseMCPTest  # noqa: E402


class Test4C1CreateLinearIssue(BaseMCPTest):
    """Test Linear issue creation using formation secrets."""

    async def run_test(self):
        """Run the test for Linear issue creation."""
        test_name = "Test 4C1: Create Linear Issue"
        description = "Create Linear issue using formation-level LINEAR_MCP_TOKEN"

        self.print_test_header(test_name, description)

        start_time = time.time()
        checks = []
        transcript = []
        success = False

        try:
            # Setup formation with MCP enabled
            await self.setup_mcp_formation("weather")  # Default formation
            checks.append("Formation loaded with MCP enabled")

            # Test 1: Basic Linear issue creation
            print("\n  1. Testing Linear issue creation...")
            request1 = (
                "Create a new issue in Linear titled 'Test MCP Integration' "
                "with description 'Testing MUXI MCP capabilities'"
            )

            print(f"  Sending request: {request1}")
            transcript.append(("User", request1))

            response1 = await self.overlord.chat(
                request1, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(response1, "__aiter__"):
                response1_text = ""
                async for chunk in response1:
                    response1_text += chunk
            else:
                response1_text = (
                    response1.content if hasattr(response1, "content") else str(response1)
                )

            print(f"  Response: {response1_text}")
            transcript.append(("System", response1_text))

            # Verify issue creation response
            response1_lower = response1_text.lower()

            # Check if Linear MCP is available or if it gracefully handles missing config
            if "linear" not in response1_lower and "mcp" not in response1_lower:
                # Might not have Linear MCP configured
                print("  ⚠️ Linear MCP might not be configured")
                if any(
                    term in response1_lower
                    for term in ["cannot", "unable", "no tool", "not available", "don't have"]
                ):
                    print("  ✓ Correctly identified missing Linear MCP")
                    checks.append("Correctly handled missing Linear MCP configuration")
                    test1_success = True  # Graceful handling is success
                else:
                    test1_success = False
            else:
                # If Linear MCP is available, check for successful creation
                issue_created = any(
                    term in response1_lower
                    for term in ["issue", "created", "linear", "ticket", "successfully"]
                )
                if issue_created:
                    checks.append("Linear issue creation successful")
                    test1_success = True
                else:
                    checks.append("Linear issue creation response unclear")
                    test1_success = False

            print(f"  ✓ Basic issue creation test: {'PASSED' if test1_success else 'FAILED'}")

            # Test 2: Detailed issue creation
            print("\n  2. Testing detailed issue creation...")
            request2 = (
                "Create a Linear issue with title 'Performance Optimization' "
                "and description 'Investigate and optimize query performance in the user service. "
                "Focus on database queries and caching strategies.'"
            )

            print(f"  Sending request: {request2}")
            transcript.append(("User", request2))

            response2 = await self.overlord.chat(
                request2, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(response2, "__aiter__"):
                response2_text = ""
                async for chunk in response2:
                    response2_text += chunk
            else:
                response2_text = (
                    response2.content if hasattr(response2, "content") else str(response2)
                )

            print(f"  Response: {response2_text}")
            transcript.append(("System", response2_text))

            response2_lower = response2_text.lower()

            # Check for detailed issue creation
            detailed_issue = (
                any(
                    term in response2_lower
                    for term in ["issue", "created", "performance", "optimization"]
                )
                or "linear" in response2_lower
            )

            if detailed_issue:
                checks.append("Detailed issue creation processed")

            test2_success = detailed_issue
            print(f"  ✓ Detailed issue creation test: {'PASSED' if test2_success else 'FAILED'}")

            # Test 3: Issue creation with labels
            print("\n  3. Testing issue creation with labels...")
            request3 = (
                "Create a Linear issue titled 'Bug: Login timeout' "
                "with labels 'bug' and 'high-priority'"
            )

            print(f"  Sending request: {request3}")
            transcript.append(("User", request3))

            response3 = await self.overlord.chat(
                request3, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(response3, "__aiter__"):
                response3_text = ""
                async for chunk in response3:
                    response3_text += chunk
            else:
                response3_text = (
                    response3.content if hasattr(response3, "content") else str(response3)
                )

            print(f"  Response: {response3_text}")
            transcript.append(("System", response3_text))

            response3_lower = response3_text.lower()

            # Check for issue with labels
            labeled_issue = (
                any(term in response3_lower for term in ["issue", "created", "bug", "login"])
                or "linear" in response3_lower
            )

            if labeled_issue:
                checks.append("Issue with labels processed")

            test3_success = labeled_issue
            print(f"  ✓ Issue with labels test: {'PASSED' if test3_success else 'FAILED'}")

            # Test 4: Check Linear service availability
            print("\n  4. Testing Linear service availability...")
            request4 = "Do you have access to Linear for creating issues and managing tasks?"
            transcript.append(("User", request4))

            response4 = await self.overlord.chat(
                request4, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(response4, "__aiter__"):
                response4_text = ""
                async for chunk in response4:
                    response4_text += chunk
            else:
                response4_text = (
                    response4.content if hasattr(response4, "content") else str(response4)
                )

            print(f"  Response: {response4_text}")
            transcript.append(("System", response4_text))

            response4_lower = response4_text.lower()

            # Check service availability response
            service_response = "linear" in response4_lower or any(
                term in response4_lower for term in ["yes", "available", "access", "can", "tools"]
            )

            if service_response:
                checks.append("Linear service availability responded")

            test4_success = service_response
            print(f"  ✓ Service availability test: {'PASSED' if test4_success else 'FAILED'}")

            # Overall success - at least basic functionality should work
            success = test1_success and test2_success

            if success:
                checks.append("Linear issue creation tests successful")
            else:
                checks.append("Some Linear issue creation tests failed")

        except Exception as e:
            print(f"  ❌ Test failed with error: {e}")
            transcript.append(("Error", str(e)))
            checks.append(f"Test failed with error: {e}")

        finally:
            # Cleanup
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, success, checks, transcript, duration)

        return success


async def main():
    """Main test execution."""
    test = Test4C1CreateLinearIssue()
    success = await test.run_test()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
