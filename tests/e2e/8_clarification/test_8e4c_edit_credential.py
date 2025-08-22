"""
Test 8E4c: Edit Credential Not Supported

This test validates that credential editing is not supported for security.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation
from test_utils import TestContext


async def test_edit_credential_not_supported():
    """Test that credential editing is not supported."""
    try:
        print("\n=== Test 8E4c: Edit Credential Not Supported ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e4c")
        
        print("\n1. Testing credential edit: 'Update my GitHub token'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Update my GitHub token",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should indicate editing not supported or redirect to removal/re-add
        response_lower = response1.content.lower()
        not_supported_indicators = ["not supported", "cannot edit", "remove", "add new", "replace"]
        assert any(indicator in response_lower for indicator in not_supported_indicators), \
            "Should indicate editing not supported or suggest alternative"
        print("   ✅ Credential editing handled appropriately")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Edit credential restriction working")
        print("✓ Credential editing appropriately restricted")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Update my GitHub token")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E4c FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_edit_credential_not_supported())
    sys.exit(0 if success else 1)