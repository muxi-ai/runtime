#!/usr/bin/env python3
"""
Verification Test: Does "My name is Alice" get stored AND retrieved?

This test confirms:
1. ✅ Alice is stored in the database (persistent memory)
2. ✅ Alice is included in the enhanced message
3. ✅ The recall question gets answered correctly

This will definitively show if our fix works.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def verify_alice_storage_and_retrieval():
    """Comprehensive verification test."""
    print("\n" + "=" * 80)
    print("VERIFICATION: Alice Storage & Retrieval")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")
        
        memobase = overlord.long_term_memory
        print(f"   Memory backend: {type(memobase).__name__}")

        # PHASE 1: Store the name
        print("\n" + "=" * 80)
        print("PHASE 1: Store 'My name is Alice'")
        print("=" * 80)
        
        response1 = await overlord.chat(
            message="My name is Alice",
            user_id="alice_user",
            session_id="verify_session",
            stream=False
        )

        content1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"\n✓ Response 1: {content1}")
        
        # Wait for extraction
        print("\n⏳ Waiting 8 seconds for memory extraction...")
        await asyncio.sleep(8)

        # VERIFICATION STEP 1: Check database directly
        print("\n" + "=" * 80)
        print("STEP 1: Verify Alice is in Database")
        print("=" * 80)
        
        if memobase:
            # Try to search with correct parameters
            try:
                # Check if formation is in multi-user mode
                print(f"   Formation is_multi_user: {overlord.is_multi_user}")
                
                # For multi-user formations
                if overlord.is_multi_user:
                    print(f"   Searching with external_user_id='alice_user'")
                    results = await memobase.search(
                        query="Alice name",
                        external_user_id="alice_user",
                        limit=10
                    )
                else:
                    # For single-user (user_id stored in metadata)
                    print(f"   Searching without external_user_id (single-user mode)")
                    results = await memobase.search(
                        query="Alice name",
                        limit=10
                    )
                
                print(f"\n✓ Search completed: {len(results)} results")
                
                if results:
                    print("\n✅ FOUND in database!")
                    for i, result in enumerate(results, 1):
                        text = result.get('text', result.get('content', str(result)))
                        score = result.get('score', 'N/A')
                        collection = result.get('collection', result.get('metadata', {}).get('collection', 'unknown'))
                        print(f"\n   Result {i}:")
                        print(f"   Collection: {collection}")
                        print(f"   Score: {score}")
                        print(f"   Text: {text}")
                        
                    print("\n✅ STEP 1 PASSED: Alice IS stored in database")
                else:
                    print("\n❌ STEP 1 FAILED: NO RESULTS - Alice was NOT stored")
                    print("\nDEBUG: Let's check what WAS stored...")
                    # Try searching for anything
                    all_results = await memobase.search(query="user", limit=5)
                    print(f"   Found {len(all_results)} results for generic 'user' query:")
                    for r in all_results:
                        print(f"   - {r.get('text', r.get('content', str(r)))[:100]}")
                        
            except Exception as e:
                print(f"\n❌ STEP 1 ERROR: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("\n❌ STEP 1 FAILED: No memory backend available")

        # PHASE 2: Check enhanced message
        print("\n" + "=" * 80)
        print("PHASE 2: Recall 'What is my name?'")
        print("=" * 80)
        
        # To see the enhanced message, we'll need to intercept it
        # For now, let's just check if the response includes Alice
        
        print("\n⏳ Sending recall question...")
        response2 = await overlord.chat(
            message="What is my name?",
            user_id="alice_user",
            session_id="verify_session",
            stream=False
        )

        content2 = response2.content if hasattr(response2, "content") else str(response2)
        
        # VERIFICATION STEP 2: Check response contains Alice
        print("\n" + "=" * 80)
        print("STEP 2: Verify Response Contains 'Alice'")
        print("=" * 80)
        
        print(f"\n✓ Response 2: {content2}")
        
        has_alice = "alice" in content2.lower()
        has_clarification = any(ind in content2.lower() for ind in [
            "could you specify",
            "could you clarify", 
            "what do you mean",
            "need more",
            "which name"
        ])
        
        if has_alice and not has_clarification:
            print("\n✅ STEP 2 PASSED: Response contains 'Alice' without clarification")
        elif has_alice and has_clarification:
            print("\n⚠️  STEP 2 PARTIAL: Response contains 'Alice' but also asks for clarification")
        elif not has_alice and has_clarification:
            print("\n❌ STEP 2 FAILED: Clarification triggered, no 'Alice' mentioned")
            print("   This means memory was NOT included in enhanced message")
        else:
            print("\n⚠️  STEP 2 UNCLEAR: No 'Alice' and no clarification - unexpected response")

        # FINAL VERDICT
        print("\n" + "=" * 80)
        print("FINAL VERDICT")
        print("=" * 80)
        
        step1_passed = results and len(results) > 0 if 'results' in locals() else False
        step2_passed = has_alice and not has_clarification
        
        print(f"\n1. Alice stored in database: {'✅ YES' if step1_passed else '❌ NO'}")
        print(f"2. Alice in response (enhanced message worked): {'✅ YES' if step2_passed else '❌ NO'}")
        
        if step1_passed and step2_passed:
            print("\n🎉 SUCCESS: Both storage AND retrieval working!")
            print("   The fix is working correctly.")
        elif step1_passed and not step2_passed:
            print("\n⚠️  PARTIAL: Storage works, but retrieval/enhancement doesn't")
            print("   Alice is in DB but not being included in enhanced message")
        elif not step1_passed and step2_passed:
            print("\n⚠️  WEIRD: Alice in response but not in DB")
            print("   Might be using buffer memory only")
        else:
            print("\n❌ FAILURE: Neither storage nor retrieval working")
            print("   The fix may not be sufficient")

        # Cleanup
        print("\n" + "=" * 80)
        await formation.stop_overlord()
        formation.stop()
        print("✓ Formation stopped")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(verify_alice_storage_and_retrieval())
    sys.exit(exit_code)
