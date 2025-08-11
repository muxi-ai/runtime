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
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_8b2_information_extraction():
    """Test extraction of key project information from conversation."""
    print("\n=== Test 8B2: Information Extraction ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8b2")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Test 1: Extract budget and timeline
        print("\n1. Providing budget and timeline information...")
        response1 = await overlord.chat(
            "My budget is $5000 and timeline is 2 weeks for the MVP",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response1.content}")
        assert response1 is not None
        
        # Test 2: Ask for recommendations that should consider budget/timeline
        print("\n2. Asking for tech stack recommendation...")
        response2 = await overlord.chat(
            "What tech stack would you recommend for a quick prototype?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response2.content}")
        
        response_lower = response2.content.lower()
        # Should mention quick/rapid/fast development given 2-week timeline
        assert any(term in response_lower for term in ["quick", "rapid", "fast", "mvp", "prototype", "week"]), \
            "Should reference the tight timeline"
        
        # Should suggest cost-effective solutions given $5000 budget
        assert any(term in response_lower for term in ["cost", "budget", "free", "open", "affordable"]), \
            "Should consider budget constraints"
        
        # Test 3: Extract technical requirements
        print("\n3. Providing technical requirements...")
        response3 = await overlord.chat(
            "The app needs user authentication, real-time chat, and payment processing",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response3.content}")
        
        # Test 4: Ask specific question that should use extracted requirements
        print("\n4. Asking about authentication solution...")
        response4 = await overlord.chat(
            "Which authentication solution would work best?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response4.content}")
        
        response_lower = response4.content.lower()
        # Should mention auth solutions
        assert any(auth in response_lower for auth in ["auth0", "firebase", "supabase", "jwt", "oauth"]), \
            "Should recommend authentication solutions"
        
        # Should consider real-time and payment requirements
        assert any(term in response_lower for term in ["real-time", "realtime", "chat", "payment", "stripe"]), \
            "Should reference other requirements when making recommendations"
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Information properly extracted and used")
        print("✓ Budget and timeline information extracted")
        print("✓ Tech stack recommendation considered constraints")
        print("✓ Technical requirements captured and referenced")
        print("✓ Authentication recommendation used all context")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: My budget is $5000 and timeline is 2 weeks for the MVP")
        print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        print("\nUser: What tech stack would you recommend for a quick prototype?")
        print(f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")
        print("\nUser: The app needs user authentication, real-time chat, and payment processing")
        print(f"System: {response3.content[:300] + '...' if len(response3.content) > 300 else response3.content}")
        print("\nUser: Which authentication solution would work best?")
        print(f"System: {response4.content[:500] + '...' if len(response4.content) > 500 else response4.content}")
        print("\n" + "="*40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8B2 FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Information extraction test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: My budget is $5000 and timeline is 2 weeks for the MVP")
            print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        if 'response2' in locals():
            print("\nUser: What tech stack would you recommend for a quick prototype?")
            print(f"System: {response2.content[:500] + '...' if len(response2.content) > 500 else response2.content}")
        if 'response3' in locals():
            print("\nUser: The app needs user authentication, real-time chat, and payment processing")
            print(f"System: {response3.content[:300] + '...' if len(response3.content) > 300 else response3.content}")
        if 'response4' in locals():
            print("\nUser: Which authentication solution would work best?")
            print(f"System: {response4.content[:500] + '...' if len(response4.content) > 500 else response4.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_8b2_constraint_tracking():
    """Test tracking of multiple constraints and preferences."""
    print("\n=== Test 8B2b: Constraint Tracking ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8b2b")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Provide multiple constraints across messages
        print("\n1. Constraint 1: Team size...")
        response1 = await overlord.chat(
            "We're a small team of 3 developers",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response1.content}")
        
        print("\n2. Constraint 2: Experience level...")
        response2 = await overlord.chat(
            "We're all junior developers with 1-2 years experience",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response2.content}")
        
        print("\n3. Constraint 3: Deployment preference...")
        response3 = await overlord.chat(
            "We prefer to deploy on AWS",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response3.content}")
        
        print("\n4. Constraint 4: Mobile requirement...")
        response4 = await overlord.chat(
            "The app needs to work well on mobile devices",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response4.content}")
        
        # Ask for comprehensive recommendation
        print("\n5. Asking for architecture recommendation considering ALL constraints...")
        response5 = await overlord.chat(
            "Based on everything I've told you, what architecture would you recommend?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response5.content}")
        
        response_lower = response5.content.lower()
        
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
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Multiple constraints properly tracked")
        print("✓ Team size constraint captured (3 developers)")
        print("✓ Experience level constraint captured (junior)")
        print("✓ Deployment preference captured (AWS)")
        print("✓ Mobile requirement captured")
        print("✓ Final recommendation considered all constraints")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: We're a small team of 3 developers")
        print(f"System: {response1.content[:300] + '...' if len(response1.content) > 300 else response1.content}")
        print("\nUser: We're all junior developers with 1-2 years experience")
        print(f"System: {response2.content[:300] + '...' if len(response2.content) > 300 else response2.content}")
        print("\nUser: We prefer to deploy on AWS")
        print(f"System: {response3.content[:300] + '...' if len(response3.content) > 300 else response3.content}")
        print("\nUser: The app needs to work well on mobile devices")
        print(f"System: {response4.content[:300] + '...' if len(response4.content) > 300 else response4.content}")
        print("\nUser: Based on everything I've told you, what architecture would you recommend?")
        print(f"System: {response5.content[:500] + '...' if len(response5.content) > 500 else response5.content}")
        print("\n" + "="*40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8B2b FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Constraint tracking test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: We're a small team of 3 developers")
            print(f"System: {response1.content[:300] + '...' if len(response1.content) > 300 else response1.content}")
        if 'response2' in locals():
            print("\nUser: We're all junior developers with 1-2 years experience")
            print(f"System: {response2.content[:300] + '...' if len(response2.content) > 300 else response2.content}")
        if 'response3' in locals():
            print("\nUser: We prefer to deploy on AWS")
            print(f"System: {response3.content[:300] + '...' if len(response3.content) > 300 else response3.content}")
        if 'response4' in locals():
            print("\nUser: The app needs to work well on mobile devices")
            print(f"System: {response4.content[:300] + '...' if len(response4.content) > 300 else response4.content}")
        if 'response5' in locals():
            print("\nUser: Based on everything I've told you, what architecture would you recommend?")
            print(f"System: {response5.content[:500] + '...' if len(response5.content) > 500 else response5.content}")
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
    
    try:
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    finally:
        pass