#!/usr/bin/env python3
"""Test 3H2: Long audio processing uses async (>5 minutes)."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3H2: Long Audio Async Processing")
    print("Goal: Long audio processing uses async (>5 minutes)")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the long audio file
    audio_path = Path("test-docs/podcast.wav")
    if not audio_path.exists():
        print(f"ERROR: Long audio file not found at {audio_path}")
        print("Note: This test requires an audio file >5 minutes")
        return
    
    with open(audio_path, "rb") as f:
        audio_content = f.read()
    
    file_size_mb = len(audio_content) / (1024 * 1024)
    # Estimate duration based on typical WAV bitrate (assuming 44.1kHz, 16-bit stereo)
    estimated_minutes = file_size_mb / 10.5  # ~10.5 MB per minute for CD quality
    
    print(f"🎵 Long audio file size: {file_size_mb:.2f} MB")
    print(f"⏱️  Estimated duration: {estimated_minutes:.1f} minutes")
    
    if estimated_minutes < 5:
        print("⚠️  Warning: Audio may be shorter than 5 minutes")
    
    # Send request with long audio
    print("\nSending long audio for transcription...")
    response = await overlord.chat(
        user_id="test_user_long_audio",
        session_id="long_audio_session",
        message="Please transcribe this podcast episode completely. Include timestamps for major topic changes if possible.",
        files=[{
            "filename": audio_path.name,
            "content": audio_content,
            "content_type": "audio/wav",
            "size": len(audio_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async processing triggered for long audio!")
        print(f"Request ID: {response['request_id']}")
        print(f"Audio size: {file_size_mb:.2f} MB (~{estimated_minutes:.1f} minutes)")
        print("✓ Successfully triggered async mode for long audio")
        
        # Monitor async processing
        print("\n⏳ Monitoring async transcription...")
        for i in range(48):  # 4 minutes max for long audio
            await asyncio.sleep(5)
            elapsed = (i + 1) * 5
            
            if hasattr(overlord, '_background_tasks'):
                task_count = len(overlord._background_tasks)
                print(f"[{elapsed}s] Active tasks: {task_count}")
                
                if task_count == 0:
                    print("✅ Long audio transcription completed!")
                    break
            
            if elapsed % 30 == 0:
                print(f"  Still processing... ({elapsed/60:.1f} minutes elapsed)")
        
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving streaming transcription...")
        print("ℹ️  Audio processed via streaming")
        
        char_count = 0
        async for chunk in response:
            char_count += len(chunk)
            if char_count < 300:
                print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Transcribed {char_count} characters via streaming")
        
    elif isinstance(response, str):
        print(f"\n⚠️  Sync response received")
        print(f"Transcription preview: {response[:200]}...")
    
    print("\n📊 Processing Summary:")
    print(f"  - Audio size: {file_size_mb:.2f} MB")
    print(f"  - Est. duration: {estimated_minutes:.1f} minutes")
    print(f"  - Expected: Async processing for >5 minute audio")
    print(f"  - Actual: {'Async' if isinstance(response, dict) else 'Sync/Stream'} processing")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


async def main():
    """Main entry point."""
    print("Starting long audio async processing test...")
    
    try:
        await run_async_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())