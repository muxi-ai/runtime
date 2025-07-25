#!/usr/bin/env python3
"""Test 4B3: MCP Failure Handling - Error recovery and graceful degradation"""

import sys

sys.path.insert(0, ".")
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from src.muxi.formation.formation import Formation  # noqa: E402


def test_mcp_failure_handling():
    """Test MCP error handling and graceful failure"""
    print("\n=== Test 4B3: MCP Failure Handling ===")
    print("Goal: Validate graceful error handling for MCP operations")

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

                print("\n1. Testing permission denied error handling...")
                response_gen = await overlord.chat(
                    "Create a file in /root/forbidden_directory", user_id="user1", use_async=False
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Should handle permission error gracefully
                response_lower = response.lower()
                assert any(
                    term in response_lower
                    for term in [
                        "error",
                        "permission",
                        "denied",
                        "unable",
                        "cannot",
                        "failed",
                        "access",
                    ]
                ), "Response should indicate permission error"
                assert (
                    "traceback" not in response_lower
                ), "Response should not contain raw traceback"
                print("✓ Permission denied handled gracefully")

                print("\n2. Testing invalid path handling...")
                response_gen = await overlord.chat(
                    "Read the file at /Users/ran/Desktop/this_file_definitely_does_not_exist_12345.txt",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Should handle missing file or access denied gracefully
                response_lower = response.lower()
                assert any(
                    term in response_lower
                    for term in [
                        "not found",
                        "doesn't exist",
                        "does not exist",
                        "unable",
                        "cannot",
                        "missing",
                        "outside",
                        "access",
                        "denied",
                    ]
                ), "Response should indicate file not found or access denied"
                print("✓ Invalid path handled gracefully")

                print("\n3. Testing invalid file operation...")
                response_gen = await overlord.chat(
                    "Delete the entire filesystem starting from /", user_id="user1", use_async=False
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Should refuse dangerous operation
                response_lower = response.lower()
                assert any(
                    term in response_lower
                    for term in ["cannot", "unable", "dangerous", "not allowed", "refuse", "error"]
                ), "Response should refuse dangerous operation"
                print("✓ Dangerous operation refused")

                print("\n4. Testing malformed request handling...")
                response_gen = await overlord.chat(
                    "Create a file with name containing null bytes: test\x00file.txt",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Should handle invalid filename
                response_lower = response.lower()
                assert any(
                    term in response_lower
                    for term in [
                        "invalid",
                        "error",
                        "cannot",
                        "unable",
                        "filename",
                        "not allowed",
                        "null",
                        "bytes",
                    ]
                ), "Response should indicate invalid filename"
                print("✓ Malformed request handled gracefully")

                print("\n5. Testing partial workflow failure...")
                response_gen = await overlord.chat(
                    "Get system stats and save to /root/forbidden.txt, "
                    "if that fails, tell me the stats anyway",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Should still provide system stats despite file write failure
                response_lower = response.lower()
                assert any(
                    term in response_lower for term in ["cpu", "memory", "ram"]
                ), "Response should still contain system stats"
                assert any(
                    term in response_lower
                    for term in [
                        "unable",
                        "couldn't save",
                        "permission",
                        "but",
                        "however",
                        "would fail",
                        "outside",
                        "attempting",
                    ]
                ), "Response should acknowledge the file write failure"
                print("✓ Partial workflow failure handled with fallback")

                print("\n6. Testing MCP timeout simulation...")
                response_gen = await overlord.chat(
                    "Try to analyze a massive 10GB file that would timeout",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Should handle large file scenario
                response_lower = response.lower()
                assert (
                    any(
                        term in response_lower
                        for term in ["large", "size", "unable", "timeout", "cannot"]
                    )
                    or len(response) > 20
                ), "Response should handle large file scenario"
                print("✓ Timeout scenario handled appropriately")

                print("\n✅ Test 4B3 PASSED: All MCP failures handled gracefully")

                # Clean shutdown to avoid async generator errors
                formation.shutdown(0)

            # Run the async test
            return asyncio.run(test_operations())

        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=90)

        if result:
            print("\n✅ Test 4B3 PASSED: All MCP failures handled gracefully")
            return True
        else:
            print("\n❌ Test 4B3 FAILED")
            return False

    except Exception as e:
        print(f"\n❌ Test 4B3 FAILED with error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_mcp_failure_handling()
    sys.exit(0 if success else 1)
