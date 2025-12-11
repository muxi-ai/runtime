#!/usr/bin/env python3
"""
Test 3K7: AVChat Transcript Test
Simple test to show the actual response from avchat
"""

import asyncio
import sys
from pathlib import Path
import base64

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_3k7_transcript():
    """Test to see actual avchat response."""
    print("\n" + "=" * 80)
    print("Test 3K7: AVChat Transcript Test")
    print("=" * 80)

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()

    # Load the formation
    await formation.load(str(formation_path / "formation.afs"))
    print("\nStarting overlord...")
    overlord = await formation.start_overlord()
    print("✓ Overlord started")

    # Test with a small audio file
    audio_path = Path(__file__).parent.parent.parent / "assets/files" / "audio-request.m4a"

    if not audio_path.exists():
        print(f"❌ Audio file not found: {audio_path}")
        await formation.shutdown()
        return False

    print(f"\n📁 Using audio file: {audio_path.name}")
    print(f"   Size: {audio_path.stat().st_size / 1024:.1f} KB")

    # Read and encode the audio file
    with open(audio_path, 'rb') as f:
        audio_content = f.read()
        audio_b64 = base64.b64encode(audio_content).decode('utf-8')

    audio_file = {
        'content': audio_b64,
        'content_type': 'audio/m4a',
        'filename': 'short.m4a'
    }

    # Call avchat with timeout and force synchronous mode
    print("\n🎤 Calling avchat() with audio file...")
    print("   Generated prompt: 'Please transcribe this audio and respond to what was said.'")
    print("   Mode: Synchronous (use_async=False)")

    try:
        response = await asyncio.wait_for(
            overlord.avchat(
                files=[audio_file],
                user_id="test-user",
                session_id="test-3k7",
                use_async=False,  # Force synchronous processing
                stream=False  # Force non-streaming response
            ),
            timeout=120.0  # 120 second timeout for audio transcription
        )

        # Display the response
        print("\n" + "=" * 80)
        print("### Chat Transcript:")
        print("=" * 80)
        print("\n👤 User: [Uploaded audio file: short.m4a]")
        print("\n🤖 System Response:")
        print("-" * 40)

        if isinstance(response, dict):
            content = response.get('content', str(response))
        else:
            content = str(response)

        # Print full response
        print(content)
        print("-" * 40)

        print("\n✅ Test completed successfully!")

    except asyncio.TimeoutError:
        print("\n❌ Timeout: No response after 120 seconds")
        formation.kill_overlord()
        formation.shutdown()
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        formation.kill_overlord()
        formation.shutdown()
        return False

    # shutdown
    formation.kill_overlord()
    formation.shutdown()
    print("\n" + "=" * 80)
    return True


if __name__ == "__main__":
    result = asyncio.run(test_3k7_transcript())
    sys.exit(0 if result else 1)
