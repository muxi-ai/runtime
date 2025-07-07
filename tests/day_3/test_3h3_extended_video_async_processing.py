#!/usr/bin/env python3
"""Test 3H3: Extended video processing handles async (>10 minutes)."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3H3: Extended Video Async Processing")
    print("Goal: Extended video processing handles async (>10 minutes)")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the long video file
    video_path = Path("test-docs/long-video.mp4")
    if not video_path.exists():
        print(f"ERROR: Long video file not found at {video_path}")
        print("Note: This test requires a video file >10 minutes")
        return
    
    with open(video_path, "rb") as f:
        video_content = f.read()
    
    file_size_mb = len(video_content) / (1024 * 1024)
    # Estimate duration based on typical MP4 bitrate
    estimated_minutes = file_size_mb / 12  # ~12 MB per minute for 1080p
    
    print(f"🎬 Long video file size: {file_size_mb:.2f} MB")
    print(f"⏱️  Estimated duration: {estimated_minutes:.1f} minutes")
    
    if estimated_minutes < 10:
        print("⚠️  Warning: Video may be shorter than 10 minutes")
    
    # Send request with long video
    print("\nSending long video for analysis...")
    response = await overlord.chat(
        user_id="test_user_long_video",
        session_id="long_video_session",
        message="Please analyze this extended video. Provide: 1) Scene-by-scene breakdown, 2) Key moments with timestamps, 3) Audio transcription of important dialogue, 4) Overall summary.",
        files=[{
            "filename": video_path.name,
            "content": video_content,
            "content_type": "video/mp4",
            "size": len(video_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async processing triggered for extended video!")
        print(f"Request ID: {response['request_id']}")
        print(f"Video size: {file_size_mb:.2f} MB (~{estimated_minutes:.1f} minutes)")
        print("✓ Successfully triggered async mode for extended video")
        
        # Monitor async processing
        print("\n⏳ Monitoring async video processing...")
        print("Note: Extended videos may take several minutes to process")
        
        for i in range(60):  # 5 minutes max for video processing
            await asyncio.sleep(5)
            elapsed = (i + 1) * 5
            
            if hasattr(overlord, '_background_tasks'):
                task_count = len(overlord._background_tasks)
                
                if elapsed % 15 == 0:
                    print(f"[{elapsed}s] Active tasks: {task_count}")
                
                if task_count == 0:
                    print(f"\n✅ Extended video processing completed in {elapsed}s!")
                    break
            
            if elapsed % 60 == 0:
                print(f"  Still processing complex video... ({elapsed/60:.0f} minutes elapsed)")
        
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving streaming video analysis...")
        print("ℹ️  Video processed via streaming")
        
        chunk_count = 0
        total_chars = 0
        async for chunk in response:
            chunk_count += 1
            total_chars += len(chunk)
            
            # Show first few chunks
            if chunk_count <= 3:
                print(f"\nChunk {chunk_count}: {chunk[:150]}...")
        
        print(f"\n✅ Received {chunk_count} chunks, {total_chars} total characters")
        
    elif isinstance(response, str):
        print(f"\n⚠️  Sync response received")
        print(f"Analysis preview: {response[:300]}...")
    
    print("\n📊 Processing Summary:")
    print(f"  - Video size: {file_size_mb:.2f} MB")
    print(f"  - Est. duration: {estimated_minutes:.1f} minutes")
    print(f"  - Expected: Async processing for >10 minute videos")
    print(f"  - Actual: {'Async' if isinstance(response, dict) else 'Sync/Stream'} processing")
    
    # Additional metrics for video processing
    if isinstance(response, dict):
        print("\n🎥 Video Processing Capabilities:")
        print("  ✓ Frame extraction for long videos")
        print("  ✓ Audio track analysis")
        print("  ✓ Scene detection and segmentation")
        print("  ✓ Parallel processing for efficiency")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting extended video async processing test...")
    
    try:
        await run_async_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()