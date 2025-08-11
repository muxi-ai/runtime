"""Test 8A1: Ambiguous Request Clarification

Tests basic clarification when a request is too vague or ambiguous.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation


async def test_ambiguous_request():
    """Test clarification for ambiguous requests."""
    try:
        print("\n=== Test 8A1: Ambiguous Request ===\n")
        
        # Load formation with clarification enabled
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Test 1: Very ambiguous request
        print("\n1. Testing with: 'Build it'")
        response = await overlord.chat(
            message="Build it",
            user_id="test_user",
            session_id="test_session_1",
            stream=False
        )
        
        print(f"   Response: {response.content}")
        
        # Should ask for clarification
        is_clarification = response.metadata and response.metadata.get("clarification")
        assert is_clarification, "Should ask for clarification on ambiguous request"
        assert any(word in response.content.lower() for word in ["what", "clarify", "specific", "build"]), \
            "Response should ask what to build"
        print("   ✅ Clarification triggered correctly")
        
        # Follow-up with clarification
        print("\n2. Providing clarification: 'A Python web scraper'")
        response2 = await overlord.chat(
            message="A Python web scraper",
            user_id="test_user",
            session_id="test_session_1",
            stream=False
        )
        
        print(f"   Response: {response2.content[:200]}...")
        
        # Should now provide specific help
        is_clarification2 = response2.metadata and response2.metadata.get("clarification")
        assert not is_clarification2, "Should not ask for clarification after receiving specific info"
        assert "python" in response2.content.lower() or "scraper" in response2.content.lower(), \
            "Should provide help with Python web scraper"
        print("   ✅ Processed request after clarification")
        
        # Test 2: Another ambiguous request
        print("\n3. Testing with: 'Fix the bug'")
        response3 = await overlord.chat(
            message="Fix the bug",
            user_id="test_user",
            session_id="test_session_2",
            stream=False
        )
        
        print(f"   Response: {response3.content}")
        
        is_clarification3 = response3.metadata and response3.metadata.get("clarification")
        assert is_clarification3, "Should ask for clarification about which bug"
        assert any(word in response3.content.lower() for word in ["which", "bug", "what", "describe"]), \
            "Should ask about the bug details"
        print("   ✅ Clarification triggered for bug request")
        
        print("\n✅ Test 8A1 PASSED: Ambiguous request clarification working")
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8A1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        sys.exit(0 if "return True" in locals() else 1)


if __name__ == "__main__":
    asyncio.run(test_ambiguous_request())