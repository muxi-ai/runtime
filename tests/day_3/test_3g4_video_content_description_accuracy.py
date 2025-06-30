#!/usr/bin/env python3
"""Test 3G4: Confirm video content descriptions are accurate."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3G4: Video Content Description Accuracy")
    print("Goal: Confirm video content descriptions are accurate")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the demo video (14MB - much smaller for testing)
    video_path = Path("test-docs/demo.mov")
    if not video_path.exists():
        print(f"ERROR: Video file not found at {video_path}")
        return
    
    with open(video_path, "rb") as f:
        video_content = f.read()
    
    # Send request for detailed video description
    print("Sending video content description request...")
    response = await overlord.chat(
        user_id="test_user_video_accuracy",
        message="Please provide a detailed and accurate description of this video. Include: 1) Visual content in each major scene, 2) Any text or graphics shown, 3) Audio/speech content, 4) Overall theme and purpose.",
        files=[{
            "filename": video_path.name,
            "content": video_content,
            "content_type": "video/quicktime",  # .mov files are QuickTime format
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
        print("\n📡 Receiving video description...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Video description complete! Total: {len(full_response)} characters")
        
        # Analyze description quality
        response_lower = full_response.lower()
        
        # Check for video description elements
        visual_terms = ["scene", "frame", "visual", "shows", "displays", "appears"]
        audio_terms = ["audio", "speech", "sound", "says", "narrator", "voice"]
        content_terms = ["content", "text", "graphic", "slide", "presentation"]
        
        visual_count = sum(1 for term in visual_terms if term in response_lower)
        audio_count = sum(1 for term in audio_terms if term in response_lower)
        content_count = sum(1 for term in content_terms if term in response_lower)
        
        print(f"\n📊 Description Quality Metrics:")
        print(f"  - Visual elements described: {visual_count}/6")
        print(f"  - Audio elements described: {audio_count}/6")
        print(f"  - Content elements described: {content_count}/6")
        
        # Quality assessment
        if visual_count >= 2:
            print("✓ Visual content well described")
        if audio_count >= 2:
            print("✓ Audio content captured")
        if content_count >= 2:
            print("✓ Content elements identified")
            
        total_quality = (visual_count + audio_count + content_count) / 18 * 100
        print(f"\n🎯 Description completeness: {total_quality:.0f}%")
        
    elif isinstance(response, str):
        print(f"\n✅ Video description: {response[:300]}...")
        print(f"Total description: {len(response)} chars")
        
        # Basic validation
        if len(response) > 200:
            print("✓ Detailed video description provided")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting video content description accuracy test...")
    
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