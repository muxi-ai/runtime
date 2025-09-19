"""
Test 3B1: Speech Transcription - Speech to Text Conversion
Sync version using audio files from tests/assets/files
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_speech_to_text():
    """Test speech transcription capabilities"""
    print("\n=== Test 3B1: Speech to Text Conversion ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read audio file from tests/assets/files
    audio_path = Path(__file__).parent.parent.parent / "assets/files" / "speech.m4a"
    with open(audio_path, "rb") as f:
        audio_content = f.read()

    print(f"✓ Loaded audio file: {len(audio_content)} bytes")

    files = [{
        "filename": "speech.m4a",
        "content": audio_content,
        "content_type": "audio/m4a",
        "size": len(audio_content)
    }]

    # Test speech transcription
    print("\n🎤 Testing speech transcription...")
    response = await overlord.chat(
        user_id="test_user",
        message="Please transcribe this audio file",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify transcription response
    result_lower = result.lower()
    expected_keywords = ["transcription", "audio", "speech", "text", "content"]
    found_keywords = [kw for kw in expected_keywords if kw in result_lower]

    assert len(found_keywords) >= 2, \
        f"Expected at least 2 keywords from {expected_keywords}, found: {found_keywords}"
    assert len(result) > 50, "Transcription should be substantial"

    print(f"✅ Found keywords: {found_keywords}")
    print("✅ Speech transcription test passed!")

    # Cleanup
    await formation.stop_overlord()


async def test_meeting_transcription():
    """Test meeting audio transcription"""
    print("\n=== Test 3B1.2: Meeting Transcription ===")

    # Load formation
    formation_path = Path(__file__).parent / "formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    print("✓ Overlord started")

    # Read meeting audio from tests/assets/files
    audio_path = Path(__file__).parent.parent.parent / "assets/files" / "meeting.mp3"
    with open(audio_path, "rb") as f:
        audio_content = f.read()

    print(f"✓ Loaded meeting audio: {len(audio_content)} bytes")

    files = [{
        "filename": "meeting.mp3",
        "content": audio_content,
        "content_type": "audio/mp3",
        "size": len(audio_content)
    }]

    # Test meeting transcription with summary
    print("\n🎤 Testing meeting transcription with summary...")
    response = await overlord.chat(
        user_id="test_user",
        message="Transcribe this meeting audio and provide a summary of key points discussed",
        files=files,
        use_async=False,
        stream=False,
    )

    result = response.content if hasattr(response, 'content') else str(response)
    print(f"📄 Response length: {len(result)} chars")
    print(f"📄 Response preview: {result[:200]}...")

    # Verify meeting analysis
    result_lower = result.lower()
    expected_keywords = ["meeting", "discuss", "point", "summary", "transcription"]
    found_keywords = [kw for kw in expected_keywords if kw in result_lower]

    assert len(found_keywords) >= 2, \
        f"Expected at least 2 keywords from {expected_keywords}, found: {found_keywords}"

    print(f"✅ Found keywords: {found_keywords}")
    print("✅ Meeting transcription test passed!")

    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Running Test 3B1: Speech Transcription (Sync Mode)")
    print("=" * 60)

    # Run tests sequentially
    asyncio.run(test_speech_to_text())
    print("\n" + "="*60 + "\n")

    asyncio.run(test_meeting_transcription())

    print("\n🎉 All Test 3B1 tests completed successfully!")
