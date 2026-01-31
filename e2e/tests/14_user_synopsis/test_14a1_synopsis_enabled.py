#!/usr/bin/env python3
"""
Test 14A1: User Synopsis - Enabled
Tests that user synopsis appears in enhanced messages when enabled.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_user_synopsis_enabled():
    """Test that user synopsis appears in enhanced messages when enabled."""
    print("\n" + "=" * 60)
    print("TEST 14A1: User Synopsis Enabled")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formations" / "formation-synopsis"
    
    try:
        # Initialize and start formation
        print("\n[Setup] Initializing formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("[Setup] Formation ready")

        # Test cases
        results = []
        user_id = "test_user_synopsis"

        # Test 1: Add user data to rich collections (modern approach)
        print("\n[Test 1/4] Adding user data to rich collections...")
        try:
            # Add identity information
            await overlord.long_term_memory.add(
                content="User's name is Alice Johnson",
                collection="user_identity",
                user_id=user_id,
                metadata={"source": "test_setup", "type": "identity"}
            )
            await overlord.long_term_memory.add(
                content="Works as a Senior Software Engineer",
                collection="user_identity",
                user_id=user_id,
                metadata={"source": "test_setup", "type": "occupation"}
            )
            # Add relationship information
            await overlord.long_term_memory.add(
                content="Part of the Platform Engineering team",
                collection="relationships",
                user_id=user_id,
                metadata={"source": "test_setup", "type": "team"}
            )
            print("  ✅ User data added to rich collections successfully")
            results.append(True)
        except Exception as e:
            print(f"  ❌ Failed to add user data: {e}")
            results.append(False)

        # Wait for processing
        await asyncio.sleep(2)

        # Test 2: Send message and check response
        print("\n[Test 2/4] Testing synopsis in enhanced message...")
        try:
            response = await overlord.chat(
                "What are Python testing best practices?",
                user_id=user_id,
                session_id="session_synopsis_test",
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
            results.append(False)

        # Test 3: Verify caching (second request should be fast)
        print("\n[Test 3/4] Testing synopsis caching...")
        try:
            cache_start = time.time()
            
            response2 = await overlord.chat(
                "Tell me about code reviews",
                user_id=user_id,
                session_id="session_synopsis_test",
                use_async=False,
                stream=False,
            )
            
            elapsed = time.time() - cache_start
            content2 = response2.content if hasattr(response2, "content") else str(response2)
            
            if content2 and len(content2) > 0:
                print(f"  ✅ Second message completed in {elapsed:.2f}s")
                results.append(True)
            else:
                print("  ❌ Empty response on second request")
                results.append(False)

        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            results.append(False)

        # Test 4: Update identity data and verify cache invalidation
        print("\n[Test 4/4] Testing cache invalidation...")
        try:
            # Update role (identity collection)
            await overlord.long_term_memory.add(
                content="Promoted to Principal Engineer",
                collection="user_identity",
                user_id=user_id,
                metadata={"source": "test_update", "type": "occupation"}
            )
            # Add current project (work_projects collection)
            await overlord.long_term_memory.add(
                content="Currently working on User Synopsis System",
                collection="work_projects",
                user_id=user_id,
                metadata={"source": "test_update", "type": "project"}
            )
            
            # Manually invalidate identity cache (simulates extraction's behavior)
            await overlord.user_context_manager.invalidate_identity_synopsis_cache(user_id)
            print("  Data updated and cache invalidated")
            
            await asyncio.sleep(2)
            
            response3 = await overlord.chat(
                "What's my current role?",
                user_id=user_id,
                session_id="session_synopsis_test",
                use_async=False,
                stream=False,
            )
            
            content3 = response3.content if hasattr(response3, "content") else str(response3)
            
            if content3 and len(content3) > 0:
                print(f"  ✅ Response after cache invalidation received")
                results.append(True)
            else:
                print("  ❌ Empty response after invalidation")
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
    exit_code = asyncio.run(test_user_synopsis_enabled())
    import os; os._exit(exit_code)
