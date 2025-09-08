#!/usr/bin/env python3
"""
Test 10A3: Rephrasing Quality
Tests the quality of LLM rephrasing for streaming events.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402
from muxi.services.streaming import get_streaming_llm_config  # noqa: E402


async def main():
    """Test rephrasing quality in streaming events."""
    print("🚀 MUXI Runtime - Test 10A3: Rephrasing Quality")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-streaming"

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded")

        # Check if rephrasing is enabled
        streaming_config = get_streaming_llm_config()

        if not streaming_config or not streaming_config.get("enabled"):
            print("\n⚠️ Rephrasing is not enabled - skipping quality test")
            print("   To enable rephrasing, configure a streaming model in formation.yaml")
            return True  # Not a failure, just skip

        print("\n📋 Streaming configuration:")
        print(f"   Model: {streaming_config.get('model')}")
        print("   Rephrasing: ENABLED")

        print("\n📋 Test: Rephrasing Quality Check")
        print("-" * 40)

        user_id = "test_user"
        session_id = "rephrasing_test_10a3"

        # Make a request that should generate rephrased events
        response = await overlord.chat(
            message="Analyze the stock market trends and provide investment advice",
            user_id=user_id,
            session_id=session_id,
            stream=True,
        )

        # Collect events
        events = []
        if hasattr(response, "__aiter__"):
            async for chunk in response:
                events.append(chunk)
                # Show first few events for debugging
                if len(events) <= 3:
                    if isinstance(chunk, dict):
                        event_type = chunk.get('type', 'unknown')
                        content = chunk.get('content', '')[:150]
                        print(f"   Event {len(events)}: {event_type} - {content}")
                    else:
                        preview = str(chunk)[:150]
                        print(f"   Event {len(events)}: {preview}")

        # Check for rephrasing indicators
        print("\n📊 Rephrasing Analysis:")

        # Natural language indicators (first person, conversational)
        rephrasing_indicators = [
            "let me",
            "i need to",
            "i'll",
            "i'm",
            "i should",
            "thinking",
            "checking",
            "analyzing",
            "working on",
            "looking at",
            "considering",
            "examining",
        ]

        found_indicators = []
        sample_rephrased = None

        for event in events[:10]:  # Check first 10 events
            # Extract content from dict events
            if isinstance(event, dict):
                event_text = event.get('content', '')
            else:
                event_text = str(event)

            event_lower = event_text.lower()
            for indicator in rephrasing_indicators:
                if indicator in event_lower and indicator not in found_indicators:
                    found_indicators.append(indicator)
                    if not sample_rephrased:
                        sample_rephrased = event_text[:200]

        if found_indicators:
            print(f"   ✅ Found {len(found_indicators)} rephrasing indicators:")
            for ind in found_indicators[:5]:  # Show first 5
                print(f"      • '{ind}'")

            if sample_rephrased:
                print("\n   Sample rephrased content:")
                print(f"   '{sample_rephrased}...'")

            # Check for internal monologue style
            full_text = " ".join([
                event.get('content', '') if isinstance(event, dict) else str(event)
                for event in events
            ])
            if any(
                phrase in full_text.lower()
                for phrase in ["let me think", "i need to", "i'm going to"]
            ):
                print("\n   ✅ Internal monologue style detected")

        else:
            print("   ⚠️ No clear rephrasing indicators found")
            print("   Events may be using direct language without rephrasing")

        # Language consistency check
        print("\n📊 Language Consistency:")

        # All events should maintain consistent tone
        has_technical = any("api" in str(e).lower() or "json" in str(e).lower() for e in events[:5])
        has_natural = any(
            ind in " ".join([
                event.get('content', '') if isinstance(event, dict) else str(event)
                for event in events[:5]
            ]).lower()
            for ind in ["let me", "i'll", "thinking"]
        )

        if has_natural and not has_technical:
            print("   ✅ Consistent natural language throughout")
        elif has_technical and not has_natural:
            print("   ℹ️ Technical language (may not be rephrased)")
        else:
            print("   ⚠️ Mixed technical and natural language")

        # Results summary
        print("\n" + "=" * 60)

        if len(events) > 0:
            if found_indicators:
                print("✅ Test 10A3 PASSED: Rephrasing quality verified")
            else:
                print("⚠️ Test 10A3 WARNING: Rephrasing enabled but indicators not found")
                print("   This may be due to the specific prompt or model behavior")

            # Print full transcript
            print("\n" + "=" * 60)
            print("📜 STREAMING TRANSCRIPT:")
            print("=" * 60)
            for i, event in enumerate(events, 1):
                if isinstance(event, dict):
                    print(f"\n[Event {i}] Type: {event.get('type', 'unknown')}")
                    content = event.get('content', '')
                    print(f"  Content: {content}")
                    if 'stage' in event:
                        print(f"  Stage: {event['stage']}")
                    # Highlight rephrasing indicators found
                    event_lower = content.lower()
                    found_in_this = [ind for ind in rephrasing_indicators if ind in event_lower]
                    if found_in_this:
                        print(f"  ** REPHRASING INDICATORS: {found_in_this} **")
                else:
                    print(f"\n[Event {i}] Raw: {event}")
            print("\n" + "=" * 60)

            return True
        else:
            print("❌ Test 10A3 FAILED: No streaming events received")
            return False

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
