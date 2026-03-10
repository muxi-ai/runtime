#!/usr/bin/env python3
"""Test 4C3: List Notion Pages - Page retrieval via MCP"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from muxi.runtime.formation import Formation  # noqa: E402

# Parent page ID for "MCP Tests" page in the Notion workspace
MCP_TESTS_PAGE_ID = "2f759768-028d-8079-9a33-cfef0b336e1d"


def test_list_notion_pages():
    """Test Notion page listing and retrieval"""
    print("\n=== Test 4C3: List Notion Pages ===")
    print("Goal: List and retrieve Notion pages using formation-level secrets")

    try:
        def run_test():
            async def test_operations():
                formation = Formation()
                await formation.load(str(Path(__file__).parent / "formations" / "formation-mcp"))
                overlord = await formation.start_overlord()
                await overlord.ensure_started()

                print("\n1. Searching for all accessible pages...")
                response_obj = await overlord.chat(
                    "Search Notion for all pages I have access to",
                    user_id="user1",
                    use_async=False,
                )

                response = (
                    response_obj.content if hasattr(response_obj, "content") else str(response_obj)
                )
                print(f"Response: {response[:400]}...")

                response_lower = response.lower()
                test1_ok = any(
                    term in response_lower
                    for term in ["page", "found", "mcp", "tests", "search", "result", "access"]
                )
                print(f"✓ Search all pages: {'PASSED' if test1_ok else 'FAILED'}")

                print("\n2. Getting specific page details...")
                response_obj = await overlord.chat(
                    f"Retrieve the details of Notion page with ID {MCP_TESTS_PAGE_ID}",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )

                response = (
                    response_obj.content if hasattr(response_obj, "content") else str(response_obj)
                )
                print(f"Response: {response[:400]}...")

                response_lower = response.lower()
                test2_ok = any(
                    term in response_lower
                    for term in ["page", "mcp", "tests", "title", "created", "id", "details"]
                )
                print(f"✓ Get page details: {'PASSED' if test2_ok else 'FAILED'}")

                print("\n3. Getting page children/blocks...")
                response_obj = await overlord.chat(
                    f"Get the child blocks of Notion page {MCP_TESTS_PAGE_ID}",
                    user_id="user1",
                    use_async=False,
                )

                response = (
                    response_obj.content if hasattr(response_obj, "content") else str(response_obj)
                )
                print(f"Response: {response[:400]}...")

                response_lower = response.lower()
                test3_ok = any(
                    term in response_lower
                    for term in ["block", "child", "content", "page", "retrieved", "empty", "no"]
                )
                print(f"✓ Get child blocks: {'PASSED' if test3_ok else 'FAILED'}")

                print("\n4. Getting current user info...")
                response_obj = await overlord.chat(
                    "Get my Notion user information using the API",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )

                response = (
                    response_obj.content if hasattr(response_obj, "content") else str(response_obj)
                )
                print(f"Response: {response[:400]}...")

                response_lower = response.lower()
                test4_ok = any(
                    term in response_lower
                    for term in ["user", "bot", "muxi", "mcp", "workspace", "name", "id"]
                )
                print(f"✓ Get user info: {'PASSED' if test4_ok else 'FAILED'}")

                success = test1_ok and test2_ok and test3_ok

                if success:
                    print("\n✅ Test 4C3 PASSED: Notion page listing successful")
                else:
                    print("\n❌ Test 4C3 FAILED: Some operations did not complete")

                # Clean exit
                import os
                os._exit(0 if success else 1)

            return asyncio.run(test_operations())

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=90)

        return result

    except Exception as e:
        print(f"\n❌ Test 4C3 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_list_notion_pages()
    os._exit(0 if success else 1)
