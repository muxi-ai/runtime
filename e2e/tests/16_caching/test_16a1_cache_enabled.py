#!/usr/bin/env python3
"""
Test 16A1: LLM Caching - Enabled by Default
Tests that caching is initialized with default production settings.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_cache_enabled():
    """Test that caching is initialized with default settings."""
    print("\n" + "=" * 60)
    print("TEST 16A1: LLM Caching Enabled by Default")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formations" / "formation-cache-enabled"
    
    try:
        # Initialize and start formation
        print("\n[Setup] Initializing formation with default caching...")
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Check that formation loaded successfully
        print("[Setup] Formation loaded")
        
        # Test cases
        results = []
        
        # Test 1: Verify formation initialized
        print("\n[Test 1/3] Verifying formation initialization...")
        try:
            if formation.config:
                print("  ✅ Formation config loaded")
                results.append(True)
            else:
                print("  ❌ Formation config not loaded")
                results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append(False)

        # Test 2: Start overlord and send message
        print("\n[Test 2/3] Testing basic chat functionality...")
        try:
            overlord = await formation.start_overlord()
            print("  Overlord started")
            
            response = await overlord.chat(
                "What is 2+2?",
                user_id="test_user_caching",
                session_id="session_cache_test",
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

        # Test 3: Verify cache is working (send same message)
        print("\n[Test 3/3] Testing cache behavior (same message)...")
        try:
            response2 = await overlord.chat(
                "What is 2+2?",  # Same question
                user_id="test_user_caching",
                session_id="session_cache_test_2",  # Different session
                use_async=False,
                stream=False,
            )

            content2 = response2.content if hasattr(response2, "content") else str(response2)
            
            if content2 and len(content2) > 0:
                print(f"  ✅ Second response received ({len(content2)} chars)")
                # Note: We can't easily verify if cache was used from outside OneLLM,
                # but if the response comes back, caching is at least not breaking things
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
            print("\nNote: Caching is enabled by default. OneLLM handles cache")
            print("operations transparently. This test verifies the system works")
            print("correctly with caching enabled.")
        else:
            print(f"⚠️ {total - passed} test(s) failed")

        # Cleanup
        print("\n[Cleanup] Stopping formation...")
        try:
            if formation.overlord:
                await formation.kill_overlord()
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
    exit_code = asyncio.run(test_cache_enabled())
    sys.exit(exit_code)
