#!/usr/bin/env python3
"""
Test 10A1: Basic Streaming
Tests that streaming events are properly emitted for simple requests.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402
from muxi.services.streaming import get_streaming_llm_config  # noqa: E402


async def main():
    """Test basic streaming functionality."""
    print("🚀 MUXI Runtime - Test 10A1: Basic Streaming")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-streaming"

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

        print("\n📋 Test: Simple request with streaming enabled")
        print("-" * 40)

        user_id = "test_user"
        session_id = "streaming_test_10a1"

        # Make a request with streaming enabled
        response = await overlord.chat(
            message="What are the key principles of quantum computing?",
            user_id=user_id,
            session_id=session_id,
            stream=True,  # Enable streaming
        )

        # Consume the stream
        stream_events = []
        if hasattr(response, "__aiter__"):
            async for chunk in response:
                stream_events.append(chunk)
                # Print first few chunks
                if len(stream_events) <= 3:
                    # Handle dict events
                    if isinstance(chunk, dict):
                        preview = f"{chunk.get('type', 'unknown')} - {chunk.get('content', '')[:100]}"
                    else:
                        preview = str(chunk)[:100]
                    print(f"   Stream chunk {len(stream_events)}: {preview}")

        # Results
        print("\n📊 Results:")
        if stream_events:
            print(f"   ✅ Received {len(stream_events)} streaming chunks")

            # Check content quality
            # Extract content from dict events
            contents = []
            for event in stream_events:
                if isinstance(event, dict):
                    contents.append(event.get('content', ''))
                else:
                    contents.append(str(event))

            full_response = " ".join(contents)
            if "quantum" in full_response.lower() or "processing" in full_response.lower():
                print("   ✅ Response contains relevant content")
            else:
                print("   ⚠️ Response may not contain expected content")

            print(f"   Total response length: {len(full_response)} characters")
        else:
            print("   ❌ No streaming chunks received")
            return False

        print("\n" + "=" * 60)
        print("✅ Test 10A1 PASSED: Basic streaming works correctly")
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
