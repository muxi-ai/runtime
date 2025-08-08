"""
Simple test to verify clarification system.
"""

import asyncio
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.muxi import Formation


async def test_simple_clarification():
    """Test if clarification works at all."""
    
    # Load formation with single agent
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-clarification"
    formation = Formation()
    await formation.load(str(formation_path))
    
    # Start overlord
    overlord = await formation.start_overlord()
    
    # Send ambiguous request
    print("\n🔍 Testing: 'I need help with a scraper'")
    response = await overlord.chat(
        message="I need help with a scraper",
        user_id="test_user",
        session_id="test_session",
        stream=False
    )
    
    print(f"📝 Response: {response.content[:200]}...")
    
    # Check if it asks for clarification
    response_lower = response.content.lower()
    has_clarification = any(word in response_lower for word in [
        "what", "which", "clarify", "specific", "tell me more", "kind of"
    ])
    
    if has_clarification:
        print("✅ Clarification detected!")
    else:
        print("❌ No clarification - went straight to answer")
    
    return has_clarification


if __name__ == "__main__":
    result = asyncio.run(test_simple_clarification())
    if result:
        print("\n✅ Clarification system is working")
    else:
        print("\n❌ Clarification system is NOT working in sync mode")