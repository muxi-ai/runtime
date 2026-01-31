#!/usr/bin/env python3
"""
Test 17A1: Multi-Identity with SQLite Backend
Tests that multi-identity user management works correctly with SQLite.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_sqlite_multi_identity():
    """Test multi-identity with SQLite backend."""
    print("\n" + "=" * 60)
    print("TEST 17A1: Multi-Identity with SQLite")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formations" / "formation-sqlite"
    
    try:
        # Initialize formation
        print("\n[Setup] Initializing formation with SQLite...")
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("[Setup] Starting overlord...")
        overlord = await formation.start_overlord()
        print("[Setup] Formation ready")
        
        # Test results
        results = []
        
        # Test 1: User with email identifier
        print("\n[Test 1/4] Testing user with email identifier...")
        try:
            response1 = await overlord.chat(
                "Hi! I'm Alice and I love Python programming.",
                user_id="alice@company.com",
                session_id="session_001",
                use_async=False,
                stream=False,
            )
            
            content1 = response1.content if hasattr(response1, "content") else str(response1)
            
            if content1 and len(content1) > 0:
                print(f"  ✅ Response received ({len(content1)} chars)")
                results.append(True)
            else:
                print("  ❌ Empty response")
                results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            results.append(False)
        
        # Wait for memory extraction
        await asyncio.sleep(2)
        
        # Test 2: Different user to verify isolation
        print("\n[Test 2/4] Testing different user isolation...")
        try:
            response2 = await overlord.chat(
                "Hello, I'm Bob and I prefer JavaScript!",
                user_id="bob@company.com",
                session_id="session_002",
                use_async=False,
                stream=False,
            )
            
            content2 = response2.content if hasattr(response2, "content") else str(response2)
            
            if content2 and len(content2) > 0:
                print(f"  ✅ Bob's response received ({len(content2)} chars)")
                results.append(True)
            else:
                print("  ❌ Empty response")
                results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            results.append(False)
        
        await asyncio.sleep(1)
        
        # Test 3: Alice asks about her preference
        print("\n[Test 3/4] Testing memory recall for Alice...")
        try:
            response3 = await overlord.chat(
                "What programming language do I like?",
                user_id="alice@company.com",
                session_id="session_003",
                use_async=False,
                stream=False,
            )
            
            content3 = response3.content if hasattr(response3, "content") else str(response3)
            
            if "python" in content3.lower():
                print(f"  ✅ Alice's preference remembered: {content3[:100]}...")
                results.append(True)
            else:
                print(f"  ❌ Memory not recalled: {content3[:100]}...")
                results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            results.append(False)
        
        # Test 4: Bob asks about his preference
        print("\n[Test 4/4] Testing memory recall for Bob...")
        try:
            response4 = await overlord.chat(
                "What programming language do I prefer?",
                user_id="bob@company.com",
                session_id="session_004",
                use_async=False,
                stream=False,
            )
            
            content4 = response4.content if hasattr(response4, "content") else str(response4)
            
            if "javascript" in content4.lower():
                print(f"  ✅ Bob's preference remembered: {content4[:100]}...")
                results.append(True)
            else:
                print(f"  ❌ Memory not recalled: {content4[:100]}...")
                results.append(False)
        except Exception as e:
            print(f"  ❌ ERROR: {str(e)[:100]}")
            results.append(False)
        
        # Final results
        print("\n" + "=" * 60)
        print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
        print("=" * 60)
        
        if all(results):
            print("✅ ALL TESTS PASSED")
            return True
        else:
            print(f"❌ SOME TESTS FAILED: {results}")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'overlord' in locals():
            try:
                await overlord.cleanup()
            except:
                pass


def main():
    """Run the test."""
    result = asyncio.run(test_sqlite_multi_identity())
    import os; os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
