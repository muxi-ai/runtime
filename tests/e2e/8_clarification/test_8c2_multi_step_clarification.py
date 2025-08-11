#!/usr/bin/env python3
"""
Area 8 - Test Group 8C: Multiple Clarification Sequences
Test 8C2: Multi-step Clarification

Tests handling of multiple clarification steps where each clarification
may lead to additional clarifications.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation


async def test_8c2_nested_clarifications():
    """Test nested clarification sequences."""
    print("\n=== Test 8C2: Multi-step Clarification ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Step 1: Initial ambiguous request
        print("\n1. Initial ambiguous request...")
        response = await overlord.chat(
            "Set up the integration",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask what kind of integration
        response_lower = response.lower()
        assert any(word in response_lower for word in ["what", "which", "integration", "service", "system", "clarify"]), \
            "Should ask for clarification about integration type"
        
        # Step 2: Provide partial clarification (still ambiguous)
        print("\n2. Partial clarification (payment integration)...")
        response = await overlord.chat(
            "Payment integration",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask which payment provider
        response_lower = response.lower()
        assert any(word in response_lower for word in ["which", "what", "provider", "stripe", "paypal", "square"]), \
            "Should ask for clarification about payment provider"
        
        # Step 3: Another clarification needed
        print("\n3. Specifying payment provider...")
        response = await overlord.chat(
            "Stripe",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Might ask about environment or implementation details
        response_lower = response.lower()
        # Should now have enough context to provide guidance
        assert any(term in response_lower for term in ["stripe", "api", "key", "webhook", "checkout", "payment"]), \
            "Should provide Stripe-specific guidance"
        
        # Step 4: Follow-up question using full context
        print("\n4. Follow-up with all context available...")
        response = await overlord.chat(
            "What test cards should I use?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should provide Stripe test card information
        response_lower = response.lower()
        assert any(term in response_lower for term in ["4242", "test", "card", "stripe"]), \
            "Should provide Stripe test card information"
        
        print("\n✅ Test 8C2 PASSED: Multi-step clarification handled correctly")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8C2 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8C2 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


async def test_8c2_branching_clarifications():
    """Test clarification that branches into multiple paths."""
    print("\n=== Test 8C2b: Branching Clarification Paths ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Initial request with multiple ambiguities
        print("\n1. Request with multiple ambiguities...")
        response = await overlord.chat(
            "Deploy the application",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask about deployment target
        response_lower = response.lower()
        assert any(word in response_lower for word in ["where", "which", "platform", "aws", "cloud", "environment"]), \
            "Should ask about deployment target"
        
        # Branch 1: Specify cloud provider
        print("\n2. Branch 1: Specifying AWS...")
        response = await overlord.chat(
            "Deploy to AWS",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask about AWS service or application type
        response_lower = response.lower()
        assert any(term in response_lower for term in ["ec2", "ecs", "lambda", "elastic", "service", "which"]), \
            "Should ask about AWS service or need more details"
        
        # Branch 2: Specify application type
        print("\n3. Branch 2: Specifying containerized app...")
        response = await overlord.chat(
            "It's a containerized Node.js application",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should now provide specific deployment guidance
        response_lower = response.lower()
        assert any(term in response_lower for term in ["ecs", "eks", "fargate", "docker", "container"]), \
            "Should suggest container services for AWS"
        
        # Final clarification based on both branches
        print("\n4. Question using both clarifications...")
        response = await overlord.chat(
            "Should I use ECS or EKS?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should compare ECS vs EKS for Node.js containers
        response_lower = response.lower()
        assert "ecs" in response_lower and "eks" in response_lower, \
            "Should compare both ECS and EKS"
        assert any(term in response_lower for term in ["node", "container", "docker"]), \
            "Should maintain Node.js container context"
        
        print("\n✅ Test 8C2b PASSED: Branching clarifications handled correctly")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8C2b FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8C2b ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


if __name__ == "__main__":
    async def run_tests():
        """Run all multi-step clarification tests."""
        results = []
        
        # Run nested clarifications test
        result = await test_8c2_nested_clarifications()
        results.append(("8C2: Nested Clarifications", result))
        
        # Run branching clarifications test
        result = await test_8c2_branching_clarifications()
        results.append(("8C2b: Branching Clarifications", result))
        
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