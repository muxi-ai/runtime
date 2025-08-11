#!/usr/bin/env python3
"""
Area 8 - Test Group 8B: Information Flow
Test 8B2: Information Extraction

Tests that the system properly extracts and remembers key information
from user messages (budget, timeline, requirements, etc.).
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation


async def test_8b2_information_extraction():
    """Test extraction of key project information from conversation."""
    print("\n=== Test 8B2: Information Extraction ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Test 1: Extract budget and timeline
        print("\n1. Providing budget and timeline information...")
        response = await overlord.chat(
            "My budget is $5000 and timeline is 2 weeks for the MVP",
            user_id="test_user"
        )
        print(f"Response: {response}")
        assert response is not None
        
        # Test 2: Ask for recommendations that should consider budget/timeline
        print("\n2. Asking for tech stack recommendation...")
        response = await overlord.chat(
            "What tech stack would you recommend for a quick prototype?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        response_lower = response.lower()
        # Should mention quick/rapid/fast development given 2-week timeline
        assert any(term in response_lower for term in ["quick", "rapid", "fast", "mvp", "prototype", "week"]), \
            "Should reference the tight timeline"
        
        # Should suggest cost-effective solutions given $5000 budget
        assert any(term in response_lower for term in ["cost", "budget", "free", "open", "affordable"]), \
            "Should consider budget constraints"
        
        # Test 3: Extract technical requirements
        print("\n3. Providing technical requirements...")
        response = await overlord.chat(
            "The app needs user authentication, real-time chat, and payment processing",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Test 4: Ask specific question that should use extracted requirements
        print("\n4. Asking about authentication solution...")
        response = await overlord.chat(
            "Which authentication solution would work best?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        response_lower = response.lower()
        # Should mention auth solutions
        assert any(auth in response_lower for auth in ["auth0", "firebase", "supabase", "jwt", "oauth"]), \
            "Should recommend authentication solutions"
        
        # Should consider real-time and payment requirements
        assert any(term in response_lower for term in ["real-time", "realtime", "chat", "payment", "stripe"]), \
            "Should reference other requirements when making recommendations"
        
        print("\n✅ Test 8B2 PASSED: Information properly extracted and used")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8B2 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8B2 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


async def test_8b2_constraint_tracking():
    """Test tracking of multiple constraints and preferences."""
    print("\n=== Test 8B2b: Constraint Tracking ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Provide multiple constraints across messages
        print("\n1. Constraint 1: Team size...")
        response = await overlord.chat(
            "We're a small team of 3 developers",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        print("\n2. Constraint 2: Experience level...")
        response = await overlord.chat(
            "We're all junior developers with 1-2 years experience",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        print("\n3. Constraint 3: Deployment preference...")
        response = await overlord.chat(
            "We prefer to deploy on AWS",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        print("\n4. Constraint 4: Mobile requirement...")
        response = await overlord.chat(
            "The app needs to work well on mobile devices",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Ask for comprehensive recommendation
        print("\n5. Asking for architecture recommendation considering ALL constraints...")
        response = await overlord.chat(
            "Based on everything I've told you, what architecture would you recommend?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        response_lower = response.lower()
        
        # Should consider team size (small team)
        assert any(term in response_lower for term in ["small", "team", "three", "3", "simple", "manageable"]), \
            "Should consider small team size"
        
        # Should consider experience level (junior)
        assert any(term in response_lower for term in ["junior", "learn", "simple", "straightforward", "easy"]), \
            "Should consider junior experience level"
        
        # Should mention AWS
        assert "aws" in response_lower, "Should mention AWS deployment"
        
        # Should consider mobile requirement
        assert any(term in response_lower for term in ["mobile", "responsive", "react", "flutter", "native"]), \
            "Should consider mobile requirement"
        
        print("\n✅ Test 8B2b PASSED: Multiple constraints properly tracked")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8B2b FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8B2b ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


if __name__ == "__main__":
    async def run_tests():
        """Run all information extraction tests."""
        results = []
        
        # Run basic information extraction test
        result = await test_8b2_information_extraction()
        results.append(("8B2: Information Extraction", result))
        
        # Run constraint tracking test
        result = await test_8b2_constraint_tracking()
        results.append(("8B2b: Constraint Tracking", result))
        
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