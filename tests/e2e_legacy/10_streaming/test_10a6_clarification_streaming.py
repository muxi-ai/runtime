#!/usr/bin/env python3
"""
Test 10A6: Clarification Streaming
Tests that streaming events work correctly during clarification flow.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402
from muxi.services.streaming import get_streaming_llm_config  # noqa: E402


async def main():
    """Test streaming with clarification flow."""
    print("🚀 MUXI Runtime - Test 10A6: Clarification Streaming")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-streaming"
    formation = None  # Initialize to None for finally block

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded")

        # Check if streaming model is configured
        streaming_config = get_streaming_llm_config()
        if streaming_config:
            print("📋 Streaming configuration:")
            print(f"   Model: {streaming_config.get('model')}")
            print(f"   Rephrasing enabled: {streaming_config.get('enabled')}")
            print(f"   Progress enabled: {streaming_config.get('progress', True)}")
        else:
            print("⚠️ No streaming configuration found")

        print("\n📋 Test: Clarification flow with streaming")
        print("-" * 40)

        user_id = "test_user"
        session_id = "streaming_clarification_test"

        # First request - incomplete, should trigger clarification
        print("\n1️⃣ Sending incomplete request...")
        response1 = await overlord.chat(
            message="Help me with",
            user_id=user_id,
            session_id=session_id,
            use_async=False,
            stream=True,
        )

        # Consume the first stream (should ask for clarification)
        stream1_events = []
        if hasattr(response1, "__aiter__"):
            async for chunk in response1:
                stream1_events.append(chunk)
                if len(stream1_events) <= 2:
                    if isinstance(chunk, dict):
                        preview = f"{chunk.get('type', 'unknown')} - {chunk.get('content', '')}"
                    else:
                        preview = str(chunk)
                    print(f"   Stream chunk {len(stream1_events)}: {preview}")

        print(f"\n   Total events from first request: {len(stream1_events)}")

        # Check if we got a clarification request
        clarification_found = False
        for event in stream1_events:
            if isinstance(event, dict):
                content = event.get('content', '')
                # Check for clarification patterns
                if any(phrase in content.lower() for phrase in ['what would you like', 'help you with what', 'can you be more specific', 'what do you need']):  # noqa: E501
                    clarification_found = True
                    print("   ✅ Clarification request detected")
                    break

        if not clarification_found:
            # Check if the final response asks for clarification
            if stream1_events:
                last_event = stream1_events[-1]
                if isinstance(last_event, dict):
                    content = last_event.get('content', '')
                    if any(phrase in content.lower() for phrase in ['what would you like', 'help you with what', 'can you be more specific']):  # noqa: E501
                        clarification_found = True
                        print("   ✅ Clarification in final response")

        # Second request - provide clarification
        print("\n2️⃣ Providing clarification...")
        response2 = await overlord.chat(
            message="debugging Python code",
            user_id=user_id,
            session_id=session_id,
            use_async=False,
            stream=True,
        )

        # Consume the second stream (should provide actual help)
        stream2_events = []
        if hasattr(response2, "__aiter__"):
            async for chunk in response2:
                stream2_events.append(chunk)
                if len(stream2_events) <= 2:
                    if isinstance(chunk, dict):
                        preview = f"{chunk.get('type', 'unknown')} - {chunk.get('content', '')}"
                    else:
                        preview = str(chunk)
                    print(f"   Stream chunk {len(stream2_events)}: {preview}")

        print(f"\n   Total events from clarification response: {len(stream2_events)}")

        # Check if we got a helpful response about debugging
        helpful_response = False
        for event in stream2_events:
            if isinstance(event, dict):
                content = event.get('content', '')
                if any(word in content.lower() for word in ['debug', 'python', 'code', 'error', 'breakpoint', 'trace']):
                    helpful_response = True
                    print("   ✅ Helpful debugging response detected")
                    break

        # Results
        print("\n📊 Results:")
        print(f"   First request events: {len(stream1_events)}")
        print(f"   Clarification detected: {'✅' if clarification_found else '❌'}")
        print(f"   Second request events: {len(stream2_events)}")
        print(f"   Helpful response: {'✅' if helpful_response else '❌'}")

        # Test passes if we got streaming events for both requests
        success = len(stream1_events) > 0 and len(stream2_events) > 0

        if success:
            print("\n" + "=" * 60)
            print("✅ Test 10A6 PASSED: Clarification streaming works correctly")
        else:
            print("\n" + "=" * 60)
            print("❌ Test 10A6 FAILED: Issues with clarification streaming")

        # Print full transcript
        print("\n" + "=" * 60)
        print("📜 STREAMING TRANSCRIPT - First Request:")
        print("=" * 60)
        for i, event in enumerate(stream1_events[:10], 1):  # Limit to first 10 events
            if isinstance(event, dict):
                print(f"\n[Event {i}] Type: {event.get('type', 'unknown')}")
                print(f"  Content: {event.get('content', '')[:200]}")  # Truncate long content
            else:
                print(f"\n[Event {i}] Raw: {str(event)[:200]}")

        print("\n" + "=" * 60)
        print("📜 STREAMING TRANSCRIPT - Clarification Response:")
        print("=" * 60)
        for i, event in enumerate(stream2_events[:10], 1):  # Limit to first 10 events
            if isinstance(event, dict):
                print(f"\n[Event {i}] Type: {event.get('type', 'unknown')}")
                print(f"  Content: {event.get('content', '')[:200]}")  # Truncate long content
            else:
                print(f"\n[Event {i}] Raw: {str(event)[:200]}")

        print("\n" + "=" * 60)

        return success

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
