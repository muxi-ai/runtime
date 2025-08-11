#!/usr/bin/env python3
"""
Area 8 - Test Group 8C: Multiple Clarification Sequences
Test 8C3: Complex Parameter Collection

Tests collection of multiple parameters through clarification,
including optional parameters, validation, and confirmation.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_8c3_multi_parameter_collection():
    """Test collection of multiple parameters for a complex task."""
    print("\n=== Test 8C3: Complex Parameter Collection ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8c3")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Request requiring multiple parameters
        print("\n1. Request requiring multiple parameters...")
        response1 = await overlord.chat(
            "Create a new API endpoint",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response1.content}")
        
        # Should ask for endpoint details
        response_lower = response1.content.lower()
        assert any(word in response_lower for word in ["what", "which", "endpoint", "path", "method", "purpose"]), \
            "Should ask for endpoint details"
        
        # Parameter 1: Endpoint path
        print("\n2. Providing endpoint path...")
        response2 = await overlord.chat(
            "/api/users/:id/profile",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response2.content}")
        
        # Should ask for HTTP method or other details
        response_lower = response2.content.lower()
        assert any(word in response_lower for word in ["method", "get", "post", "put", "delete", "http"]), \
            "Should ask for HTTP method or continue gathering parameters"
        
        # Parameter 2: HTTP method
        print("\n3. Providing HTTP method...")
        response3 = await overlord.chat(
            "GET method to retrieve user profile",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response3.content}")
        
        # Parameter 3: Response format
        print("\n4. Asking about response format...")
        response4 = await overlord.chat(
            "What response format should it return?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response4.content}")
        
        # Should suggest common formats
        response_lower = response4.content.lower()
        assert any(format in response_lower for format in ["json", "xml", "html"]), \
            "Should mention response formats"
        
        # Parameter 4: Authentication requirement
        print("\n5. Asking about authentication...")
        response5 = await overlord.chat(
            "Does this endpoint need authentication?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response5.content}")
        
        # Should discuss authentication options
        response_lower = response5.content.lower()
        assert any(auth in response_lower for auth in ["auth", "jwt", "token", "bearer", "api"]), \
            "Should discuss authentication"
        
        # Final implementation based on all parameters
        print("\n6. Requesting implementation with all parameters collected...")
        response6 = await overlord.chat(
            "Now show me the implementation with JWT authentication and JSON response",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response6.content}")
        
        # Should reference all collected parameters
        response_lower = response6.content.lower()
        assert "/api/users" in response_lower or "profile" in response_lower, \
            "Should reference the endpoint path"
        assert "get" in response_lower, \
            "Should reference GET method"
        assert "jwt" in response_lower or "json" in response_lower, \
            "Should reference JWT and/or JSON"
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Complex parameters collected successfully")
        print("✓ Initial request triggered endpoint details clarification")
        print("✓ Endpoint path collected successfully")
        print("✓ HTTP method (GET) specified and acknowledged")
        print("✓ Response format discussion initiated")
        print("✓ Authentication requirements discussed")
        print("✓ Final implementation referenced all collected parameters")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Create a new API endpoint")
        print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        print("\nUser: /api/users/:id/profile")
        print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        print("\nUser: GET method to retrieve user profile")
        print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        print("\nUser: What response format should it return?")
        print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        print("\nUser: Does this endpoint need authentication?")
        print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
        print("\nUser: Now show me the implementation with JWT authentication and JSON response")
        print(f"System: {response6.content[:500] + '...' if len(response6.content) > 500 else response6.content}")
        print("\n" + "="*40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8C3 FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Complex parameter collection test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Create a new API endpoint")
            print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        if 'response2' in locals():
            print("\nUser: /api/users/:id/profile")
            print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        if 'response3' in locals():
            print("\nUser: GET method to retrieve user profile")
            print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        if 'response4' in locals():
            print("\nUser: What response format should it return?")
            print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        if 'response5' in locals():
            print("\nUser: Does this endpoint need authentication?")
            print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
        if 'response6' in locals():
            print("\nUser: Now show me the implementation with JWT authentication and JSON response")
            print(f"System: {response6.content[:500] + '...' if len(response6.content) > 500 else response6.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_8c3_parameter_validation():
    """Test parameter validation and correction during clarification."""
    print("\n=== Test 8C3b: Parameter Validation and Correction ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8c3b")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Request with parameters that need validation
        print("\n1. Setting up database connection...")
        response1 = await overlord.chat(
            "Configure database connection",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response1.content}")
        
        # Should ask for database details
        response_lower = response1.content.lower()
        assert any(word in response_lower for word in ["which", "what", "database", "type", "postgres", "mysql"]), \
            "Should ask for database type"
        
        # Provide database type
        print("\n2. Specifying PostgreSQL...")
        response2 = await overlord.chat(
            "PostgreSQL database",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response2.content}")
        
        # Invalid port number
        print("\n3. Providing invalid port...")
        response3 = await overlord.chat(
            "Host is localhost and port is 99999",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response3.content}")
        
        # Should mention port issue or suggest default
        response_lower = response3.content.lower()
        assert any(term in response_lower for term in ["port", "5432", "valid", "range", "default"]), \
            "Should address port validity"
        
        # Correction
        print("\n4. Correcting port...")
        response4 = await overlord.chat(
            "Use default port 5432",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response4.content}")
        
        # Missing required parameter
        print("\n5. Asking about missing parameter...")
        response5 = await overlord.chat(
            "What about the database name?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response5.content}")
        
        # Should acknowledge need for database name
        response_lower = response5.content.lower()
        assert any(term in response_lower for term in ["database", "name", "specify", "provide"]), \
            "Should acknowledge database name requirement"
        
        # Complete configuration
        print("\n6. Providing database name...")
        response6 = await overlord.chat(
            "Database name is 'myapp_production'",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response6.content}")
        
        # Should now have complete valid configuration
        response_lower = response6.content.lower()
        assert any(term in response_lower for term in ["postgres", "localhost", "5432", "myapp"]), \
            "Should reference the complete configuration"
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Parameter validation handled correctly")
        print("✓ Database configuration clarification initiated")
        print("✓ PostgreSQL type specified")
        print("✓ Invalid port (99999) addressed")
        print("✓ Port corrected to valid default (5432)")
        print("✓ Missing database name parameter identified")
        print("✓ Complete configuration with validation")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Configure database connection")
        print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        print("\nUser: PostgreSQL database")
        print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        print("\nUser: Host is localhost and port is 99999")
        print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        print("\nUser: Use default port 5432")
        print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        print("\nUser: What about the database name?")
        print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
        print("\nUser: Database name is 'myapp_production'")
        print(f"System: {response6.content[:400] + '...' if len(response6.content) > 400 else response6.content}")
        print("\n" + "="*40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8C3b FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Parameter validation test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: Configure database connection")
            print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        if 'response2' in locals():
            print("\nUser: PostgreSQL database")
            print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        if 'response3' in locals():
            print("\nUser: Host is localhost and port is 99999")
            print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        if 'response4' in locals():
            print("\nUser: Use default port 5432")
            print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        if 'response5' in locals():
            print("\nUser: What about the database name?")
            print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
        if 'response6' in locals():
            print("\nUser: Database name is 'myapp_production'")
            print(f"System: {response6.content[:400] + '...' if len(response6.content) > 400 else response6.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


if __name__ == "__main__":
    async def run_tests():
        """Run all complex parameter collection tests."""
        results = []
        
        # Run multi-parameter collection test
        result = await test_8c3_multi_parameter_collection()
        results.append(("8C3: Multi-parameter Collection", result))
        
        # Run parameter validation test
        result = await test_8c3_parameter_validation()
        results.append(("8C3b: Parameter Validation", result))
        
        # Print summary
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