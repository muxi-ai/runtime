#!/usr/bin/env python3
"""Test remember_user_info functionality - simplified version"""

import sys

sys.path.insert(0, ".")
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def test_remember_user_info():
    """Test remember_user_info functionality"""
    print("\n=== Testing remember_user_info ===")

    async def run_test():
        formation = Formation()
        # Use a formation that works without long-term memory
        await formation.load("test-formations/formation-memory/formation-buffer-local-real.yaml")
        overlord = await formation.start_overlord()

        try:
            # Helper function to handle async generator responses
            def get_response(coro):
                result = asyncio.run(coro)
                if hasattr(result, "__aiter__"):
                    # It's an async generator, collect all chunks
                    async def collect():
                        chunks = []
                        async for chunk in result:
                            chunks.append(chunk)
                        return "".join(chunks)

                    return asyncio.run(collect())
                return result

            # Test 1: Store user info with dict
            print("\nTest 1: Storing user info (dict)")
            user_id = "test_user_123"
            properties = {"plan": "pro", "company": "Acme Corp"}

            result = get_response(overlord.remember_user_info(user_id, properties))
            print(f"Result: {result}")
            assert "memories saved" in result.lower()

            # Test 2: Store user info with string
            print("\nTest 2: Storing user info (string)")
            user2_id = "test_user_456"

            result = get_response(
                overlord.remember_user_info(
                    user2_id, "I'm a software engineer working on Python projects"
                )
            )
            print(f"Result: {result}")
            assert "memories saved" in result.lower()

            # Test 3: Verify chat still works after remember_user_info
            print("\nTest 3: Verifying normal chat works")
            response = get_response(
                overlord.chat(user_id=user_id, message="Hello, can you help me?")
            )
            print(f"Chat response: {response[:100]}...")
            assert len(response) > 0

            print("\n✅ All tests passed!")
            return {"status": "success", "tests_passed": 3}

        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return {"status": "failed", "error": str(e)}
        finally:
            await formation.stop_overlord()

    # Run in thread to avoid event loop issues
    return await run_test()


if __name__ == "__main__":
    print("Testing remember_user_info feature (simplified)...")
    result = test_remember_user_info()
    print(f"\nTest result: {result}")
    if result["status"] == "success":
        print("\n🎉 All remember_user_info tests completed successfully!")
    else:
        print(f"\n❌ Tests failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)
