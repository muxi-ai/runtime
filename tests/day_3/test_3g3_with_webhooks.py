"""
Test 3G3 with Webhooks: Audio Transcription Accuracy
Validate transcription accuracy across different audio conditions with webhook support.
"""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_audio_transcription_accuracy_with_webhooks():
    """Test audio transcription accuracy validation with webhook support"""
    print("\n=== Test 3G3 with Webhooks: Audio Transcription Accuracy ===")
    
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
            user_id="test_user_transcription_accuracy",
            message="How do you validate transcription accuracy for different audio conditions: clear speech, accented speakers, multiple speakers, background noise, technical jargon, and varying audio quality?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["transcription", "accuracy", "validate", "speech", "accent", "speaker", "noise", "jargon"],
            min_keywords=4,
            min_length=150,
            test_name="Audio Transcription Accuracy"
        )
        
        print(f"Audio Transcription Accuracy Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_transcription_quality_assessment_with_webhooks():
    """Test understanding of transcription quality assessment with webhook support"""
    print("\n=== Test 3G3 with Webhooks: Transcription Quality Assessment ===")
    
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
            user_id="test_user_transcription_quality",
            message="What methods can be used to assess transcription quality: word error rate, confidence scores, speaker diarization accuracy, and timestamp precision?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["transcription", "quality", "assess", "error", "rate", "confidence", "diarization", "timestamp"],
            min_keywords=4,
            min_length=120,
            test_name="Transcription Quality Assessment"
        )
        
        print(f"Transcription Quality Assessment Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_audio_transcription_accuracy_with_webhooks()
        await test_transcription_quality_assessment_with_webhooks()
        print("\nAll audio transcription accuracy webhook tests completed!")
    
    asyncio.run(run_all_tests())