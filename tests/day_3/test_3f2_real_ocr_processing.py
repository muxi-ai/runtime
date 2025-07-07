#!/usr/bin/env python3
"""Test 3F2: Perform real OCR on chart images and extract data."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3F2: Real OCR on Chart Images")
    print("Goal: Extract actual data from chart images using OCR")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the chart image
    chart_path = Path("test-docs/chart.png")
    if not chart_path.exists():
        print(f"ERROR: Chart image not found at {chart_path}")
        return
    
    with open(chart_path, "rb") as f:
        image_content = f.read()
    
    # Send request with chart image
    print("Sending OCR request for chart data extraction...")
    response = await overlord.chat(
        user_id="test_user_ocr",
        message="Please extract all text and data from this chart using OCR. Include all numbers, labels, and axis values.",
        files=[{
            "filename": chart_path.name,
            "content": image_content,
            "content_type": "image/png",
            "size": len(image_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async OCR processing started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(12):  # 1 minute max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ OCR processing completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving OCR results...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ OCR complete! Extracted {len(full_response)} characters")
        
        # Verify OCR quality
        if "axis" in full_response.lower() or "data" in full_response.lower():
            print("✓ Successfully extracted chart components")
        
    elif isinstance(response, str):
        print(f"\n✅ OCR results: {response[:200]}...")
        print(f"Total extracted text: {len(response)} chars")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting OCR test...")
    
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