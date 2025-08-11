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

from muxi.formation import Formation


async def test_8b3_multi_turn_conversation():
    """Test context management across multiple conversation turns."""
    print("\n=== Test 8B3: Multi-turn Context Management ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Turn 1: Initial request
        print("\n1. Initial request with ambiguity...")
        response = await overlord.chat(
            "I need to build a dashboard",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should ask for clarification
        response_lower = response.lower()
        assert any(word in response_lower for word in ["what", "which", "type", "kind", "purpose", "clarify"]), \
            "Should ask for clarification about the dashboard"
        
        # Turn 2: Provide clarification
        print("\n2. Providing clarification...")
        response = await overlord.chat(
            "It's for monitoring server metrics - CPU, memory, disk usage",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Turn 3: Follow-up question
        print("\n3. Follow-up question about refresh rate...")
        response = await overlord.chat(
            "How often should the data refresh?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should provide relevant suggestions for monitoring dashboard
        response_lower = response.lower()
        assert any(term in response_lower for term in ["second", "minute", "real-time", "realtime", "interval"]), \
            "Should suggest refresh intervals appropriate for monitoring"
        
        # Turn 4: Change aspect but maintain context
        print("\n4. Asking about visualization libraries...")
        response = await overlord.chat(
            "What charting libraries would work well for this?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should recommend visualization libraries suitable for metrics
        response_lower = response.lower()
        assert any(lib in response_lower for lib in ["chart", "d3", "plotly", "grafana", "graph"]), \
            "Should recommend visualization libraries"
        
        # Should still reference monitoring/metrics context
        assert any(term in response_lower for term in ["metric", "monitor", "cpu", "memory", "performance"]), \
            "Should maintain monitoring dashboard context"
        
        # Turn 5: Reference earlier context
        print("\n5. Referencing earlier context...")
        response = await overlord.chat(
            "Should I use WebSockets for the real-time updates you mentioned?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should provide relevant WebSocket advice
        response_lower = response.lower()
        assert any(term in response_lower for term in ["websocket", "socket", "real-time", "realtime", "push"]), \
            "Should discuss WebSocket usage"
        
        print("\n✅ Test 8B3 PASSED: Multi-turn context properly maintained")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8B3 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8B3 ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


async def test_8b3_topic_switching():
    """Test context management when switching between topics."""
    print("\n=== Test 8B3b: Topic Switching with Context Retention ===")
    
    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    try:
        # Topic 1: Database design
        print("\n1. Topic 1: Database design...")
        response = await overlord.chat(
            "I'm designing a database for an online bookstore",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        print("\n2. Database question...")
        response = await overlord.chat(
            "Should I use normalized or denormalized tables?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should discuss database normalization in bookstore context
        response_lower = response.lower()
        assert any(term in response_lower for term in ["normal", "denormal", "3nf", "join"]), \
            "Should discuss normalization"
        
        # Topic 2: Switch to API design
        print("\n3. Topic 2: Switching to API design...")
        response = await overlord.chat(
            "Now let's talk about the REST API for this bookstore",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        print("\n4. API question...")
        response = await overlord.chat(
            "What endpoints would you recommend?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should suggest bookstore-related endpoints
        response_lower = response.lower()
        assert any(endpoint in response_lower for endpoint in ["book", "author", "order", "cart", "user", "category"]), \
            "Should suggest bookstore-specific endpoints"
        
        # Topic 3: Reference both previous topics
        print("\n5. Referencing both topics...")
        response = await overlord.chat(
            "How should the API interact with the database we discussed?",
            user_id="test_user"
        )
        print(f"Response: {response}")
        
        # Should reference both database and API context
        response_lower = response.lower()
        assert any(db_term in response_lower for db_term in ["database", "table", "query", "orm"]), \
            "Should reference database context"
        assert any(api_term in response_lower for api_term in ["api", "endpoint", "rest", "http"]), \
            "Should reference API context"
        assert any(book_term in response_lower for book_term in ["book", "store", "order"]), \
            "Should maintain bookstore context"
        
        print("\n✅ Test 8B3b PASSED: Context retained across topic switches")
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test 8B3b FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test 8B3b ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await formation.stop()


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
    
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)