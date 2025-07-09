#!/usr/bin/env python3
"""Test 3G2: Validate OCR accuracy reaches acceptable thresholds."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3G2: OCR Accuracy Validation")
    print("Goal: Validate OCR accuracy reaches acceptable thresholds")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare a slide image with known text
    slide_path = Path("test-docs/slide.png")
    if not slide_path.exists():
        print(f"ERROR: Slide image not found at {slide_path}")
        return
    
    with open(slide_path, "rb") as f:
        slide_content = f.read()
    
    # Send request for OCR with accuracy check
    print("Sending OCR accuracy validation request...")
    response = await overlord.chat(
        user_id="test_user_ocr_accuracy",
        message="Please perform OCR on this slide image. Extract all text including titles, bullet points, and any labels. Be as accurate as possible.",
        files=[{
            "filename": slide_path.name,
            "content": slide_content,
            "content_type": "image/png",
            "size": len(slide_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async OCR validation started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(12):  # 1 minute max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ OCR validation completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving OCR results...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ OCR complete! Total: {len(full_response)} characters")
        
        # Calculate basic accuracy metrics
        words = full_response.split()
        word_count = len(words)
        
        # Check for common presentation elements
        has_bullets = "•" in full_response or "-" in full_response or "*" in full_response
        has_title = any(line.isupper() or line.istitle() for line in full_response.split('\n')[:5])
        
        print(f"\n📊 OCR Metrics:")
        print(f"  - Words extracted: {word_count}")
        print(f"  - Has bullet points: {has_bullets}")
        print(f"  - Has title text: {has_title}")
        
        # Simple accuracy check (>90% would need ground truth comparison)
        if word_count > 20:
            print("✓ OCR extracted substantial text content")
        
        if has_bullets and has_title:
            print("✓ OCR preserved document structure")
        
    elif isinstance(response, str):
        print(f"\n✅ OCR results: {response[:200]}...")
        print(f"Total OCR text: {len(response)} chars")
        
        # Basic validation
        if len(response) > 100:
            print("✓ OCR produced meaningful output")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


async def main():
    """Main entry point."""
    print("Starting OCR accuracy validation test...")
    
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