#!/usr/bin/env python3
"""
Test 10A4: Streaming Control
Tests that streaming can be enabled/disabled via the stream parameter.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test streaming control with stream parameter."""
    print("🚀 MUXI Runtime - Test 10A4: Streaming Control")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-streaming"
    formation = None  # Initialize to None for finally block

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded")
        print("\n📋 Test: Streaming Enable/Disable Control")
        print("-" * 40)

        user_id = "test_user"
        session_id = "control_test_10a4"

        # Test 1: Streaming disabled (stream=False)
        print("\n1️⃣ Testing with stream=False")

        response_no_stream = await overlord.chat(
            message="What is the capital of France?",
            user_id=user_id,
            session_id=session_id + "_no_stream",
            stream=False,  # Explicitly disable streaming
        )

        # Check response type
        if hasattr(response_no_stream, "__aiter__"):
            print("   ❌ Got streaming response when stream=False")
            test1_passed = False
        else:
            print("   ✅ Got non-streaming response when stream=False")
            test1_passed = True

            # Show response content
            if hasattr(response_no_stream, "content"):
                content = response_no_stream.content
                print("   Response type: Object with 'content' attribute")
            else:
                content = str(response_no_stream)
                print("   Response type: String")

            preview = content[:100] if len(content) > 100 else content
            print(f"   Content: {preview}...")

            # Verify it contains the answer
            if "paris" in content.lower():
                print("   ✅ Response contains correct answer")

        # Test 2: Streaming enabled (stream=True)
        print("\n2️⃣ Testing with stream=True")

        response_stream = await overlord.chat(
            message="What is the capital of Germany?",
            user_id=user_id,
            session_id=session_id + "_stream",
            stream=True,  # Explicitly enable streaming
        )

        # Check response type
        if hasattr(response_stream, "__aiter__"):
            print("   ✅ Got streaming response when stream=True")
            test2_passed = True

            # Consume the stream
            chunks = []
            async for chunk in response_stream:
                chunks.append(chunk)

            print(f"   Received {len(chunks)} chunks")

            # Extract content from dict events
            contents = []
            for chunk in chunks:
                if isinstance(chunk, dict):
                    contents.append(chunk.get('content', ''))
                else:
                    contents.append(str(chunk))

            # Verify content
            full_response = " ".join(contents)
            if "berlin" in full_response.lower():
                print("   ✅ Streamed response contains correct answer")

            # Show first chunk as sample
            if chunks:
                if isinstance(chunks[0], dict):
                    preview = f"{chunks[0].get('type', 'unknown')} - {chunks[0].get('content', '')[:100]}"
                else:
                    preview = str(chunks[0])[:100]
                print(f"   First chunk: {preview}")
        else:
            print("   ❌ Got non-streaming response when stream=True")
            test2_passed = False

        # Test 3: Default behavior (no stream parameter)
        print("\n3️⃣ Testing default behavior (no stream parameter)")

        response_default = await overlord.chat(
            message="What is the capital of Spain?",
            user_id=user_id,
            session_id=session_id + "_default",
            # No stream parameter - use formation default
        )

        # Check what we got (depends on formation config)
        if hasattr(response_default, "__aiter__"):
            print("   ℹ️ Default behavior: Streaming enabled")
            chunks = []
            async for chunk in response_default:
                chunks.append(chunk)
            # Extract content from dict events
            contents = []
            for chunk in chunks:
                if isinstance(chunk, dict):
                    contents.append(chunk.get('content', ''))
                else:
                    contents.append(str(chunk))
            full_response = " ".join(contents)
        else:
            print("   ℹ️ Default behavior: Streaming disabled")
            if hasattr(response_default, "content"):
                full_response = response_default.content
            else:
                full_response = str(response_default)

        if "madrid" in full_response.lower():
            print("   ✅ Default response contains correct answer")

        # Results summary
        print("\n" + "=" * 60)

        if test1_passed and test2_passed:
            print("✅ Test 10A4 PASSED: Streaming control works correctly")
            print("   • stream=False produces non-streaming response")
            print("   • stream=True produces streaming response")

            # Print streaming transcript (only if we got streaming chunks)
            if 'chunks' in locals() and chunks:
                print("\n" + "=" * 60)
                print("📜 STREAMING TRANSCRIPT (stream=True test):")
                print("=" * 60)
                for i, event in enumerate(chunks, 1):
                    if isinstance(event, dict):
                        print(f"\n[Event {i}] Type: {event.get('type', 'unknown')}")
                        print(f"  Content: {event.get('content', '')}")
                        if 'stage' in event:
                            print(f"  Stage: {event['stage']}")
                    else:
                        print(f"\n[Event {i}] Raw: {event}")
                print("\n" + "=" * 60)

            return True
        else:
            print("❌ Test 10A4 FAILED: Issues with streaming control")
            if not test1_passed:
                print("   • stream=False not working correctly")
            if not test2_passed:
                print("   • stream=True not working correctly")
            return False

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
