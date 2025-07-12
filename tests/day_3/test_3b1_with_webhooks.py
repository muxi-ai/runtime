"""
Test 3B1: Speech Transcription (With Webhook Verification)
Tests the system's ability to transcribe speech from audio files.
"""

import os
import sys
sys.path.insert(0, '.')

import pytest
import asyncio
from pathlib import Path

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal
from utils.webhook_test_utils import (
    setup_webhook_test,
    check_async_response_with_webhook,
)


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    # Setup webhook testing
    setup_webhook_test()
    
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    await formation.load(str(formation_path))
    
    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    overlord = await formation.start_overlord()
    yield overlord
    await formation.stop_overlord()


def test_speech_transcription_methodology_async(overlord):
    """Test comprehensive speech transcription methodology with async"""
    print("\n=== Test 3B1.1: Speech Transcription Methodology with Async/Webhook ===")
    
    # Request detailed methodology
    response = get_response(
        overlord.chat(
            user_id="test_user_speech_async",
            message=(
                "Explain in detail how modern speech transcription works in multimodal AI systems. "
                "Please cover: 1) Audio preprocessing and feature extraction (MFCC, spectrograms), "
                "2) Acoustic modeling techniques (HMM, neural networks, transformers), "
                "3) Language modeling and decoding strategies, "
                "4) Handling of accents, noise, and multiple speakers, "
                "5) Real-time vs batch processing considerations."
            ),
            use_async=True,  # Force async
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['speech', 'audio', 'transcription', 'acoustic', 'model', 'feature'],
        min_keywords=4,
        min_length=400,
        test_name="Speech Transcription Methodology"
    )


def test_long_audio_transcription_async(overlord):
    """Test long audio transcription concepts with async"""
    print("\n=== Test 3B1.2: Long Audio Transcription with Async/Webhook ===")
    
    # Request analysis of long audio
    response = get_response(
        overlord.chat(
            user_id="test_user_long_audio_async",
            message=(
                "If I gave you a 2-hour conference recording with multiple speakers, "
                "please describe the complete process for: "
                "1) Speaker diarization and identification, "
                "2) Handling overlapping speech and crosstalk, "
                "3) Maintaining context over long durations, "
                "4) Generating timestamped transcripts with speaker labels, "
                "5) Creating searchable indexes and summaries."
            ),
            use_async=True,  # Force async
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['speaker', 'transcription', 'audio', 'conference', 'diarization', 'timestamp'],
        min_keywords=3,
        min_length=300,
        test_name="Long Audio Transcription"
    )


def test_multilingual_transcription_async(overlord):
    """Test multilingual transcription concepts with async"""
    print("\n=== Test 3B1.3: Multilingual Transcription with Async/Webhook ===")
    
    # Request multilingual analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_multilingual_async",
            message=(
                "Explain how to handle multilingual speech transcription where speakers "
                "switch between languages (code-switching). Include: "
                "1) Language detection and switching mechanisms, "
                "2) Handling mixed-language sentences, "
                "3) Cultural context and idiom translation, "
                "4) Phonetic variations across languages, "
                "5) Building unified multilingual models."
            ),
            use_async=True,  # Force async
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['language', 'multilingual', 'transcription', 'speech', 'translation'],
        min_keywords=3,
        min_length=300,
        test_name="Multilingual Transcription"
    )


def test_audio_quality_analysis_async(overlord):
    """Test audio quality analysis with async"""
    print("\n=== Test 3B1.4: Audio Quality Analysis with Async/Webhook ===")
    
    # Request quality analysis methodology
    response = get_response(
        overlord.chat(
            user_id="test_user_quality_async",
            message=(
                "Describe comprehensive methods for analyzing audio quality in speech recordings: "
                "1) Signal-to-noise ratio measurement, "
                "2) Echo and reverberation detection, "
                "3) Compression artifact identification, "
                "4) Bandwidth and sampling rate analysis, "
                "5) Automatic quality scoring and enhancement recommendations."
            ),
            use_async=True,  # Force async
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['audio', 'quality', 'signal', 'noise', 'analysis'],
        min_keywords=3,
        min_length=250,
        test_name="Audio Quality Analysis"
    )


def test_transcription_memory_retention(overlord):
    """Test memory retention for transcribed content"""
    print("\n=== Test 3B1.5: Transcription Memory Retention ===")
    
    user_id = "test_user_trans_memory"
    
    # Establish transcription context
    response1 = get_response(
        overlord.chat(
            user_id=user_id,
            message=(
                "I just transcribed a critical meeting with these key points: "
                "1) Project deadline moved to March 15th, "
                "2) Budget increased by 35% to $485,000, "
                "3) Team size expanding from 12 to 18 members, "
                "4) New office location at 450 Market Street. "
                "Please remember these specific details."
            ),
            use_async=False,
        )
    )
    
    print("Transcription context established")
    
    # Test memory recall
    memory_response = get_response(
        overlord.chat(
            user_id=user_id,
            message="What were the specific details from the meeting I just transcribed?",
            use_async=False,
        )
    )
    
    print(f"Memory recall response: {memory_response[:200]}...")
    
    # Verify memory retention
    response_lower = memory_response.lower()
    
    # Check for specific details
    details_found = []
    if "march 15" in response_lower or "march" in response_lower:
        details_found.append("Deadline")
    if "485" in response_lower or "35%" in response_lower:
        details_found.append("Budget")
    if "18" in response_lower or "12" in response_lower:
        details_found.append("Team size")
    if "450" in response_lower or "market street" in response_lower:
        details_found.append("Location")
    
    print(f"Details recalled: {details_found}")
    assert len(details_found) >= 2, f"Should recall at least 2 meeting details, found: {details_found}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])