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

from muxi.formation import Formation


async def test_8c3_multi_parameter_collection():
    """Test collection of multiple parameters for a complex task."""
    print("\n=== Test 8C3: Complex Parameter Collection ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Request requiring multiple parameters
        print("\n1. Request requiring multiple parameters...")
        response = await overlord.chat(
            "Create a new API endpoint",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask for endpoint details
        response_lower = response.lower()
        assert any(word in response_lower for word in ["what", "which", "endpoint", "path", "method", "purpose"]), \
            "Should ask for endpoint details"
        
        # Parameter 1: Endpoint path
        print("\n2. Providing endpoint path...")
        response = await overlord.chat(
            "/api/users/:id/profile",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask for HTTP method or other details
        response_lower = response.lower()
        assert any(word in response_lower for word in ["method", "get", "post", "put", "delete", "http"]), \
            "Should ask for HTTP method or continue gathering parameters"
        
        # Parameter 2: HTTP method
        print("\n3. Providing HTTP method...")
        response = await overlord.chat(
            "GET method to retrieve user profile",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Parameter 3: Response format
        print("\n4. Asking about response format...")
        response = await overlord.chat(
            "What response format should it return?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should suggest common formats
        response_lower = response.lower()
        assert any(format in response_lower for format in ["json", "xml", "html"]), \
            "Should mention response formats"
        
        # Parameter 4: Authentication requirement
        print("\n5. Asking about authentication...")
        response = await overlord.chat(
            "Does this endpoint need authentication?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should discuss authentication options
        response_lower = response.lower()
        assert any(auth in response_lower for auth in ["auth", "jwt", "token", "bearer", "api"]), \
            "Should discuss authentication"
        
        # Final implementation based on all parameters
        print("\n6. Requesting implementation with all parameters collected...")
        response = await overlord.chat(
            "Now show me the implementation with JWT authentication and JSON response",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should reference all collected parameters
        response_lower = response.lower()
        assert "/api/users" in response_lower or "profile" in response_lower, \
            "Should reference the endpoint path"
        assert "get" in response_lower, \
            "Should reference GET method"
        assert "jwt" in response_lower or "json" in response_lower, \
            "Should reference JWT and/or JSON"
        
        print("\n✅ Test 8C3 PASSED: Complex parameters collected successfully")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8C3 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8C3 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


async def test_8c3_parameter_validation():
    """Test parameter validation and correction during clarification."""
    print("\n=== Test 8C3b: Parameter Validation and Correction ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Request with parameters that need validation
        print("\n1. Setting up database connection...")
        response = await overlord.chat(
            "Configure database connection",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask for database details
        response_lower = response.lower()
        assert any(word in response_lower for word in ["which", "what", "database", "type", "postgres", "mysql"]), \
            "Should ask for database type"
        
        # Provide database type
        print("\n2. Specifying PostgreSQL...")
        response = await overlord.chat(
            "PostgreSQL database",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Invalid port number
        print("\n3. Providing invalid port...")
        response = await overlord.chat(
            "Host is localhost and port is 99999",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should mention port issue or suggest default
        response_lower = response.lower()
        assert any(term in response_lower for term in ["port", "5432", "valid", "range", "default"]), \
            "Should address port validity"
        
        # Correction
        print("\n4. Correcting port...")
        response = await overlord.chat(
            "Use default port 5432",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Missing required parameter
        print("\n5. Asking about missing parameter...")
        response = await overlord.chat(
            "What about the database name?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should acknowledge need for database name
        response_lower = response.lower()
        assert any(term in response_lower for term in ["database", "name", "specify", "provide"]), \
            "Should acknowledge database name requirement"
        
        # Complete configuration
        print("\n6. Providing database name...")
        response = await overlord.chat(
            "Database name is 'myapp_production'",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should now have complete valid configuration
        response_lower = response.lower()
        assert any(term in response_lower for term in ["postgres", "localhost", "5432", "myapp"]), \
            "Should reference the complete configuration"
        
        print("\n✅ Test 8C3b PASSED: Parameter validation handled correctly")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8C3b FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8C3b ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


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
    
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)