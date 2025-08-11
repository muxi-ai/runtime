#!/usr/bin/env python3
"""
Area 8 - Test Group 8B: Information Flow
Test 8B1: Context Propagation

Tests that context from previous messages is properly maintained
and used in subsequent interactions.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_8b1_context_propagation():
    """Test that context propagates across conversation turns."""
    print("\n=== Test 8B1: Context Propagation ===")
    
    # Load formation with clarification capabilities
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8b1")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Test 1: Establish context
        print("\n1. Establishing e-commerce platform context...")
        response = await overlord.chat(
            "I'm working on an e-commerce platform using React and Node.js",
            user_id=ctx.user_id
        )
        print(f"Response: {response}")
        assert response is not None
        
        # Test 2: Ask question that should use context
        print("\n2. Asking database recommendation (should consider e-commerce context)...")
        response = await overlord.chat(
            "What database should I use?",
            user_id=ctx.user_id
        )
        print(f"Response: {response}")
        
        # Should recommend databases suitable for e-commerce
        response_lower = response.lower()
        assert any(db in response_lower for db in ["postgres", "postgresql", "mysql", "mongo", "dynamodb"]), \
            "Should recommend appropriate databases for e-commerce"
        
        # Should reference e-commerce context
        assert any(term in response_lower for term in ["e-commerce", "ecommerce", "product", "order", "transaction"]), \
            "Should reference e-commerce context in recommendation"
        
        # Test 3: Further context refinement
        print("\n3. Adding scalability requirement...")
        response = await overlord.chat(
            "I expect high traffic during sales events with millions of users",
            user_id=ctx.user_id
        )
        print(f"Response: {response}")
        
        # Test 4: Question that should consider all context
        print("\n4. Asking about caching strategy (should consider React, Node.js, high traffic)...")
        response = await overlord.chat(
            "What caching strategy would you recommend?",
            user_id=ctx.user_id
        )
        print(f"Response: {response}")
        
        # Should mention relevant caching solutions
        response_lower = response.lower()
        assert any(cache in response_lower for cache in ["redis", "memcached", "cdn", "cloudflare", "cache"]), \
            "Should recommend caching solutions"
        
        # Should reference high traffic/scalability
        assert any(term in response_lower for term in ["traffic", "scale", "performance", "load"]), \
            "Should reference scalability requirements"
        
        print("\n✅ Test 8B1 PASSED: Context properly propagates across conversation")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8B1 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8B1 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


async def test_8b1_context_isolation():
    """Test that context is properly isolated between users."""
    print("\n=== Test 8B1b: Context Isolation Between Users ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test contexts for two different users
    ctx1 = TestContext("test_8b1_user1")
    ctx2 = TestContext("test_8b1_user2")
    print(f"User1: {ctx1.user_id}, User2: {ctx2.user_id}")
    
    try:
        # User 1: Python context
        print("\n1. User1: Establishing Python ML context...")
        response = await overlord.chat(
            "I'm building a machine learning model in Python using scikit-learn",
            user_id=ctx1.user_id
        )
        print(f"User1 Response: {response}")
        
        # User 2: Java context
        print("\n2. User2: Establishing Java microservices context...")
        response = await overlord.chat(
            "I'm developing microservices in Java with Spring Boot",
            user_id=ctx2.user_id
        )
        print(f"User2 Response: {response}")
        
        # User 1: Question should use Python/ML context
        print("\n3. User1: Asking about data preprocessing...")
        response = await overlord.chat(
            "What libraries should I use for data preprocessing?",
            user_id=ctx1.user_id
        )
        print(f"User1 Response: {response}")
        
        response_lower = response.lower()
        assert any(lib in response_lower for lib in ["pandas", "numpy", "scikit", "sklearn"]), \
            "User1 should get Python/ML library recommendations"
        assert "spring" not in response_lower and "java" not in response_lower, \
            "User1 should not get Java recommendations"
        
        # User 2: Question should use Java/microservices context
        print("\n4. User2: Asking about service communication...")
        response = await overlord.chat(
            "What's the best way to handle service-to-service communication?",
            user_id=ctx2.user_id
        )
        print(f"User2 Response: {response}")
        
        response_lower = response.lower()
        assert any(term in response_lower for term in ["rest", "grpc", "kafka", "rabbitmq", "feign"]), \
            "User2 should get microservices communication recommendations"
        assert "pandas" not in response_lower and "numpy" not in response_lower, \
            "User2 should not get Python/ML recommendations"
        
        print("\n✅ Test 8B1b PASSED: Context properly isolated between users")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8B1b FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8B1b ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


if __name__ == "__main__":
    async def run_tests():
        """Run all context propagation tests."""
        results = []
        
        # Run basic context propagation test
        result = await test_8b1_context_propagation()
        results.append(("8B1: Context Propagation", result))
        
        # Run context isolation test
        result = await test_8b1_context_isolation()
        results.append(("8B1b: Context Isolation", result))
        
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