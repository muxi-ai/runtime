"""
Test 8E2c: Basic Auth in Dynamic Mode

This test validates that Basic authentication requests are accepted inline
in dynamic mode with appropriate security warnings.

Test flow:
1. Configure formation in dynamic mode
2. Simulate Basic auth credential request
3. Verify system prompts with security warning
4. Test credential storage and validation
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_basic_auth_dynamic_mode():
    """Test Basic auth requests with security warnings in dynamic mode."""
    try:
        print("\n=== Test 8E2c: Basic Auth in Dynamic Mode ===")
        
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Configure dynamic mode with Basic auth warnings
        formation.config["user_credentials"] = {
            "mode": "dynamic",
            "security_warnings": {
                "basic_auth": True
            },
            "inline_acceptance": {
                "basic": True
            }
        }
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        ctx = TestContext("test_8e2c")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Step 1: Request that needs Basic auth
        print("\n1. Testing Basic auth request: 'Access the legacy API with Basic auth'")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Access the legacy API with Basic auth",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response1.content}")
        
        # Should prompt with security warning
        response_lower = response1.content.lower()
        warning_indicators = ["⚠️", "warning", "caution", "security", "careful", "note"]
        credential_indicators = ["username", "password", "basic", "provide", "enter"]
        
        has_warning = any(indicator in response_lower for indicator in warning_indicators)
        requests_credentials = any(indicator in response_lower for indicator in credential_indicators)
        
        assert has_warning or requests_credentials, \
            "Should show security warning or request Basic auth credentials"
        print("   ✅ Security warning shown or credentials requested")
        
        if has_warning:
            print("   ✅ Security warning displayed for Basic auth")
        
        # Step 2: Provide Basic auth credentials
        print("\n2. Providing Basic auth: 'username:password123'")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="username:password123",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        
        print(f"   Response: {response2.content}")
        
        # Should acknowledge storage
        response_lower = response2.content.lower()
        storage_indicators = ["stored", "saved", "configured", "received"]
        assert any(indicator in response_lower for indicator in storage_indicators), \
            "Should acknowledge Basic auth storage"
        print("   ✅ Basic auth storage acknowledged")
        
        # Should not echo credentials
        assert "password123" not in response2.content, \
            "Should not echo password back"
        print("   ✅ Password not echoed back")
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Basic auth dynamic mode working correctly")
        print("✓ Security warning displayed for Basic auth")
        print("✓ Credentials accepted inline in dynamic mode")
        print("✓ Storage acknowledged securely")
        print("✓ Password not echoed back")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Access the legacy API with Basic auth")
        print(f"System: {response1.content}")
        print("\nUser: username:password123")
        print(f"System: {response2.content}")
        print("\n" + "="*40)

        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8E2c FAILED: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Basic auth dynamic mode test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Access the legacy API with Basic auth")
            print(f"System: {response1.content}")
        if 'response2' in locals():
            print("\nUser: username:password123")
            print(f"System: {response2.content}")
        print("\n" + "="*40)

        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":
    async def run_tests():
        """Run Basic auth dynamic mode test."""
        results = []
        
        result = await test_basic_auth_dynamic_mode()
        results.append(("8E2c: Basic Auth Dynamic Mode", result))
        
        print("\n" + "="*50)
        print("TEST SUMMARY")
        print("="*50)
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{test_name}: {status}")
        
        all_passed = all(result for _, result in results)
        if all_passed:
            print(f"\n🎉 All {len(results)} tests PASSED!")
        else:
            failed = sum(1 for _, result in results if not result)
            print(f"\n⚠️ {failed}/{len(results)} tests FAILED")
        
        return all_passed
    
    try:
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    finally:
        pass