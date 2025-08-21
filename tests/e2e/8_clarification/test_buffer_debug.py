#!/usr/bin/env python3
"""
Debug test to check if buffer memory context is being included in requests.
This is a diagnostic test to understand the current behavior.
"""
import asyncio
import sys
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_buffer_memory_inclusion():
    """Test if buffer memory context is included in subsequent requests."""
    print("\n=== Debug Test: Buffer Memory Context Inclusion ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_buffer_debug")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    # First, let's check the formation's buffer memory configuration
    print("\n1. Checking buffer memory configuration...")
    if hasattr(overlord, 'buffer_memory'):
        print(f"   Buffer memory enabled: {overlord.buffer_memory is not None}")
        if overlord.buffer_memory:
            print(f"   Buffer size: {getattr(overlord.buffer_memory, 'size', 'unknown')}")
    else:
        print("   No buffer_memory attribute found on overlord")
    
    try:
        # Send first message
        print("\n2. Sending first message...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "My favorite color is blue",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=30.0
        )
        print(f"Response 1: {response1.content[:200]}...")
        
        # Send second message
        print("\n3. Sending second message...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "I like Python programming",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=30.0
        )
        print(f"Response 2: {response2.content[:200]}...")
        
        # Now ask a question that requires context from buffer memory
        print("\n4. Asking question that requires buffer memory context...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "What is my favorite color?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=30.0
        )
        print(f"Response 3: {response3.content}")
        
        # Check if the system remembers
        response_lower = response3.content.lower()
        remembers_color = "blue" in response_lower
        
        print("\n" + "="*50)
        print("DIAGNOSTIC RESULTS:")
        print("="*50)
        
        if remembers_color:
            print("✅ Buffer memory IS being included - system remembers 'blue'")
        else:
            print("❌ Buffer memory NOT being included - system doesn't remember 'blue'")
            print("   This explains why 8D1 and 8D2 tests are failing!")
        
        # Additional diagnostic: Check if we can see the previous programming statement
        print("\n5. Checking if programming preference is remembered...")
        response4 = await asyncio.wait_for(
            overlord.chat(
                "What programming language did I mention?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=30.0
        )
        print(f"Response 4: {response4.content}")
        
        remembers_python = "python" in response4.content.lower()
        
        if remembers_python:
            print("✅ Programming preference remembered")
        else:
            print("❌ Programming preference NOT remembered")
        
        # Now let's try to check the overlord's internal state if possible
        print("\n6. Checking overlord internal state...")
        
        # Check if there's a method to get buffer memory contents
        if hasattr(overlord, 'buffer_memory'):
            if hasattr(overlord.buffer_memory, 'get_messages'):
                messages = await overlord.buffer_memory.get_messages(
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    limit=10
                )
                print(f"   Buffer contains {len(messages)} messages")
                for i, msg in enumerate(messages):
                    print(f"   Message {i}: {str(msg)[:100]}...")
            else:
                print("   No get_messages method available")
        
        # Check if enhanced message includes context
        print("\n7. Testing message enhancement...")
        # This would require access to internal methods, but let's see what we can find
        
        if hasattr(overlord, '_enhance_message'):
            enhanced = await overlord._enhance_message(
                "Test message",
                ctx.user_id,
                ctx.session_id
            )
            print(f"   Enhanced message preview: {str(enhanced)[:500]}...")
            
            # Check if it contains previous context
            if "blue" in str(enhanced) or "python" in str(enhanced).lower():
                print("   ✅ Enhanced message DOES contain buffer context")
            else:
                print("   ❌ Enhanced message does NOT contain buffer context")
        else:
            print("   Cannot access _enhance_message method")
        
        print("\n" + "="*50)
        print("CONCLUSION:")
        print("="*50)
        
        if not remembers_color and not remembers_python:
            print("Buffer memory context is NOT being included in requests.")
            print("This is why clarification tests 8D1 and 8D2 are failing.")
            print("\nThe issue is likely in one of these areas:")
            print("1. Message enhancement not pulling from buffer memory")
            print("2. Buffer memory not being queried for context")
            print("3. Context not being passed to the LLM in the request")
            print("\nPer docs/request-lifecycle.md lines 376-417:")
            print("- Buffer should provide recent_messages")
            print("- These should be merged into full_context")
            print("- Context should be included in message formatting")
        else:
            print("Buffer memory context IS being included correctly.")
        
        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return remembers_color
        
    except Exception as e:
        print(f"\n❌ Debug test error: {e}")
        import traceback
        traceback.print_exc()
        
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":
    success = asyncio.run(test_buffer_memory_inclusion())
    sys.exit(0 if success else 1)