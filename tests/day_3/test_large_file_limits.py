"""
Test Large File API Limits - Verify known limits are hit
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.muxi.runtime.formation.formation import Formation


async def test_large_audio_file():
    """Test large audio file that should hit OpenAI 25MB limit"""
    print("\n=== Testing Large Audio File (43MB WAV) ===")
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("✓ Overlord started")
    
    # Read the large audio file
    audio_path = Path(__file__).parent.parent.parent / "test-docs" / "podcast.wav"
    with open(audio_path, "rb") as f:
        audio_content = f.read()
    
    print(f"✓ Loaded large audio file: {len(audio_content):,} bytes ({len(audio_content)/1024/1024:.1f}MB)")
    
    files = [{
        "filename": "podcast.wav",
        "content": audio_content,
        "content_type": "audio/wav",
        "size": len(audio_content)
    }]
    
    print("\n🎤 Testing large audio transcription...")
    try:
        response = await overlord.chat(
            user_id="test_user",
            message="Transcribe this audio file",
            files=files,
            use_async=False,
            stream=False,
        )
        
        result = response.content if hasattr(response, 'content') else str(response)
        print(f"📄 Response: {result[:200]}...")
        print("❌ UNEXPECTED: Large audio file was processed successfully!")
        
    except Exception as e:
        print(f"✅ EXPECTED ERROR: {type(e).__name__}: {str(e)}")
    
    # Cleanup
    await formation.stop_overlord()


async def test_large_video_file():
    """Test large video file that should hit API limits"""
    print("\n=== Testing Large Video File (127MB MP4) ===")
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("✓ Overlord started")
    
    # Read the large video file
    video_path = Path(__file__).parent.parent.parent / "test-docs" / "presentation.mp4"
    with open(video_path, "rb") as f:
        video_content = f.read()
    
    print(f"✓ Loaded large video file: {len(video_content):,} bytes ({len(video_content)/1024/1024:.1f}MB)")
    
    files = [{
        "filename": "presentation.mp4",
        "content": video_content,
        "content_type": "video/mp4",
        "size": len(video_content)
    }]
    
    print("\n🎥 Testing large video analysis...")
    try:
        response = await overlord.chat(
            user_id="test_user",
            message="Analyze this video presentation",
            files=files,
            use_async=False,
            stream=False,
        )
        
        result = response.content if hasattr(response, 'content') else str(response)
        print(f"📄 Response: {result[:200]}...")
        print("⚠️  Large video file was processed - check if this hits limits")
        
    except Exception as e:
        print(f"✅ EXPECTED ERROR: {type(e).__name__}: {str(e)}")
    
    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    print("🧪 Testing Large File API Limits")
    print("=" * 60)
    
    # Run tests sequentially
    asyncio.run(test_large_audio_file())
    print("\n" + "="*60 + "\n")
    
    asyncio.run(test_large_video_file())
    
    print("\n🎯 Large file limit testing completed!")