#!/usr/bin/env python3
"""
Test 16A3: LLM Caching - Custom Parameters
Tests that custom cache parameters are applied correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_cache_custom():
    """Test that custom cache parameters are applied."""
    print("\n" + "=" * 60)
    print("TEST 16A3: LLM Caching with Custom Parameters")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formations" / "formation-cache-custom"
    
    try:
        # Initialize and start formation
        print("\n[Setup] Initializing formation with custom cache params...")
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("[Setup] Formation loaded")
        
        # Test cases
        results = []
        
        # Test 1: Verify custom parameters in config
        print("\n[Test 1/4] Verifying custom cache parameters...")
        try:
            cache_config = formation._llm_config.get("settings", {}).get("caching", {})
            
            checks = {
                "enabled": cache_config.get("enabled") is True,
                "max_entries": cache_config.get("max_entries") == 100,
                "p": cache_config.get("p") == 0.90,
                "hash_only": cache_config.get("hash_only") is False,
                "stream_chunk_strategy": cache_config.get("stream_chunk_strategy") == "words",
                "stream_chunk_length": cache_config.get("stream_chunk_length") == 5,
                "ttl": cache_config.get("ttl") == 60,
            }
            
            all_correct = all(checks.values())
            
            if all_correct:
                print(f"  ✅ All custom parameters correct: {cache_config}")
                results.append(True)
            else:
                failed = [k for k, v in checks.items() if not v]
                print(f"  ❌ Some parameters incorrect: {failed}")
                print(f"     Config: {cache_config}")
                results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

        # Test 2: Verify system starts with custom params
        print("\n[Test 2/4] Starting overlord with custom cache...")
        try:
            overlord = await formation.start_overlord()
            print("  ✅ Overlord started successfully with custom cache params")
            results.append(True)
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            import traceback
            traceback.print_exc()
            results.append(False)

        # Test 3: Test basic chat functionality
        print("\n[Test 3/4] Testing chat with custom cache...")
        try:
            response = await overlord.chat(
                "Count from 1 to 3",
                user_id="test_user_custom_cache",
                session_id="session_custom_cache",
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

        # Test 4: Test similar message (should potentially cache with p=0.90)
        print("\n[Test 4/4] Testing similar message (looser similarity)...")
        try:
            response2 = await overlord.chat(
                "Please count from one to three",  # Similar to previous
                user_id="test_user_custom_cache",
                session_id="session_custom_cache_2",
                use_async=False,
                stream=False,
            )

            content2 = response2.content if hasattr(response2, "content") else str(response2)
            
            if content2 and len(content2) > 0:
                print(f"  ✅ Similar message response received ({len(content2)} chars)")
                print("     Note: With p=0.90, similar messages may get cached responses")
                results.append(True)
            else:
                print("  ❌ Empty response on similar message")
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
            print("\nCustom cache parameters:")
            print("  - max_entries: 100 (vs default 10000)")
            print("  - p: 0.90 (vs default 0.95) - looser matching")
            print("  - stream_chunk_strategy: words (vs default sentences)")
            print("  - stream_chunk_length: 5 (vs default 1)")
            print("  - ttl: 60s (vs default 86400s)")
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
    exit_code = asyncio.run(test_cache_custom())
    import os; os._exit(exit_code)
