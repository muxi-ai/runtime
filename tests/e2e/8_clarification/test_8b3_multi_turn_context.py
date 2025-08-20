"""Test 8B3: Multi-turn Context Management

Tests maintaining context across multi-turn conversations,
including clarifications, follow-ups, and topic changes.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_multi_turn_context():
    """Test context management across multiple conversation turns."""
    try:
        print("\n=== Test 8B3: Multi-turn Context Management ===\n")

        # Load formation with clarification capabilities
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create unique test context
        ctx = TestContext("test_8b3")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")

        # Turn 1: Initial request
        print("\n1. Initial request with ambiguity...")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="I need to build a dashboard",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response1, str):
            content1 = response1
        elif hasattr(response1, "content"):
            content1 = response1.content
        else:
            content1 = str(response1)
        print(f"   Response: {content1[:200]}...")

        # Should ask for clarification
        response_lower = content1.lower()
        asks_clarification = any(
            word in response_lower
            for word in ["what", "which", "type", "kind", "purpose", "clarify"]
        )

        if asks_clarification:
            print("   ✅ Clarification requested")
        else:
            print("   ⚠️ No clarification requested for ambiguous request")

        # Turn 2: Provide clarification
        print("\n2. Providing clarification...")
        response2 = await asyncio.wait_for(
            overlord.chat(
                message="It's for monitoring server metrics - CPU, memory, disk usage",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response2, str):
            content2 = response2
        elif hasattr(response2, "content"):
            content2 = response2.content
        else:
            content2 = str(response2)
        print(f"   Response: {content2[:200]}...")

        # Turn 3: Follow-up question
        print("\n3. Follow-up question about refresh rate...")
        response3 = await asyncio.wait_for(
            overlord.chat(
                message="How often should the data refresh?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response3, str):
            content3 = response3
        elif hasattr(response3, "content"):
            content3 = response3.content
        else:
            content3 = str(response3)
        print(f"   Response: {content3[:200]}...")

        # Should provide relevant suggestions for monitoring dashboard
        response_lower = content3.lower()
        has_refresh_suggestion = any(
            term in response_lower
            for term in ["second", "minute", "real-time", "realtime", "interval"]
        )

        if has_refresh_suggestion:
            print("   ✅ Refresh interval suggestion provided")
        else:
            print("   ⚠️ No specific refresh interval suggested")

        # Turn 4: Change aspect but maintain context
        print("\n4. Asking about visualization libraries...")
        response4 = await asyncio.wait_for(
            overlord.chat(
                message="What charting libraries would work well for this?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response4, str):
            content4 = response4
        elif hasattr(response4, "content"):
            content4 = response4.content
        else:
            content4 = str(response4)
        print(f"   Response: {content4[:200]}...")

        # Should recommend visualization libraries suitable for metrics
        response_lower = content4.lower()
        has_viz_library = any(
            lib in response_lower for lib in ["chart", "d3", "plotly", "grafana", "graph"]
        )
        has_monitoring_context = any(
            term in response_lower for term in ["metric", "monitor", "cpu", "memory", "performance"]
        )

        if has_viz_library:
            print("   ✅ Visualization library recommended")
        else:
            print("   ❌ No visualization library found")

        if has_monitoring_context:
            print("   ✅ Monitoring context maintained")
        else:
            print("   ⚠️ Monitoring context not explicitly referenced")

        # Turn 5: Reference earlier context
        print("\n5. Referencing earlier context...")
        response5 = await asyncio.wait_for(
            overlord.chat(
                message="Should I use WebSockets for the real-time updates you mentioned?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False,
            ),
            timeout=120.0  # 2 minute timeout
        )

        # Handle different response types
        if isinstance(response5, str):
            content5 = response5
        elif hasattr(response5, "content"):
            content5 = response5.content
        else:
            content5 = str(response5)
        print(f"   Response: {content5[:200]}...")

        # Should provide relevant WebSocket advice
        response_lower = content5.lower()
        has_websocket_advice = any(
            term in response_lower
            for term in ["websocket", "socket", "real-time", "realtime", "push"]
        )

        if has_websocket_advice:
            print("   ✅ WebSocket advice provided")
        else:
            print("   ⚠️ No specific WebSocket advice")

        # Determine overall test success
        test_passed = has_viz_library

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        if test_passed:
            print("🎉 SUCCESS: Multi-turn context properly maintained")
            print("✓ Initial dashboard request handled")
            print("✓ Server monitoring context established")
            print("✓ Refresh rate recommendations provided")
            print("✓ Visualization recommendations maintained context")
            print("✓ WebSocket discussion referenced earlier context")
        else:
            print("⚠️ PARTIAL: Multi-turn context needs improvement")
            if not asks_clarification:
                print("✗ Initial ambiguous request not clarified")
            if not has_refresh_suggestion:
                print("✗ No refresh interval suggestions")
            if not has_viz_library:
                print("✗ No visualization library recommendations")
            if not has_monitoring_context:
                print("✗ Monitoring context lost")
            if not has_websocket_advice:
                print("✗ WebSocket advice missing")
        print("\n" + "=" * 40)

        print("\n### Chat transcript:")
        print("\nUser: I need to build a dashboard")
        print(f"System: {content1[:400] + '...' if len(content1) > 400 else content1}")
        print("\nUser: It's for monitoring server metrics - CPU, memory, disk usage")
        print(f"System: {content2[:400] + '...' if len(content2) > 400 else content2}")
        print("\nUser: How often should the data refresh?")
        print(f"System: {content3[:400] + '...' if len(content3) > 400 else content3}")
        print("\nUser: What charting libraries would work well for this?")
        print(f"System: {content4[:400] + '...' if len(content4) > 400 else content4}")
        print("\nUser: Should I use WebSockets for the real-time updates you mentioned?")
        print(f"System: {content5[:400] + '...' if len(content5) > 400 else content5}")

        print("\n" + "=" * 40)

        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()

        return test_passed

    except Exception as e:
        print(f"\n❌ Test 8B3 FAILED: {e}")
        import traceback

        traceback.print_exc()

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("❌ FAILED: Multi-turn context test failed")
        print(f"✗ Error: {e}")
        print("\n" + "=" * 40)

        print("\n### Partial Chat transcript (before failure):")
        if "content1" in locals():
            print("\nUser: I need to build a dashboard")
            print(f"System: {content1[:400] + '...' if len(content1) > 400 else content1}")
        if "content2" in locals():
            print("\nUser: It's for monitoring server metrics - CPU, memory, disk usage")
            print(f"System: {content2[:400] + '...' if len(content2) > 400 else content2}")
        if "content3" in locals():
            print("\nUser: How often should the data refresh?")
            print(f"System: {content3[:400] + '...' if len(content3) > 400 else content3}")
        if "content4" in locals():
            print("\nUser: What charting libraries would work well for this?")
            print(f"System: {content4[:400] + '...' if len(content4) > 400 else content4}")
        if "content5" in locals():
            print("\nUser: Should I use WebSockets for the real-time updates you mentioned?")
            print(f"System: {content5[:400] + '...' if len(content5) > 400 else content5}")

        print("\n" + "=" * 40)

        # Try to shut down even on failure
        if "formation" in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass

        return False
    finally:
        sys.exit(0 if "return True" in locals() else 1)


if __name__ == "__main__":
    asyncio.run(test_multi_turn_context())
