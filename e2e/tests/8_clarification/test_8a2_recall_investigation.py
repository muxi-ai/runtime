#!/usr/bin/env python3
"""
Investigation: Test 8A2 Recall Question Issue

This test investigates why recall questions trigger clarification instead of
checking memory first. We'll trace the complete flow to see where it breaks.

Expected flow:
1. User: "My name is Alice" → Store in memory ✅
2. User: "What is my name?" → Check memory → Return "Alice" ✅

Actual flow:
1. User: "My name is Alice" → Store in memory ✅
2. User: "What is my name?" → Clarification triggered ❌

This test will show us EXACTLY where the issue is.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def investigate_recall_issue():
    """Deep dive into why recall questions trigger clarification."""
    print("\n" + "=" * 80)
    print("INVESTIGATION: Test 8A2 Recall Question Issue")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")

        # Phase 1: Store information
        print("\n" + "=" * 80)
        print("PHASE 1: Store Information")
        print("=" * 80)
        
        print("\nTurn 1: User states 'My name is Alice'")
        response1 = await overlord.chat(
            message="My name is Alice",
            user_id="test_alice",
            session_id="investigation_session",
            stream=False
        )

        content1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"\nResponse 1:")
        print(f"   Length: {len(content1)} chars")
        print(f"   Content: {content1}")
        
        # Wait for memory storage
        print("\n   Waiting 3 seconds for memory storage...")
        await asyncio.sleep(3)

        # Check what's in memory
        print("\n2. Checking memory state...")
        
        # Check buffer memory
        print("\n   A) Buffer Memory:")
        if overlord.buffer_memory:
            buffer_entries = await overlord.search_buffer_memory(
                query=None,
                user_id="test_alice",
                session_id="investigation_session",
                k=10
            )
            print(f"      Found {len(buffer_entries)} entries in buffer")
            for i, entry in enumerate(buffer_entries, 1):
                role = entry.get('role', 'unknown')
                content = entry.get('content', '')[:100]
                print(f"      {i}. Role: {role}, Content: {content}...")
        else:
            print("      No buffer memory available")
        
        # Check persistent memory (long_term_memory)
        print("\n   B) Long-term Memory:")
        if overlord.long_term_memory:
            # Search for "Alice"
            results = await overlord.long_term_memory.search(
                query="Alice",
                user_id="test_alice",
                limit=5
            )
            print(f"      Search for 'Alice': {len(results)} results")
            for i, result in enumerate(results, 1):
                memory_text = str(result.get('content', result.get('text', result)))[:100]
                memory_type = result.get('collection', result.get('type', 'unknown'))
                print(f"      {i}. Type: {memory_type}, Content: {memory_text}...")
        else:
            print("      No long-term memory available")

        # Phase 2: Recall question
        print("\n" + "=" * 80)
        print("PHASE 2: Recall Question")
        print("=" * 80)
        
        print("\nTurn 2: User asks 'What is my name?'")
        
        # Check if clarification system intercepts
        print("\n   Checking clarification system state...")
        clarification_system = overlord.clarification_system
        if clarification_system:
            print(f"      Clarification system: {type(clarification_system).__name__}")
            
            # Check if there are pending clarifications
            if hasattr(clarification_system, '_pending_clarifications'):
                pending = clarification_system._pending_clarifications
                print(f"      Pending clarifications: {len(pending)}")
        
        response2 = await overlord.chat(
            message="What is my name?",
            user_id="test_alice",
            session_id="investigation_session",
            stream=False
        )

        content2 = response2.content if hasattr(response2, "content") else str(response2)
        print(f"\nResponse 2:")
        print(f"   Length: {len(content2)} chars")
        print(f"   Content: {content2}")
        
        # Analyze response
        print("\n3. Analyzing Response 2...")
        
        clarification_indicators = [
            "could you specify",
            "what assistance",
            "need more",
            "clarify",
            "which",
            "what do you mean",
            "can you provide more",
            "could you tell me more"
        ]
        
        found_indicators = [ind for ind in clarification_indicators if ind in content2.lower()]
        
        if found_indicators:
            print(f"   ❌ CLARIFICATION TRIGGERED!")
            print(f"   Found indicators: {found_indicators}")
            print(f"\n   This is the BUG: System asked for clarification instead of recalling from memory")
        else:
            print(f"   ✅ No clarification indicators found")
            
            # Check if "Alice" is in response
            if "alice" in content2.lower():
                print(f"   ✅ Response contains 'Alice' - memory recall worked!")
            else:
                print(f"   ⚠️  Response doesn't mention 'Alice' - but no clarification")

        # Phase 3: Check what context was sent to LLM
        print("\n" + "=" * 80)
        print("PHASE 3: Context Analysis")
        print("=" * 80)
        
        print("\n4. What context should have been available?")
        print("   Expected in enhanced message:")
        print("   - Buffer memory: 'My name is Alice' conversation")
        print("   - Persistent memory: User identity with name=Alice")
        print("   - Vector memory: Relevant past conversations")
        print("\n   The LLM should have seen enough context to answer 'Alice'")
        
        # Cleanup
        print("\n" + "=" * 80)
        print("5. Cleaning up...")
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
    exit_code = asyncio.run(investigate_recall_issue())
    sys.exit(exit_code)
