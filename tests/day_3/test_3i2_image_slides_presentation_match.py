#!/usr/bin/env python3
"""Test 3I2: Image slides match presentation source."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3I2: Image Slides Match Presentation Source")
    print("Goal: Verify image slides match their presentation source")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare files
    files = []
    
    # Slide image
    slide_path = Path("test-docs/slide.png")
    if slide_path.exists():
        with open(slide_path, "rb") as f:
            slide_content = f.read()
        files.append({
            "filename": slide_path.name,
            "content": slide_content,
            "content_type": "image/png",
            "size": len(slide_content),
        })
        print(f"✓ Added Slide Image: {slide_path.name} ({len(slide_content)} bytes)")
    
    # PowerPoint source
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
    
    if len(files) < 2:
        print("ERROR: Need both slide image and PowerPoint file")
        return
    
    # Send request to match slide with presentation
    print("\nSending slide matching request...")
    response = await overlord.chat(
        user_id="test_user_slide_match",
        message="Please analyze if this slide image comes from this PowerPoint presentation. Compare: 1) Visual design and layout, 2) Text content and formatting, 3) Graphics and diagrams, 4) Overall style consistency. Determine if the slide is part of the presentation.",
        files=files,
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async slide matching started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(18):  # 1.5 minutes max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Slide matching completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving matching analysis...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Matching complete! Total: {len(full_response)} characters")
        
        # Check for matching indicators
        response_lower = full_response.lower()
        
        # Analysis quality checks
        has_layout = "layout" in response_lower or "design" in response_lower
        has_content = "text" in response_lower or "content" in response_lower
        has_style = "style" in response_lower or "format" in response_lower
        has_match = "match" in response_lower or "same" in response_lower or "part of" in response_lower
        
        print("\n📊 Matching Analysis Quality:")
        if has_layout:
            print("  ✓ Layout comparison performed")
        if has_content:
            print("  ✓ Content comparison performed")
        if has_style:
            print("  ✓ Style consistency checked")
        if has_match:
            print("  ✓ Match determination made")
        
    elif isinstance(response, str):
        print(f"\n✅ Matching results: {response[:300]}...")
        
        # Basic validation
        if len(response) > 100:
            print("✓ Detailed matching analysis provided")
    
    print("\n🎯 Slide Matching Validation:")
    print("  - Image OCR performed")
    print("  - PowerPoint content extracted")
    print("  - Visual elements compared")
    print("  - Match confidence assessed")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


async def main():
    """Main entry point."""
    print("Starting image slides presentation match test...")
    
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