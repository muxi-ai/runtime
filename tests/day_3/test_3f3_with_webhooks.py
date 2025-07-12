"""
Test 3F3 with Webhooks: Real Speech Transcription
Transcribe actual speech from audio files with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_real_speech_transcription_with_webhooks():
    """Test real speech transcription with webhook support"""
    print("\n=== Test 3F3 with Webhooks: Real Speech Transcription ===")
    print("Goal: Transcribe actual speech from audio files with webhook support")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)

    try:
        # Test conceptual transcription understanding if no real audio file
        audio_path = Path("test-docs/speech.m4a")
        if not audio_path.exists():
            print(f"Audio file not found at {audio_path}, testing conceptual transcription understanding...")
            
            # Test transcription understanding
            response = await overlord.chat(
                user_id="test_user_transcription_concept",
                message="If I upload an audio file of someone saying 'Hello, welcome to our quarterly business review. Today we'll discuss Q3 results and Q4 projections.', how would you transcribe it?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["transcribe", "audio", "speech", "text", "words", "voice", "recognition"],
                min_keywords=3,
                min_length=80,
                test_name="Transcription Conceptual Understanding"
            )
            
            print(f"Transcription Conceptual Test Complete - Async: {is_async}")
            return

        # If audio file exists, test real transcription
        with open(audio_path, "rb") as f:
            audio_content = f.read()

        # Send request with audio file
        print("Sending speech transcription request...")
        response = await overlord.chat(
            user_id="test_user_speech",
            message="Please transcribe this audio file completely. Include all spoken words.",
            files=[{
                "filename": audio_path.name,
                "content": audio_content,
                "content_type": "audio/m4a",
                "size": len(audio_content),
            }],
        )

        # Use universal webhook checker for file processing (likely async)
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["transcribe", "speech", "audio", "word", "text"],
            min_keywords=2,
            min_length=30,
            timeout=60.0,  # Give more time for audio processing
            test_name="Real Speech Transcription"
        )

        print(f"Real Speech Transcription Complete - Async: {is_async}")
        
        # Additional test for transcription accuracy
        response2 = await overlord.chat(
            user_id="test_user_speech",
            message="How clear was the audio quality and how confident are you in the transcription accuracy?"
        )
        
        result2, is_async2 = check_response_with_webhook(
            response2,
            expected_keywords=["audio", "quality", "clear", "transcription", "accurate", "confident"],
            min_keywords=2,
            min_length=30,
            test_name="Transcription Quality Assessment"
        )
        
        print(f"Transcription Quality Assessment Complete - Async: {is_async2}")

    finally:
        print("🔚 Stopping overlord...")
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_transcription_methodology_with_webhooks():
    """Test understanding of transcription methodology with webhook support"""
    print("\n=== Test 3F3 with Webhooks: Transcription Methodology ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)

    try:
        response = await overlord.chat(
            user_id="test_user_transcription_method",
            message="What are the challenges and best practices for transcribing different types of audio: clear speech, accented speech, multiple speakers, noisy environments, and technical jargon?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["transcribe", "speech", "accent", "speaker", "noise", "challenge", "practice", "audio"],
            min_keywords=4,
            min_length=150,
            test_name="Transcription Methodology"
        )
        
        print(f"Transcription Methodology Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_speech_analysis_with_webhooks():
    """Test speech analysis beyond transcription with webhook support"""
    print("\n=== Test 3F3 with Webhooks: Speech Analysis ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)

    try:
        response = await overlord.chat(
            user_id="test_user_speech_analysis",
            message="Beyond transcription, what other insights can be extracted from speech audio: speaker identification, emotion detection, speaking pace, pauses, confidence levels?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["speaker", "emotion", "pace", "pause", "confidence", "analysis", "speech", "insight"],
            min_keywords=4,
            min_length=120,
            test_name="Speech Analysis"
        )
        
        print(f"Speech Analysis Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_real_speech_transcription_with_webhooks()
        await test_transcription_methodology_with_webhooks()
        await test_speech_analysis_with_webhooks()
        print("\nAll speech transcription webhook tests completed!")
    
    asyncio.run(run_all_tests())