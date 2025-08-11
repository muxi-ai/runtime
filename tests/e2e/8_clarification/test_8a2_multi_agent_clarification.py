"""Test 8A2: Multi-agent Clarification

Tests clarification when multiple agents could handle the request.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation
from test_utils import TestContext


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
        
        # Create unique test context
        ctx = TestContext("test_8a2")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Test: Ambiguous help request
        print("\n1. Testing with: 'I need help with the bug'")
        response = await overlord.chat(
            message="I need help with the bug",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
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
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        print(f"   Response: {response2.content[:200]}...")
        
        # Should now route to appropriate agent
        is_clarification2 = response2.metadata and response2.metadata.get("clarification")
        assert not is_clarification2, "Should process after clarification"
        assert "python" in response2.content.lower() or "syntax" in response2.content.lower(), \
            "Should help with Python syntax"
        print("   ✅ Routed to appropriate agent after clarification")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Multi-agent clarification working")
        print("✓ Ambiguous bug request triggered clarification")
        print("✓ System asked for clarification about bug type")
        print("✓ Clarification response processed correctly")
        print("✓ Request routed to appropriate agent after clarification")
        print("\n" + "="*40)
        
        print("\n### Chat transcript:")
        print("\nUser: I need help with the bug")
        print(f"System: {response.content}")
        print("\nUser: A Python syntax error in my code")
        print(f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")
        
        print("\n" + "="*40)
        
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8A2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Multi-agent clarification test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)
        
        print("\n### Partial Chat transcript (before failure):")
        if 'response' in locals():
            print("\nUser: I need help with the bug")
            print(f"System: {response.content}")
        if 'response2' in locals():
            print("\nUser: A Python syntax error in my code")
            print(f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")
        
        print("\n" + "="*40)
        
        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        
        return False
    finally:
        sys.exit(0 if "return True" in locals() else 1)


if __name__ == "__main__":
    asyncio.run(test_multi_agent_clarification())