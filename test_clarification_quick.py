"""Quick test to see if clarification is working."""

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
        
        # Check if clarification components are initialized
        print(f"Has information_analyzer: {hasattr(overlord, 'information_analyzer')}")
        if hasattr(overlord, 'information_analyzer'):
            print(f"information_analyzer is None: {overlord.information_analyzer is None}")
        print(f"Has clarification_config: {hasattr(overlord, 'clarification_config')}")
        if hasattr(overlord, 'clarification_config'):
            print(f"clarification_config: {overlord.clarification_config}")
        print(f"Has _pending_clarifications: {hasattr(overlord, '_pending_clarifications')}")
        if hasattr(overlord, '_pending_clarifications'):
            print(f"_pending_clarifications: {overlord._pending_clarifications}")
        
        if overlord.information_analyzer:
            print("✅ Clarification system initialized!")
        else:
            print("❌ Clarification system NOT initialized")
            
        print("\nTesting ambiguous message...")
        response = await overlord.chat(
            message="I need help with a scraper",
            user_id="test_user",
            session_id="test_session",
            stream=False
        )
        
        print(f"\nResponse type: {type(response)}")
        print(f"Response content preview: {str(response.content)[:200]}...")
        
        # Check if it's asking for clarification
        if "clarif" in str(response.content).lower() or "what" in str(response.content).lower():
            print("✅ Clarification detected!")
        else:
            print("❌ No clarification - went straight to answer")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())