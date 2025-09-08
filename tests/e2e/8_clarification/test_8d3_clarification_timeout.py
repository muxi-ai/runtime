#!/usr/bin/env python3
"""
Area 8 - Test Group 8D: Clarification Stack Management
Test 8D3: Clarification Timeout

Tests clarification session timeout and context expiration.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))  # For test_utils

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_8d3_clarification_abandonment():
    """Test clarification context switching (abandonment)."""
    print("\n=== Test 8D3: Clarification Context Switching ===")

    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    # Create unique test context
    ctx = TestContext("test_8d3")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

    try:
        # Start a potentially dangerous clarification
        print("\n1. Starting clarification for sensitive operation...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Delete files from the system",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response1.content}")

        # Should ask which files
        assert any(word in response1.content.lower() for word in [
            "which", "what", "files", "specify", "careful"
        ]), "Should ask for clarification about which files"

        # Instead of answering, switch context completely
        print("\n2. Switching context with unrelated message...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "Actually, tell me about the weather forecast",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response2.content}")

        # Should handle context switch gracefully
        response_lower = response2.content.lower()

        # Check if system recognized context switch
        context_switched = (
            # Either responds about weather
            any(word in response_lower for word in ["weather", "forecast", "temperature", "climate"]) or
            # Or acknowledges the context switch
            any(word in response_lower for word in ["instead", "help", "weather", "different"]) or
            # Or at least doesn't continue with file deletion
            not any(word in response_lower for word in ["delete", "files", "remove"])
        )
        assert context_switched, "Should switch context and not continue with file deletion"

        # Now go back and mention files - should NOT delete
        print("\n3. Mentioning files after context switch...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "important_data.txt and config.json",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response3.content}")

        # Should NOT interpret this as files to delete
        response_lower = response3.content.lower()
        assert not any(word in response_lower for word in [
            "delet", "remov", "will delete", "deleting"
        ]), "Should NOT delete files - clarification context was abandoned"

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Clarification context switching handled safely")
        print("✓ Started clarification for file deletion")
        print("✓ Context switched to different topic")
        print("✓ Original clarification safely abandoned")
        print("✓ File names not interpreted as deletion targets")
        print("\n" + "="*40)

        print("\n### Chat transcript:")
        print("\nUser: Delete files from the system")
        print(f"System: {response1.content[:300] + '...' if len(response1.content) > 300 else response1.content}")
        print("\nUser: Actually, tell me about the weather forecast")
        print(f"System: {response2.content[:300] + '...' if len(response2.content) > 300 else response2.content}")
        print("\nUser: important_data.txt and config.json")
        print(f"System: {response3.content[:300] + '...' if len(response3.content) > 300 else response3.content}")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8D3 FAILED: {e}")
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


async def test_8d3_session_timeout_simulation():
    """Test behavior with new session after clarification."""
    print("\n=== Test 8D3b: New Session After Clarification ===")

    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    # Create unique test context
    ctx = TestContext("test_8d3b")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

    try:
        # Start clarification in first session
        print("\n1. Starting clarification in first session...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Update the production database",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response1.content}")

        # Should ask for clarification
        assert any(word in response1.content.lower() for word in [
            "which", "what", "database", "table", "update", "careful"
        ]), "Should ask for clarification about database update"

        # Create new session (simulating timeout/reconnect)
        new_session = ctx.new_session()
        print(f"\n2. Creating new session: {new_session}")

        # Send a greeting in new session
        print("\n3. Greeting in new session...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "Hello, how can you help me today?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,  # New session ID
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response2.content}")

        # Should respond to greeting, not continue clarification
        response_lower = response2.content.lower()
        is_greeting_response = (
            any(word in response_lower for word in ["hello", "help", "assist", "can"]) and
            not any(word in response_lower for word in ["database", "update", "production", "which table"])
        )
        assert is_greeting_response, "Should respond to greeting, not continue old clarification"

        # Try to provide database details - should not execute update
        print("\n4. Mentioning database in new context...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "I need to work with the users table",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response3.content}")

        # Should treat as new request, not continuation
        response_lower = response3.content.lower()
        not_update_continuation = not any(phrase in response_lower for phrase in [
            "updating production",
            "will update",
            "proceeding with update",
            "update confirmed"
        ])
        assert not_update_continuation, "Should not treat as continuation of update request"

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Session boundary respected")
        print("✓ Started clarification in first session")
        print("✓ Created new session (timeout simulation)")
        print("✓ New session starts fresh conversation")
        print("✓ Old clarification context not carried over")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8D3b FAILED: {e}")
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


async def test_8d3_explicit_cancellation():
    """Test explicit clarification cancellation."""
    print("\n=== Test 8D3c: Explicit Clarification Cancellation ===")

    formation_path = Path(__file__).parent / "formations/formation-clarification/formation.yaml"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    # Create unique test context
    ctx = TestContext("test_8d3c")
    print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

    try:
        # Start clarification
        print("\n1. Starting clarification...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                "Deploy to production",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response1.content}")

        # Should ask for clarification
        assert any(word in response1.content.lower() for word in [
            "which", "what", "environment", "service", "application"
        ]), "Should ask for clarification about deployment"

        # Explicitly cancel
        print("\n2. Explicitly canceling...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                "Never mind, cancel that",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response2.content}")

        # Should acknowledge cancellation
        response_lower = response2.content.lower()
        cancelled = any(word in response_lower for word in [
            "cancel", "stopped", "abort", "okay", "understand", "no problem"
        ])
        assert cancelled, "Should acknowledge cancellation"

        # New request should start fresh
        print("\n3. Starting new request...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                "Show me the code",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=120.0
        )
        print(f"Response: {response3.content}")

        # Should ask about code, not deployment
        response_lower = response3.content.lower()
        new_context = (
            any(word in response_lower for word in ["code", "which", "what", "show"]) and
            not any(word in response_lower for word in ["deploy", "production"])
        )
        assert new_context, "Should start fresh context about code"

        print("\n" + "="*40)
        print("\n### Test Result:")
        print("🎉 SUCCESS: Explicit cancellation handled correctly")
        print("✓ Started deployment clarification")
        print("✓ User explicitly cancelled")
        print("✓ Cancellation acknowledged")
        print("✓ New request starts fresh context")
        print("\n" + "="*40)

        # Properly shut down
        await formation.stop_overlord()
        formation.shutdown()
        return True

    except Exception as e:
        print(f"\n❌ Test 8D3c FAILED: {e}")
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
        """Run all timeout/cancellation tests."""
        results = []

        # Run context switching test
        result = await test_8d3_clarification_abandonment()
        results.append(("8D3: Context Switching", result))

        # Run session timeout test
        result = await test_8d3_session_timeout_simulation()
        results.append(("8D3b: Session Timeout", result))

        # Run explicit cancellation test
        result = await test_8d3_explicit_cancellation()
        results.append(("8D3c: Explicit Cancellation", result))

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
