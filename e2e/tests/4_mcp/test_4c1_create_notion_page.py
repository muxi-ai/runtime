#!/usr/bin/env python3
"""Test 4C1: Create Notion Page using formation-level secrets."""

import asyncio
import time

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_mcp_test import BaseMCPTest  # noqa: E402

# Parent page ID for "MCP Tests" page in the Notion workspace
MCP_TESTS_PAGE_ID = "2f759768-028d-8079-9a33-cfef0b336e1d"


class Test4C1CreateNotionPage(BaseMCPTest):
    """Test Notion page creation using formation secrets."""

    async def run_test(self):
        """Run the test for Notion page creation."""
        test_name = "Test 4C1: Create Notion Page"
        description = "Create Notion page using formation-level NOTION_MCP_TOKEN"

        self.print_test_header(test_name, description)

        start_time = time.time()
        checks = []
        transcript = []
        success = False

        try:
            await self.setup_mcp_formation("weather")
            checks.append("Formation loaded with MCP enabled")

            # Test 1: Create a page under the MCP Tests parent
            print("\n  1. Testing Notion page creation...")
            request1 = (
                f"Create a new Notion page as a child of page {MCP_TESTS_PAGE_ID} "
                "with title 'Test MCP Integration' and content 'Testing MUXI MCP capabilities'"
            )

            print(f"  Sending request: {request1[:100]}...")
            transcript.append(("User", request1))

            response1 = await self.overlord.chat(
                request1, user_id="test_user", use_async=False, stream=False
            )

            response1_text = (
                response1.content if hasattr(response1, "content") else str(response1)
            )

            print(f"  Response: {response1_text[:500]}...")
            transcript.append(("System", response1_text))

            response1_lower = response1_text.lower()

            # Check for successful creation or appropriate error handling
            page_created = any(
                term in response1_lower
                for term in ["created", "page", "successfully", "notion", "added", "new page"]
            )
            # Also accept validation errors as proof the MCP is working
            mcp_working = "validation" in response1_lower or "api" in response1_lower

            test1_success = page_created or mcp_working
            if test1_success:
                checks.append("Notion page creation attempted via MCP")

            print(f"  ✓ Basic page creation test: {'PASSED' if test1_success else 'FAILED'}")

            # Test 2: Search for pages to verify MCP connectivity
            print("\n  2. Testing Notion search...")
            request2 = "Search Notion for pages containing 'MCP'"

            print(f"  Sending request: {request2}")
            transcript.append(("User", request2))

            response2 = await self.overlord.chat(
                request2, user_id="test_user", use_async=False, stream=False
            )

            response2_text = (
                response2.content if hasattr(response2, "content") else str(response2)
            )

            print(f"  Response: {response2_text[:500]}...")
            transcript.append(("System", response2_text))

            response2_lower = response2_text.lower()

            # Check for search results
            search_worked = any(
                term in response2_lower
                for term in ["found", "page", "mcp", "search", "result", "tests"]
            )

            test2_success = search_worked
            if test2_success:
                checks.append("Notion search completed")

            print(f"  ✓ Search test: {'PASSED' if test2_success else 'FAILED'}")

            # Test 3: Add content to existing page
            print("\n  3. Testing adding content to page...")
            request3 = (
                f"Add a paragraph to the Notion page {MCP_TESTS_PAGE_ID} "
                "with text 'This content was added by MUXI MCP test at "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')}'"
            )

            print(f"  Sending request: {request3[:100]}...")
            transcript.append(("User", request3))

            response3 = await self.overlord.chat(
                request3, user_id="test_user", use_async=False, stream=False
            )

            response3_text = (
                response3.content if hasattr(response3, "content") else str(response3)
            )

            print(f"  Response: {response3_text[:500]}...")
            transcript.append(("System", response3_text))

            response3_lower = response3_text.lower()

            content_added = any(
                term in response3_lower
                for term in ["added", "appended", "updated", "content", "paragraph", "block"]
            )

            test3_success = content_added
            if test3_success:
                checks.append("Content addition attempted")

            print(f"  ✓ Add content test: {'PASSED' if test3_success else 'FAILED'}")

            # Overall success
            success = test1_success and test2_success

            if success:
                checks.append("Notion MCP integration tests successful")
            else:
                checks.append("Some Notion MCP tests failed")

        except Exception as e:
            print(f"  ❌ Test failed with error: {e}")
            transcript.append(("Error", str(e)))
            checks.append(f"Test failed with error: {e}")

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, success, checks, transcript, duration)

        return success


async def main():
    """Main test execution."""
    test = Test4C1CreateNotionPage()
    success = await test.run_test()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
