#!/usr/bin/env python3
"""Test 3F4: Extract and analyze frames from video files."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3F4: Video Frame Extraction and Analysis")
    print("Goal: Extract and analyze frames from video files")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the video file
    video_path = Path("test-docs/demo.mov")
    if not video_path.exists():
        print(f"ERROR: Video file not found at {video_path}")
        return
    
    with open(video_path, "rb") as f:
        video_content = f.read()
    
    # Send request with video file
    print("Sending video frame analysis request...")
    response = await overlord.chat(
        user_id="test_user_video",
        message="Please analyze this video. Extract key frames and describe what's happening in the video, including any text or important visual elements.",
        files=[{
            "filename": video_path.name,
            "content": video_content,
            "content_type": "video/quicktime",
            "size": len(video_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async video analysis started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(24):  # 2 minutes max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Video analysis completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving video analysis...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Video analysis complete! Total: {len(full_response)} characters")
        
        # Verify analysis includes visual elements
        if "frame" in full_response.lower() or "scene" in full_response.lower():
            print("✓ Successfully analyzed video frames")
        
    elif isinstance(response, str):
        print(f"\n✅ Video analysis: {response[:200]}...")
        print(f"Total analysis text: {len(response)} chars")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting video frame extraction test...")
    
    try:
        asyncio.run(run_async_test())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()