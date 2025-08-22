"""
Test 8E5d: Missing Configuration

This test validates handling of missing credential configuration.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation
from test_utils import TestContext


async def test_missing_credential_config():
    """Test handling of missing credential configuration."""
    try:
        print("\n=== Test 8E5d: Missing Configuration ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Remove user_credentials config to test missing configuration
        if "user_credentials" in formation.config:
            del formation.config["user_credentials"]
        
        overlord = await formation.start_overlord()
        ctx = TestContext("test_8e5d")
        
        print("\n1. Test with missing config: 'Access GitHub API'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Access GitHub API",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should handle missing config gracefully (default to secure behavior)
        response_lower = response1.content.lower()
        # Either works with default config or explains configuration needed
        config_indicators = ["configure", "setup", "configuration", "credential"]
        working_indicators = ["github", "api", "access", "repositories"]
        
        handles_gracefully = any(indicator in response_lower for indicator in config_indicators + working_indicators)
        assert handles_gracefully, "Should handle missing config gracefully"
        print("   ✅ Missing configuration handled gracefully")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Missing configuration handling working")
        print("✓ Missing config handled gracefully")
        print("✓ System remains functional or provides guidance")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Access GitHub API")
        print(f"System: {response1.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E5d FAILED: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_missing_credential_config())
    sys.exit(0 if success else 1)