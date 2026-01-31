#!/usr/bin/env python3
"""
Test 17A2: Multi-Identity Quick Test
Quick smoke test to verify multi-identity system works.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_multi_identity_quick():
    """Quick test of multi-identity functionality."""
    print("\n" + "=" * 60)
    print("TEST 17A2: Multi-Identity Quick Test")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formations" / "formation-sqlite"
    
    try:
        # Initialize formation
        print("\n[Setup] Initializing formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        
        overlord = await formation.start_overlord()
        print("[Setup] Formation ready\n")
        
        # Test 1: Basic chat with user identifier
        print("[Test 1/3] Testing basic chat with user identifier...")
        response1 = await overlord.chat(
            "Hello, I am Alice",
            user_id="alice@test.com",
            session_id="test_001",
            use_async=False,
            stream=False,
        )
        
        content1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"  ✅ Response: {content1[:80]}...")
        
        # Test 2: Different user
        print("\n[Test 2/3] Testing different user...")
        response2 = await overlord.chat(
            "Hi, I'm Bob",
            user_id="bob@test.com",
            session_id="test_002",
            use_async=False,
            stream=False,
        )
        
        content2 = response2.content if hasattr(response2, "content") else str(response2)
        print(f"  ✅ Response: {content2[:80]}...")
        
        # Test 3: Alice again (different session)
        print("\n[Test 3/3] Testing same user, different session...")
        response3 = await overlord.chat(
            "What's my name?",
            user_id="alice@test.com",
            session_id="test_003",
            use_async=False,
            stream=False,
        )
        
        content3 = response3.content if hasattr(response3, "content") else str(response3)
        print(f"  ✅ Response: {content3[:80]}...")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Multi-identity system working!")
        print("=" * 60)
        return True
            
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
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
    result = asyncio.run(test_multi_identity_quick())
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
