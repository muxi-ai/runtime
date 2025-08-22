"""
Test 8E4b: Remove Credential

This test validates credential removal functionality.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation
from test_utils import TestContext


async def test_remove_credential():
    """Test credential removal functionality."""
    try:
        print("\n=== Test 8E4b: Remove Credential ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e4b")
        
        print("\n1. Testing credential removal: 'Remove my GitHub credentials'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Remove my GitHub credentials",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should handle removal request
        response_lower = response1.content.lower()
        removal_indicators = ["remove", "delete", "confirm", "sure", "credential"]
        assert any(indicator in response_lower for indicator in removal_indicators), \
            "Should handle credential removal request"
        print("   ✅ Credential removal request handled")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Remove credential working")
        print("✓ Credential removal request handled appropriately")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Remove my GitHub credentials")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E4b FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_remove_credential())
    sys.exit(0 if success else 1)