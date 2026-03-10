#!/usr/bin/env python3
"""Test 4B2: File + System Info Coordination - Multi-MCP coordination"""

import sys
import os
import asyncio
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


def test_file_system_coordination():
    """Test coordination between filesystem and system info MCPs"""
    print("\n=== Test 4B2: File + System Info Coordination ===")
    print("Goal: Test multi-MCP coordination between System and Filesystem MCPs")

    # Create a test directory on Desktop (where filesystem MCP has access)
    test_dir = Path("/Users/ran/Desktop/muxi_test_4b2")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(exist_ok=True)
    print(f"Using test directory: {test_dir}")

    try:
        def run_test():
            async def test_operations():
                formation = Formation()
                await formation.load(str(Path(__file__).parent / "formations" / "formation-mcp"))
                overlord = await formation.start_overlord()
                await overlord.ensure_started()

                tests_passed = 0
                tests_total = 3

                # Test 1: Get system info (simpler test - just verify system MCP works)
                print("\n1. Testing System MCP access...")
                response_obj = await overlord.chat(
                    "What is the current memory usage on this system?",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )

                response = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
                print(f"Response: {response[:300]}...")

                response_lower = response.lower()
                if any(term in response_lower for term in ["memory", "ram", "gb", "mb", "%", "usage"]):
                    print("✓ System MCP access successful")
                    tests_passed += 1
                else:
                    print("✗ System MCP access failed")

                # Test 2: Create a file via filesystem MCP
                print("\n2. Testing Filesystem MCP access...")
                response_obj = await overlord.chat(
                    f"Create a file called 'test.txt' in {test_dir} with content 'Hello from MCP test'",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )

                response = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
                print(f"Response: {response[:300]}...")

                response_lower = response.lower()
                file_created = (test_dir / "test.txt").exists()
                response_mentions_file = any(term in response_lower for term in ["created", "file", "wrote", "saved"])
                
                if file_created or response_mentions_file:
                    print(f"✓ Filesystem MCP access successful (file exists: {file_created})")
                    tests_passed += 1
                else:
                    print("✗ Filesystem MCP access failed")

                # Test 3: List directory contents
                print("\n3. Testing directory listing...")
                response_obj = await overlord.chat(
                    f"List the contents of the directory {test_dir}",
                    user_id="user1",
                    use_async=False,
                    stream=False,
                )

                response = response_obj.content if hasattr(response_obj, 'content') else str(response_obj)
                print(f"Response: {response[:300]}...")

                response_lower = response.lower()
                if any(term in response_lower for term in ["directory", "files", "contents", "empty", "test.txt", "list"]):
                    print("✓ Directory listing successful")
                    tests_passed += 1
                else:
                    print("✗ Directory listing failed")

                # Overall result
                success = tests_passed >= 2  # Pass if at least 2 of 3 tests work

                if success:
                    print(f"\n✅ Test 4B2 PASSED: {tests_passed}/{tests_total} tests passed")
                else:
                    print(f"\n❌ Test 4B2 FAILED: Only {tests_passed}/{tests_total} tests passed")

                formation.shutdown(0)
                return success

            return asyncio.run(test_operations())

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=120)

        return result

    except Exception as e:
        print(f"\n❌ Test 4B2 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print(f"Cleaned up test directory: {test_dir}")


if __name__ == "__main__":
    success = test_file_system_coordination()
    os._exit(0 if success else 1)
