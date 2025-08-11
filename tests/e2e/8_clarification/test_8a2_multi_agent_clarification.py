"""Test 8A2: Multi-agent Clarification

Tests clarification when multiple agents could handle the request.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation


async def test_multi_agent_clarification():
    """Test clarification in multi-agent scenarios."""
    try:
        print("\n=== Test 8A2: Multi-agent Clarification ===\n")
        
        # Load multi-agent formation
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Test: Ambiguous help request
        print("\n1. Testing with: 'I need help with the bug'")
        response = await overlord.chat(
            message="I need help with the bug",
            user_id="test_user",
            session_id="multi_agent_session",
            stream=False
        )
        
        print(f"   Response: {response.content}")
        
        # Should ask what kind of bug (code, process, etc.)
        is_clarification = response.metadata and response.metadata.get("clarification")
        assert is_clarification, "Should ask for clarification about bug type"
        print("   ✅ Multi-agent clarification triggered")
        
        # Provide clarification
        print("\n2. Clarifying: 'A Python syntax error in my code'")
        response2 = await overlord.chat(
            message="A Python syntax error in my code",
            user_id="test_user",
            session_id="multi_agent_session",
            stream=False
        )
        
        print(f"   Response: {response2.content[:200]}...")
        
        # Should now route to appropriate agent
        is_clarification2 = response2.metadata and response2.metadata.get("clarification")
        assert not is_clarification2, "Should process after clarification"
        assert "python" in response2.content.lower() or "syntax" in response2.content.lower(), \
            "Should help with Python syntax"
        print("   ✅ Routed to appropriate agent after clarification")
        
        print("\n✅ Test 8A2 PASSED: Multi-agent clarification working")
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8A2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        sys.exit(0 if "return True" in locals() else 1)


if __name__ == "__main__":
    asyncio.run(test_multi_agent_clarification())