#!/usr/bin/env python3
"""
Area 8 - Test Group 8B: Information Flow
Test 8B3: Multi-turn Context Management

Tests that context is properly maintained across multiple conversation turns,
including clarifications, follow-ups, and topic changes.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation
from test_utils import TestContext


async def test_8b3_multi_turn_conversation():
    """Test context management across multiple conversation turns."""
    print("\n=== Test 8B3: Multi-turn Context Management ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8b3")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Turn 1: Initial request
        print("\n1. Initial request with ambiguity...")
        response1 = await overlord.chat(
            "I need to build a dashboard",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response1.content}")
        
        # Should ask for clarification
        response_lower = response1.content.lower()
        assert any(word in response_lower for word in ["what", "which", "type", "kind", "purpose", "clarify"]), \
            "Should ask for clarification about the dashboard"
        
        # Turn 2: Provide clarification
        print("\n2. Providing clarification...")
        response2 = await overlord.chat(
            "It's for monitoring server metrics - CPU, memory, disk usage",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response2.content}")
        
        # Turn 3: Follow-up question
        print("\n3. Follow-up question about refresh rate...")
        response3 = await overlord.chat(
            "How often should the data refresh?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response3.content}")
        
        # Should provide relevant suggestions for monitoring dashboard
        response_lower = response3.content.lower()
        assert any(term in response_lower for term in ["second", "minute", "real-time", "realtime", "interval"]), \
            "Should suggest refresh intervals appropriate for monitoring"
        
        # Turn 4: Change aspect but maintain context
        print("\n4. Asking about visualization libraries...")
        response4 = await overlord.chat(
            "What charting libraries would work well for this?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response4.content}")
        
        # Should recommend visualization libraries suitable for metrics
        response_lower = response4.content.lower()
        assert any(lib in response_lower for lib in ["chart", "d3", "plotly", "grafana", "graph"]), \
            "Should recommend visualization libraries"
        
        # Should still reference monitoring/metrics context
        assert any(term in response_lower for term in ["metric", "monitor", "cpu", "memory", "performance"]), \
            "Should maintain monitoring dashboard context"
        
        # Turn 5: Reference earlier context
        print("\n5. Referencing earlier context...")
        response5 = await overlord.chat(
            "Should I use WebSockets for the real-time updates you mentioned?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response5.content}")
        
        # Should provide relevant WebSocket advice
        response_lower = response5.content.lower()
        assert any(term in response_lower for term in ["websocket", "socket", "real-time", "realtime", "push"]), \
            "Should discuss WebSocket usage"
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Multi-turn context properly maintained")
        print("✓ Initial dashboard request triggered clarification")
        print("✓ Server monitoring context established")
        print("✓ Refresh rate recommendations considered context")
        print("✓ Visualization recommendations maintained context")
        print("✓ WebSocket discussion referenced earlier context")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: I need to build a dashboard")
        print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        print("\nUser: It's for monitoring server metrics - CPU, memory, disk usage")
        print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        print("\nUser: How often should the data refresh?")
        print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        print("\nUser: What charting libraries would work well for this?")
        print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        print("\nUser: Should I use WebSockets for the real-time updates you mentioned?")
        print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
        print("\n" + "="*40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8B3 FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Multi-turn context test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: I need to build a dashboard")
            print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        if 'response2' in locals():
            print("\nUser: It's for monitoring server metrics - CPU, memory, disk usage")
            print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        if 'response3' in locals():
            print("\nUser: How often should the data refresh?")
            print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        if 'response4' in locals():
            print("\nUser: What charting libraries would work well for this?")
            print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        if 'response5' in locals():
            print("\nUser: Should I use WebSockets for the real-time updates you mentioned?")
            print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
        print("\n" + "="*40)

        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        return False


async def test_8b3_topic_switching():
    """Test context management when switching between topics."""
    print("\n=== Test 8B3b: Topic Switching with Context Retention ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Create unique test context
    ctx = TestContext("test_8b3b")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
    
    try:
        # Topic 1: Database design
        print("\n1. Topic 1: Database design...")
        response1 = await overlord.chat(
            "I'm designing a database for an online bookstore",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response1.content}")
        
        print("\n2. Database question...")
        response2 = await overlord.chat(
            "Should I use normalized or denormalized tables?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response2.content}")
        
        # Should discuss database normalization in bookstore context
        response_lower = response2.content.lower()
        assert any(term in response_lower for term in ["normal", "denormal", "3nf", "join"]), \
            "Should discuss normalization"
        
        # Topic 2: Switch to API design
        print("\n3. Topic 2: Switching to API design...")
        response3 = await overlord.chat(
            "Now let's talk about the REST API for this bookstore",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response3.content}")
        
        print("\n4. API question...")
        response4 = await overlord.chat(
            "What endpoints would you recommend?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response4.content}")
        
        # Should suggest bookstore-related endpoints
        response_lower = response4.content.lower()
        assert any(endpoint in response_lower for endpoint in ["book", "author", "order", "cart", "user", "category"]), \
            "Should suggest bookstore-specific endpoints"
        
        # Topic 3: Reference both previous topics
        print("\n5. Referencing both topics...")
        response5 = await overlord.chat(
            "How should the API interact with the database we discussed?",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"Response: {response5.content}")
        
        # Should reference both database and API context
        response_lower = response5.content.lower()
        assert any(db_term in response_lower for db_term in ["database", "table", "query", "orm"]), \
            "Should reference database context"
        assert any(api_term in response_lower for api_term in ["api", "endpoint", "rest", "http"]), \
            "Should reference API context"
        assert any(book_term in response_lower for book_term in ["book", "store", "order"]), \
            "Should maintain bookstore context"
        
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Context retained across topic switches")
        print("✓ Online bookstore context established")
        print("✓ Database normalization discussion maintained context")
        print("✓ API design discussion maintained bookstore context")
        print("✓ Final question referenced both database and API topics")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: I'm designing a database for an online bookstore")
        print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        print("\nUser: Should I use normalized or denormalized tables?")
        print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        print("\nUser: Now let's talk about the REST API for this bookstore")
        print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        print("\nUser: What endpoints would you recommend?")
        print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        print("\nUser: How should the API interact with the database we discussed?")
        print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
        print("\n" + "="*40)
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        return True
        
    except Exception as e:
        print(f"\n❌ Test 8B3b FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Try to print partial transcript even on failure
        print("\n" + "="*40)
        print("\n### Test Result:")
        print("❌ FAILED: Topic switching test failed")
        print(f"✗ Error: {e}")
        print("\n" + "="*40)

        print("\n### Partial Chat transcript (before failure):")
        if 'response1' in locals():
            print("\nUser: I'm designing a database for an online bookstore")
            print(f"System: {response1.content[:400] + '...' if len(response1.content) > 400 else response1.content}")
        if 'response2' in locals():
            print("\nUser: Should I use normalized or denormalized tables?")
            print(f"System: {response2.content[:400] + '...' if len(response2.content) > 400 else response2.content}")
        if 'response3' in locals():
            print("\nUser: Now let's talk about the REST API for this bookstore")
            print(f"System: {response3.content[:400] + '...' if len(response3.content) > 400 else response3.content}")
        if 'response4' in locals():
            print("\nUser: What endpoints would you recommend?")
            print(f"System: {response4.content[:400] + '...' if len(response4.content) > 400 else response4.content}")
        if 'response5' in locals():
            print("\nUser: How should the API interact with the database we discussed?")
            print(f"System: {response5.content[:400] + '...' if len(response5.content) > 400 else response5.content}")
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
        """Run all multi-turn context tests."""
        results = []
        
        # Run multi-turn conversation test
        result = await test_8b3_multi_turn_conversation()
        results.append(("8B3: Multi-turn Conversation", result))
        
        # Run topic switching test
        result = await test_8b3_topic_switching()
        results.append(("8B3b: Topic Switching", result))
        
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