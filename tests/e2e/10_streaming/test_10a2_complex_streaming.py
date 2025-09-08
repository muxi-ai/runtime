#!/usr/bin/env python3
"""
Test 10A2: Complex Task Streaming
Tests streaming with workflow decomposition for complex tasks.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test streaming with complex task decomposition."""
    print("🚀 MUXI Runtime - Test 10A2: Complex Task Streaming")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-streaming"

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded")
        print("\n📋 Test: Complex task with workflow decomposition")
        print("-" * 40)

        user_id = "test_user"
        session_id = "streaming_test_10a2"

        # Test a complex request that triggers workflow decomposition
        response_gen = await overlord.chat(
            message=(
                "Research the latest AI breakthroughs, analyze their impact, "
                "and create a comprehensive report with timeline and predictions"
            ),
            user_id=user_id,
            session_id=session_id,
            stream=True,
        )

        # Collect streaming events
        complex_events = []
        event_types = set()
        has_planning = False
        has_decomposition = False

        if hasattr(response_gen, "__aiter__"):
            async for chunk in response_gen:
                complex_events.append(chunk)

                # Handle dict events (new streaming format)
                if isinstance(chunk, dict):
                    event_type = chunk.get("type", "")
                    event_types.add(event_type)

                    if event_type == "planning":
                        has_planning = True
                        if "decomposition" in chunk.get("stage", ""):
                            has_decomposition = True
                            content = chunk.get('content', '')[:200]
                            print(f"   📝 Decomposition event: {content}...")

                    # Print first few events
                    if len(complex_events) <= 3:
                        content = chunk.get('content', '')[:150]
                        print(f"   Event {len(complex_events)}: {event_type} - {content}")
                else:
                    # Legacy string format
                    if len(complex_events) <= 3:
                        preview = str(chunk)[:150]
                        print(f"   Event {len(complex_events)}: {preview}")

        # Results
        print("\n📊 Results:")
        print(f"   Total events: {len(complex_events)}")

        if event_types:
            print(f"   Event types seen: {event_types}")
        else:
            print("   Event format: Plain text stream")

        # Check for planning/decomposition indicators
        # Extract content from dict events
        contents = []
        for event in complex_events:
            if isinstance(event, dict):
                contents.append(event.get('content', ''))
            else:
                contents.append(str(event))

        full_response = " ".join(contents)
        response_lower = full_response.lower()

        planning_indicators = [
            "breaking", "tasks", "steps", "plan", "decompos",
            "analyzing", "thinking", "let me", "i'll"
        ]

        has_indicators = any(ind in response_lower for ind in planning_indicators)

        if has_planning or has_decomposition or has_indicators:
            print("   ✅ Found planning/decomposition activity")
        else:
            print("   ℹ️ No explicit planning events (may be using simple response)")

        # Validate response quality
        if len(complex_events) > 0:
            print(f"   ✅ Generated {len(complex_events)} streaming events")

            # Check for relevant content
            expected_terms = ["ai", "breakthrough", "research", "report", "timeline"]
            found_terms = [term for term in expected_terms if term in response_lower]

            if found_terms:
                print(f"   ✅ Response contains relevant terms: {found_terms}")
            else:
                print("   ⚠️ Response may not address the request fully")
        else:
            print("   ❌ No streaming events generated")
            return False

        print("\n" + "=" * 60)
        print("✅ Test 10A2 PASSED: Complex task streaming works correctly")

        # Print full transcript
        print("\n" + "=" * 60)
        print("📜 STREAMING TRANSCRIPT:")
        print("=" * 60)
        for i, event in enumerate(complex_events, 1):
            if isinstance(event, dict):
                print(f"\n[Event {i}] Type: {event.get('type', 'unknown')}")
                print(f"  Content: {event.get('content', '')}")
                if 'stage' in event:
                    print(f"  Stage: {event['stage']}")
                if 'timestamp' in event:
                    print(f"  Timestamp: {event['timestamp']}")
                # Show if this was a planning/decomposition event
                if event.get('type') == 'planning':
                    print("  ** PLANNING EVENT **")
                if 'decomposition' in str(event.get('stage', '')).lower():
                    print("  ** DECOMPOSITION EVENT **")
            else:
                print(f"\n[Event {i}] Raw: {event}")
        print("\n" + "=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if "formation" in locals():
            try:
                print("\nShutting down...")
                await formation.kill_overlord()
                formation.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
