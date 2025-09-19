#!/usr/bin/env python3
"""
Test 10A5: Progress Control
Tests the overlord.response.progress setting to control streaming event emissions.
When progress=false, only content events should be streamed (no thinking/planning).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402
from muxi.services.streaming import get_streaming_llm_config  # noqa: E402


async def main():
    """Test progress control for streaming events."""
    print("🚀 MUXI Runtime - Test 10A5: Progress Control")
    print("=" * 60)

    # Use the formation with progress disabled
    formation_path = Path(__file__).parent / "formation-streaming" / "formation-without-progress.yaml"
    formation = None  # Initialize to None for finally block

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded (with progress: false)")

        # Verify configuration
        streaming_config = get_streaming_llm_config()

        if streaming_config:
            progress_enabled = streaming_config.get("progress", True)
            print("\n📋 Streaming configuration:")
            print(f"   Model: {streaming_config.get('model')}")
            print(f"   Rephrasing: {streaming_config.get('enabled')}")
            print(f"   Progress: {'ENABLED' if progress_enabled else 'DISABLED'}")

            if progress_enabled:
                print("\n⚠️ WARNING: Progress is enabled, but test expects it disabled")
                print("   Check formation-without-progress.yaml has progress: false")
        else:
            print("\n⚠️ No streaming configuration found")

        print("\n📋 Test: Progress Events Control")
        print("-" * 40)

        user_id = "test_user"
        session_id = "progress_test_10a5"

        # Make a complex request that would normally generate progress events
        print("\n🔍 Testing complex task (should normally emit progress events)...")

        response_stream = await overlord.chat(
            message=(
                "Analyze the current economic situation, research market trends, "
                "and provide a detailed investment strategy"
            ),
            user_id=user_id,
            session_id=session_id,
            stream=True,
        )

        # Collect and analyze events
        all_events = []
        progress_events = []
        content_events = []

        # Progress indicators to look for
        progress_indicators = [
            "thinking", "planning", "analyzing", "checking",
            "breaking", "decomposing", "let me", "i'll",
            "working on", "processing", "researching"
        ]

        if hasattr(response_stream, "__aiter__"):
            print("\n📝 Analyzing streamed events...")

            async for chunk in response_stream:
                all_events.append(chunk)

                # Extract content from dict events
                if isinstance(chunk, dict):
                    chunk_text = chunk.get('content', '')
                    event_type = chunk.get('type', '')
                    # Progress events might be marked in type
                    if event_type == 'progress':
                        progress_events.append(chunk)
                else:
                    chunk_text = str(chunk)
                    event_type = ''

                chunk_lower = chunk_text.lower()

                # Categorize the event by content
                is_progress = any(ind in chunk_lower for ind in progress_indicators)

                if is_progress and chunk not in progress_events:
                    progress_events.append(chunk)
                    # Show first progress event found
                    if len(progress_events) == 1:
                        if isinstance(chunk, dict):
                            preview = f"{event_type} - {chunk_text[:150]}"
                        else:
                            preview = chunk_text[:150]
                        print(f"\n   ⚠️ Found progress event: {preview}")
                else:
                    content_events.append(chunk)

                # Show first few events
                if len(all_events) <= 3:
                    if isinstance(chunk, dict):
                        preview = f"{event_type} - {chunk_text[:100]}"
                    else:
                        preview = chunk[:100] if len(chunk) > 100 else chunk
                    print(f"   Event {len(all_events)}: {preview}")

        # Results analysis
        print("\n📊 Results:")
        print(f"   Total events: {len(all_events)}")
        print(f"   Progress events: {len(progress_events)}")
        print(f"   Content events: {len(content_events)}")

        # Verify behavior based on configuration
        if not streaming_config or streaming_config.get("progress", True):
            # Progress is enabled - we expect progress events
            print("\n📋 Expected behavior: Progress ENABLED")

            if progress_events:
                print("   ✅ Progress events found (as expected)")
            else:
                print("   ⚠️ No progress events found (might be a simple response)")

            test_passed = True  # Either way is fine when progress is enabled

        else:
            # Progress is disabled - we should NOT see progress events
            print("\n📋 Expected behavior: Progress DISABLED (content only)")

            if len(progress_events) == 0:
                print("   ✅ No progress events emitted (as expected)")
                print("   ✅ Only content streamed to save LLM costs")
                test_passed = True
            else:
                print(f"   ❌ Found {len(progress_events)} progress events (should be 0)")
                print("   These events should have been filtered when progress=false")

                # Show some examples of leaked progress events
                print("\n   Examples of unexpected progress events:")
                for event in progress_events[:3]:
                    preview = event[:150] if len(event) > 150 else event
                    print(f"      • {preview}")

                test_passed = False

        # Check that we still got actual content
        if len(content_events) > 0 or len(all_events) > 0:
            print(f"   ✅ Received {'content' if content_events else 'response'} events")

            # Verify response quality
            # Extract text from dict events for joining
            text_events = []
            for event in all_events:
                if isinstance(event, dict):
                    text_events.append(event.get('content', ''))
                else:
                    text_events.append(str(event))
            full_response = "".join(text_events)
            expected_terms = ["economic", "market", "investment", "strategy", "trend"]
            found_terms = [t for t in expected_terms if t in full_response.lower()]

            if found_terms:
                print(f"   ✅ Response addresses the request: {found_terms[:3]}")
        else:
            print("   ❌ No events received at all")
            test_passed = False

        # Summary
        print("\n" + "=" * 60)

        if test_passed:
            if not streaming_config or streaming_config.get("progress", True):
                print("✅ Test 10A5 PASSED: Progress control working (progress enabled)")
            else:
                print("✅ Test 10A5 PASSED: Progress control working (only content streamed)")
                print("   This configuration saves on LLM rephrasing costs")
        else:
            print("❌ Test 10A5 FAILED: Progress control not working as expected")

        # Print full transcript
        print("\n" + "=" * 60)
        print("📜 STREAMING TRANSCRIPT:")
        print("=" * 60)
        for i, event in enumerate(all_events, 1):
            if isinstance(event, dict):
                event_type = event.get('type', 'unknown')
                content = event.get('content', '')
                print(f"\n[Event {i}] Type: {event_type}")
                print(f"  Content: {content}")
                if 'stage' in event:
                    print(f"  Stage: {event['stage']}")
                # Mark progress events
                if event in progress_events:
                    print("  ** PROGRESS EVENT **")
                if event in content_events:
                    print("  ** CONTENT EVENT **")
            else:
                print(f"\n[Event {i}] Raw: {event}")

        print("\n" + "=" * 60)
        print(f"Summary: {len(all_events)} total events")
        print(f"  - Progress events: {len(progress_events)}")
        print(f"  - Content events: {len(content_events)}")
        print("=" * 60)

        return test_passed

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if formation:
            try:
                print("\nShutting down...")
                await formation.kill_overlord()
                formation.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    import os
    try:
        success = asyncio.run(main())
        exit_code = 0 if success else 1
    except Exception:
        exit_code = 1
    finally:
        # Force exit to prevent hanging
        os._exit(exit_code)
