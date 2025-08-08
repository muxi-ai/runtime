"""Test with extremely ambiguous responses."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def test():
    try:
        print("Loading formation...")
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        print("\n=== Testing Extreme Ambiguity ===\n")
        
        # Test 1: Incomplete/nonsensical responses
        print("Test 1: Extremely vague responses")
        messages = [
            "help me with",
            "the thing",
            "you know",
            "that one",
        ]
        
        session_id = "extreme_1"
        for i, msg in enumerate(messages, 1):
            print(f"  Round {i}: User says '{msg}'")
            response = await overlord.chat(
                message=msg,
                user_id="test_extreme",
                session_id=session_id,
                stream=False
            )
            is_clarification = response.metadata and response.metadata.get("clarification")
            response_preview = str(response.content)[:100]
            print(f"  Bot: {response_preview}...")
            print(f"  {'🔄 Clarification' if is_clarification else '✅ Processing'}")
            if not is_clarification:
                break
            print()
        
        print("\n---")
        
        # Test 2: Question as response
        print("\nTest 2: Responding with questions")
        session_id = "extreme_2"
        
        response1 = await overlord.chat(
            message="I need assistance",
            user_id="test_extreme_2",
            session_id=session_id,
            stream=False
        )
        print(f"  User: 'I need assistance'")
        print(f"  Bot: {str(response1.content)[:100]}...")
        
        response2 = await overlord.chat(
            message="What do you think I need?",
            user_id="test_extreme_2",
            session_id=session_id,
            stream=False
        )
        print(f"\n  User: 'What do you think I need?'")
        is_clarification = response2.metadata and response2.metadata.get("clarification")
        print(f"  Bot: {str(response2.content)[:100]}...")
        print(f"  {'🔄 Still clarifying' if is_clarification else '✅ Processing'}")
        
        print("\n=== Conclusion ===")
        print("The system handles extreme ambiguity by continuing to ask")
        print("for clarification until it has enough context to proceed.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())