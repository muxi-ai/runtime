#!/usr/bin/env python3
"""
Test 16A2: LLM Caching - Explicitly Disabled
Tests that caching can be disabled via configuration.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_cache_disabled():
    """Test that caching can be explicitly disabled."""
    print("\n" + "=" * 60)
    print("TEST 16A2: LLM Caching Explicitly Disabled")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formations" / "formation-cache-disabled"
    
    try:
        # Initialize and start formation
        print("\n[Setup] Initializing formation with caching disabled...")
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("[Setup] Formation loaded")
        
        # Test cases
        results = []
        
        # Test 1: Verify caching is disabled in config
        print("\n[Test 1/3] Verifying cache disabled in config...")
        try:
            cache_config = formation._llm_config.get("settings", {}).get("caching", {})
            is_enabled = cache_config.get("enabled", True)  # Default is True
            
            if is_enabled is False:
                print(f"  ✅ Caching is disabled in config: {cache_config}")
                results.append(True)
            else:
                print(f"  ❌ Caching is still enabled: {cache_config}")
                results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append(False)

        # Test 2: Verify system works with caching disabled
        print("\n[Test 2/3] Testing chat with caching disabled...")
        try:
            overlord = await formation.start_overlord()
            print("  Overlord started")
            
            response = await overlord.chat(
                "What is the capital of France?",
                user_id="test_user_no_cache",
                session_id="session_no_cache",
                use_async=False,
                stream=False,
            )

            content = response.content if hasattr(response, "content") else str(response)
            
            if content and len(content) > 0:
                print(f"  ✅ Response received ({len(content)} chars)")
                results.append(True)
            else:
                print("  ❌ Empty response received")
                results.append(False)

        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            import traceback
            traceback.print_exc()
            results.append(False)

        # Test 3: Verify multiple requests work
        print("\n[Test 3/3] Testing multiple requests...")
        try:
            response2 = await overlord.chat(
                "What is 5+5?",
                user_id="test_user_no_cache",
                session_id="session_no_cache",
                use_async=False,
                stream=False,
            )

            content2 = response2.content if hasattr(response2, "content") else str(response2)
            
            if content2 and len(content2) > 0:
                print(f"  ✅ Second response received ({len(content2)} chars)")
                results.append(True)
            else:
                print("  ❌ Empty response on second request")
                results.append(False)

        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            results.append(False)

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        passed = sum(results)
        total = len(results)

        print(f"Passed: {passed}/{total}")

        if all(results):
            print("🎉 ALL TESTS PASSED!")
            print("\nNote: System works correctly with caching disabled.")
            print("This is useful for development to see immediate prompt changes.")
        else:
            print(f"⚠️ {total - passed} test(s) failed")

        # Cleanup
        print("\n[Cleanup] Stopping formation...")
        try:
            if formation.overlord:
                await formation.stop_overlord()
            print("[Cleanup] Complete")
        except Exception as cleanup_error:
            print(f"[Cleanup] Warning: {cleanup_error}")

        return 0 if all(results) else 1

    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_cache_disabled())
    import os; os._exit(exit_code)
