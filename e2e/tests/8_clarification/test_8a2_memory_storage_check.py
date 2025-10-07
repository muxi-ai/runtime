#!/usr/bin/env python3
"""
Investigation: Does "My name is Alice" get stored and retrieved?

This test checks:
1. Is "Alice" stored in persistent memory?
2. Is "Alice" in buffer memory?
3. Is "Alice" included in the enhanced message sent to LLM?

This will show us EXACTLY where the breakdown happens.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def investigate_memory_storage():
    """Check if Alice is stored and retrieved."""
    print("\n" + "=" * 80)
    print("INVESTIGATION: Memory Storage & Retrieval for 'My name is Alice'")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")
        
        # Get the database connection for direct queries
        memobase = overlord.long_term_memory
        
        print(f"\n2. Memory backend: {type(memobase).__name__}")

        # Turn 1: Store the name
        print("\n" + "=" * 80)
        print("TURN 1: User says 'My name is Alice'")
        print("=" * 80)
        
        response1 = await overlord.chat(
            message="My name is Alice",
            user_id="alice_test",
            session_id="memory_check_session",
            stream=False
        )

        content1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"\nSystem response: {content1}")
        
        # Wait for memory extraction and storage
        print("\n   Waiting 5 seconds for memory extraction...")
        await asyncio.sleep(5)

        # Check persistent memory storage
        print("\n3. Checking Persistent Memory (Memobase)...")
        
        if memobase:
            # Check user_identity collection
            print("\n   A) Querying user_identity collection for 'Alice':")
            try:
                # Direct search
                identity_results = await memobase.search(
                    query="Alice",
                    user_id="alice_test",
                    collection="user_identity",
                    limit=5
                )
                print(f"      Found {len(identity_results)} results in user_identity")
                for i, result in enumerate(identity_results, 1):
                    print(f"      {i}. {result}")
                
                if not identity_results:
                    print("      ⚠️  NO RESULTS in user_identity - name may not have been extracted!")
            except Exception as e:
                print(f"      Error searching user_identity: {e}")
            
            # Check default collection
            print("\n   B) Querying default collection for 'Alice':")
            try:
                default_results = await memobase.search(
                    query="Alice",
                    user_id="alice_test",
                    limit=10
                )
                print(f"      Found {len(default_results)} results in default collection")
                for i, result in enumerate(default_results, 1):
                    print(f"      {i}. {result}")
            except Exception as e:
                print(f"      Error searching default: {e}")
            
            # Check all collections
            print("\n   C) Searching ALL collections for 'name' or 'Alice':")
            collections = ["user_identity", "preferences", "work_projects", "relationships", "activities", "default"]
            total_found = 0
            for coll in collections:
                try:
                    results = await memobase.search(
                        query="name Alice",
                        user_id="alice_test",
                        collection=coll,
                        limit=5
                    )
                    if results:
                        print(f"      {coll}: {len(results)} results")
                        for r in results:
                            print(f"         - {r}")
                        total_found += len(results)
                except Exception as e:
                    # Collection might not exist
                    pass
            
            if total_found == 0:
                print(f"      ❌ NO RESULTS FOUND in ANY collection!")
                print(f"      This means 'My name is Alice' was NOT extracted to persistent memory")
        else:
            print("   ⚠️  No memobase available")

        # Check buffer memory
        print("\n4. Checking Buffer Memory...")
        if overlord.buffer_memory:
            # Try to get recent messages
            print("   Looking for conversation history in buffer...")
            
            # The buffer stores raw messages - let's check via the KV store
            # The key format is: f"{user_id}:{session_id}:messages"
            try:
                # Try to access buffer directly
                print(f"   Buffer type: {type(overlord.buffer_memory).__name__}")
                
                # Check if there's a way to list keys
                if hasattr(overlord.buffer_memory, 'kv_get'):
                    # Try to get the messages list
                    messages_key = f"alice_test:memory_check_session:messages"
                    buffer_data = await overlord.buffer_memory.kv_get(messages_key)
                    if buffer_data:
                        print(f"   ✅ Found buffer data: {len(str(buffer_data))} chars")
                        print(f"   Buffer preview: {str(buffer_data)[:200]}...")
                    else:
                        print(f"   ⚠️  No buffer data found for key: {messages_key}")
                
            except Exception as e:
                print(f"   Error checking buffer: {e}")
        else:
            print("   ⚠️  No buffer memory available")

        # Turn 2: Ask for the name
        print("\n" + "=" * 80)
        print("TURN 2: User asks 'What is my name?'")
        print("=" * 80)
        
        print("\nBefore sending, let's predict what SHOULD happen:")
        print("   Expected enhanced message should contain:")
        print("   - Buffer: Recent conversation with 'My name is Alice'")
        print("   - Persistent: user_identity with name=Alice (if extracted)")
        print("   - Result: LLM should answer 'Alice' without clarification")
        
        response2 = await overlord.chat(
            message="What is my name?",
            user_id="alice_test",
            session_id="memory_check_session",
            stream=False
        )

        content2 = response2.content if hasattr(response2, "content") else str(response2)
        print(f"\nSystem response: {content2}")
        
        # Analyze
        print("\n5. Analysis...")
        
        clarification_indicators = [
            "could you specify",
            "what assistance",
            "need more",
            "clarify",
            "what do you mean",
            "can you provide more"
        ]
        
        has_clarification = any(ind in content2.lower() for ind in clarification_indicators)
        has_alice = "alice" in content2.lower()
        
        print(f"\n   Has clarification indicators: {has_clarification}")
        print(f"   Contains 'Alice': {has_alice}")
        
        if has_clarification:
            print("\n   ❌ CLARIFICATION WAS TRIGGERED")
            print("   This suggests:")
            print("   1. Memory was not included in enhanced message, OR")
            print("   2. Clarification check happens BEFORE memory retrieval, OR")
            print("   3. Memory extraction failed to store 'Alice'")
        elif has_alice:
            print("\n   ✅ MEMORY RECALL WORKED!")
            print("   System correctly retrieved and used 'Alice' from memory")
        else:
            print("\n   ⚠️  UNCLEAR - no clarification but no 'Alice' mentioned either")

        # Cleanup
        print("\n6. Cleaning up...")
        await formation.stop_overlord()
        formation.stop()
        print("   ✓ Formation stopped")

    except Exception as e:
        print(f"\n✗ Investigation failed: {str(e)}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("INVESTIGATION COMPLETE")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(investigate_memory_storage())
    sys.exit(exit_code)
