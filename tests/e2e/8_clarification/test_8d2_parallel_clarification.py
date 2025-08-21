#!/usr/bin/env python3
"""
Area 8 - Test Group 8D: Clarification Stack Management
Test 8D2: Parallel Clarification Branches

Tests handling of parallel clarification branches where multiple
aspects need clarification simultaneously.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_8d2_parallel_source_clarification():
    """Test parallel clarification for multiple data sources."""
    print("\n=== Test 8D2: Parallel Source Clarification ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8d2")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Request that needs clarification about multiple things
        print("\n1. Initial request needing multiple clarifications...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Compare the data from both sources",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response1.content}")
        
        # Should ask about first source
        assert any(word in response1.content.lower() for word in ["first", "source", "what", "which"]), \
            "Should ask about the first source"
        
        # Clarify first source
        print("\n2. Clarifying first source...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "PostgreSQL database",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response2.content}")
        
        # Should ask about second source or database details
        response_lower = response2.content.lower()
        assert any(word in response_lower for word in ["second", "other", "database", "table", "what"]), \
            "Should ask about second source or need more database details"
        
        # Clarify second source
        print("\n3. Clarifying second source...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "REST API endpoint",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response3.content}")
        
        # Should ask for more details about one or both sources
        response_lower = response3.content.lower()
        needs_details = any(word in response_lower for word in [
            "table", "endpoint", "url", "which", "compare", "field", "column"
        ])
        assert needs_details, "Should ask for specific details about sources"
        
        # Provide database details
        print("\n4. Providing database table details...")
        response4 = await asyncio.wait_for(
            overlord.chat(
                "The users table for the database",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response4.content}")
        
        # Should ask about API endpoint
        response_lower = response4.content.lower()
        assert any(word in response_lower for word in ["api", "endpoint", "url", "rest"]), \
            "Should ask about API endpoint details"
        
        # Provide API details
        print("\n5. Providing API endpoint details...")
        response5 = await asyncio.wait_for(
            overlord.chat(
                "/api/v2/customers endpoint",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response5.content}")
        
        # Should now have enough context OR recognize lack of tools
        response_lower = response5.content.lower()
        
        # Check if system acknowledges it collected the info but lacks tools
        lacks_tools = any(phrase in response_lower for phrase in [
            "don't have the tools",
            "don't have access",
            "cannot access",
            "can't access",
            "unable to access",
            "don't have the capability",
            "cannot directly access"
        ])
        
        # Check if system provides comparison guidance despite lacking tools
        has_comparison_context = any(word in response_lower for word in ["compare", "comparison", "match", "difference"])
        
        # Either it lacks tools (expected) or provides comparison guidance
        assert lacks_tools or has_comparison_context, \
            "Should either acknowledge lack of tools or provide comparison guidance"
        
        # If it lacks tools, that's the expected behavior for this test
        if lacks_tools:
            print("✅ System correctly identified it lacks database/API access tools (expected)")
        else:
            print("✅ System provided comparison guidance")
        
        # Verify both branches are remembered
        print("\n6. Verifying parallel context preservation...")
        response6 = await asyncio.wait_for(
            overlord.chat(
                "What sources am I comparing?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response6.content}")
        
        response_lower = response6.content.lower()
        context_preserved = (
            ("postgresql" in response_lower or "database" in response_lower) and
            ("users" in response_lower) and
            ("api" in response_lower or "rest" in response_lower) and
            ("customers" in response_lower or "/api/v2/customers" in response_lower)
        )
        assert context_preserved, "Should remember both parallel clarification branches"
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Parallel clarification branches handled correctly")
        print("✓ First branch: PostgreSQL database → users table")
        print("✓ Second branch: REST API → /api/v2/customers endpoint")
        print("✓ Both branches preserved and available for comparison")
        print("✓ Context maintained across parallel clarifications")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Compare the data from both sources")
        print(f"System: {response1.content[:300] + '...' if len(response1.content) > 300 else response1.content}")
        print("\nUser: PostgreSQL database")
        print(f"System: {response2.content[:300] + '...' if len(response2.content) > 300 else response2.content}")
        print("\nUser: REST API endpoint")
        print(f"System: {response3.content[:300] + '...' if len(response3.content) > 300 else response3.content}")
        print("\nUser: The users table for the database")
        print(f"System: {response4.content[:300] + '...' if len(response4.content) > 300 else response4.content}")
        print("\nUser: /api/v2/customers endpoint")
        print(f"System: {response5.content[:300] + '...' if len(response5.content) > 300 else response5.content}")
        print("\nUser: What sources am I comparing?")
        print(f"System: {response6.content[:300] + '...' if len(response6.content) > 300 else response6.content}")
        print("\n" + "="*40)
        
        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8D2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_8d2_interleaved_clarifications():
    """Test interleaved clarifications for complex multi-part request."""
    print("\n=== Test 8D2b: Interleaved Multi-Part Clarifications ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8d2b")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Complex request needing multiple clarifications
        print("\n1. Complex multi-part request...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Create a report comparing performance metrics and send it to the team",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response1.content}")
        
        # Should ask about metrics or time period
        assert any(word in response1.content.lower() for word in [
            "metric", "performance", "which", "what", "period", "time"
        ]), "Should ask about metrics or time period"
        
        # Partial clarification
        print("\n2. Clarifying metrics type...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "API response times and error rates",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response2.content}")
        
        # Should ask about time period or team
        response_lower = response2.content.lower()
        assert any(word in response_lower for word in [
            "period", "time", "when", "team", "who", "send"
        ]), "Should ask about time period or team"
        
        # Clarify time period
        print("\n3. Clarifying time period...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "Last 30 days",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response3.content}")
        
        # Should ask about team or format
        response_lower = response3.content.lower()
        assert any(word in response_lower for word in [
            "team", "who", "send", "email", "format", "report"
        ]), "Should ask about team or report format"
        
        # Clarify team
        print("\n4. Clarifying team...")
        response4 = await asyncio.wait_for(
            overlord.chat(
                "Engineering team via email",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response4.content}")
        
        # Should now have complete context
        response_lower = response4.content.lower()
        has_all_context = (
            any(word in response_lower for word in ["api", "response", "error"]) and
            any(word in response_lower for word in ["30", "days", "month"]) and
            any(word in response_lower for word in ["engineering", "team", "email"])
        )
        assert has_all_context, "Should have all context for report creation"
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Interleaved clarifications handled correctly")
        print("✓ Part 1: Metrics → API response times and error rates")
        print("✓ Part 2: Time period → Last 30 days")
        print("✓ Part 3: Recipients → Engineering team via email")
        print("✓ All parts integrated for complete task execution")
        print("\n" + "="*40)
        
        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8D2b FAILED: {e}")
        import traceback
        traceback.print_exc()
        
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
        """Run all parallel clarification tests."""
        results = []
        
        # Run parallel source clarification test
        result = await test_8d2_parallel_source_clarification()
        results.append(("8D2: Parallel Source Clarification", result))
        
        # Run interleaved clarifications test
        result = await test_8d2_interleaved_clarifications()
        results.append(("8D2b: Interleaved Clarifications", result))
        
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