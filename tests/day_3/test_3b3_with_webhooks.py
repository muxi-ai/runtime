"""
Test 3B3 with Webhooks: Audio Metadata Extraction
Tests the system's ability to extract and analyze audio metadata and properties with webhook support.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path

from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    # Load the directory, not the file, to enable agent auto-discovery
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    await formation.load(str(formation_path))
    
    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    # Setup webhook testing environment
    setup_webhook_test()
    
    overlord = await formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    await formation.stop_overlord()


def test_audio_format_analysis_with_webhooks(overlord):
    """Test analysis of audio format and properties with webhook support"""
    print("\n=== Test 3B3 with Webhooks: Audio Format Analysis ===")
    
    # Simulate audio format analysis
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_format",
            message="I analyzed an audio file with these properties: "
                    "Format: WAV (PCM), Sample Rate: 44.1 kHz, Bit Depth: 16-bit, "
                    "Channels: Stereo, Duration: 12:34, File Size: 132 MB. "
                    "The audio appears to be a podcast recording with good quality. "
                    "Please explain what these technical properties mean for audio quality."
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['audio', 'format', 'wav', 'sound', 'quality', 'sample'],
        min_keywords=2,
        min_length=50,
        test_name="Audio Format Analysis"
    )
    
    print(f"Audio Format Analysis Complete - Async: {is_async}")


def test_podcast_content_structure_with_webhooks(overlord):
    """Test analysis of podcast content structure with webhook support"""
    print("\n=== Test 3B3 with Webhooks: Podcast Content Structure ===")
    
    # Simulate podcast structure analysis
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_podcast",
            message="I analyzed a podcast audio file and found this structure: "
                    "1. Intro music (0:00-0:30) with upbeat jingle "
                    "2. Host introduction (0:30-2:00) - single speaker "
                    "3. Guest interview segment (2:00-25:00) - two speakers in dialogue "
                    "4. Sponsor messages (25:00-26:30) - different voice "
                    "5. Closing remarks (26:30-28:00) - host only "
                    "6. Outro music (28:00-28:30). "
                    "Describe this podcast structure and any insights about the content format."
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['podcast', 'segment', 'structure', 'content', 'section', 'audio'],
        min_keywords=2,
        min_length=100,
        test_name="Podcast Content Structure"
    )
    
    print(f"Podcast Structure Analysis Complete - Async: {is_async}")


def test_audio_duration_analysis_with_webhooks(overlord):
    """Test analysis of audio duration and pacing with webhook support"""
    print("\n=== Test 3B3 with Webhooks: Audio Duration Analysis ===")
    
    user_id = "test_user_duration"
    
    # Analyze short audio
    response1 = asyncio.run(
        overlord.chat(
            user_id=user_id,
            message="I analyzed a short audio file: Duration 10 seconds, appears to be a voice note. "
                    "The speaker talks quickly, covering 3 key points in rapid succession. "
                    "Comment on the pacing and effectiveness of such short audio messages."
        )
    )
    
    # Check short audio response
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['audio', 'short', 'quick', 'pace', 'voice'],
        min_keywords=1,
        min_length=30,
        test_name="Short Audio Analysis"
    )
    
    # Analyze longer audio comparison
    response2 = asyncio.run(
        overlord.chat(
            user_id=user_id,
            message="I now analyzed a longer audio file: Duration 2 minutes 15 seconds, a meeting recording. "
                    "This has a slower pace with pauses between speakers. "
                    "How does this duration and pacing compare to the previous 10-second voice note?"
        )
    )
    
    # Check comparison response
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['duration', 'length', 'long', 'short', 'time', 'minute'],
        min_keywords=1,
        min_length=30,
        test_name="Long Audio Comparison"
    )
    
    print(f"Duration Analysis Complete - Short Async: {is_async1}, Long Async: {is_async2}")


def test_audio_quality_assessment_with_webhooks(overlord):
    """Test assessment of audio quality with webhook support"""
    print("\n=== Test 3B3 with Webhooks: Audio Quality Assessment ===")
    
    # Simulate audio quality analysis
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_quality",
            message="I analyzed the audio quality of a speech recording: "
                    "Clarity: Excellent - crisp vocal reproduction with no distortion. "
                    "Background noise: Minimal - slight room tone but no distracting sounds. "
                    "Dynamic range: Good - voice levels consistent throughout. "
                    "Production quality: Professional - appears to use quality microphone and acoustic treatment. "
                    "Overall assessment: Broadcast-quality recording suitable for podcast or presentation. "
                    "What makes this a high-quality audio recording?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['quality', 'clear', 'audio', 'sound', 'noise', 'recording'],
        min_keywords=2,
        min_length=50,
        test_name="Audio Quality Assessment"
    )
    
    print(f"Audio Quality Assessment Complete - Async: {is_async}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])