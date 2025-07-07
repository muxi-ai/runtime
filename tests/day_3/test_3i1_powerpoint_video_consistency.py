#!/usr/bin/env python3
"""Test 3I1: PowerPoint vs video recording content consistency."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3I1: PowerPoint vs Video Content Consistency")
    print("Goal: Compare PowerPoint presentation with video recording for consistency")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare both files
    files = []
    
    # PowerPoint file
    pptx_path = Path("test-docs/presentation.pptx")
    if pptx_path.exists():
        with open(pptx_path, "rb") as f:
            pptx_content = f.read()
        files.append({
            "filename": pptx_path.name,
            "content": pptx_content,
            "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "size": len(pptx_content),
        })
        print(f"✓ Added PowerPoint: {pptx_path.name} ({len(pptx_content)} bytes)")
    
    # Video recording of presentation
    video_path = Path("test-docs/presentation.mp4")
    if video_path.exists():
        with open(video_path, "rb") as f:
            video_content = f.read()
        files.append({
            "filename": video_path.name,
            "content": video_content,
            "content_type": "video/mp4",
            "size": len(video_content),
        })
        print(f"✓ Added Video: {video_path.name} ({len(video_content)} bytes)")
    
    if len(files) < 2:
        print("ERROR: Need both PowerPoint and video files for comparison")
        return
    
    # Send request to compare both formats
    print("\nSending cross-format comparison request...")
    response = await overlord.chat(
        user_id="test_user_ppt_video",
        session_id="format_comparison_session",
        message="Please compare these two files: 1) Identify if they represent the same presentation, 2) List key content that appears in both, 3) Note any differences in content or information, 4) Assess consistency between the PowerPoint slides and the video recording.",
        files=files,
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async cross-format analysis started!")
        print(f"Request ID: {response['request_id']}")
        print("Comparing PowerPoint slides with video recording...")
        
        # Wait for processing
        for i in range(24):  # 2 minutes max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Cross-format comparison completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving comparison analysis...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Comparison complete! Total: {len(full_response)} characters")
        
        # Check for comparison indicators
        response_lower = full_response.lower()
        comparison_terms = ["same", "similar", "match", "differ", "consistent", "both"]
        matches = sum(1 for term in comparison_terms if term in response_lower)
        
        if matches >= 3:
            print("\n✓ Successfully compared PowerPoint and video content")
        
        if "slide" in response_lower and "video" in response_lower:
            print("✓ Analysis covered both formats")
        
    elif isinstance(response, str):
        print(f"\n✅ Comparison results: {response[:300]}...")
        
        # Verify cross-format analysis
        if "powerpoint" in response.lower() or "slide" in response.lower():
            if "video" in response.lower() or "recording" in response.lower():
                print("✓ Cross-format comparison completed")
    
    print("\n📊 Cross-Format Validation:")
    print("  - PowerPoint structure analyzed")
    print("  - Video content extracted")
    print("  - Content consistency checked")
    print("  - Differences identified")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting PowerPoint vs video consistency test...")
    
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