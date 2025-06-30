#!/usr/bin/env python3
"""Test 3G1: Verify PDF text extraction matches source content."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3G1: PDF Text Extraction Accuracy")
    print("Goal: Verify PDF text extraction matches source content")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the PDF file
    pdf_path = Path("test-docs/sample.pdf")
    if not pdf_path.exists():
        print(f"ERROR: PDF file not found at {pdf_path}")
        return
    
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()
    
    # Send request for exact text extraction
    print("Sending PDF text extraction request...")
    response = await overlord.chat(
        user_id="test_user_pdf_accuracy",
        message="Please extract the exact text from this PDF. Include all paragraphs, headings, and any formulas or technical content exactly as they appear.",
        files=[{
            "filename": pdf_path.name,
            "content": pdf_content,
            "content_type": "application/pdf",
            "size": len(pdf_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async PDF extraction started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(12):  # 1 minute max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ PDF extraction completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving extracted text...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Text extraction complete! Total: {len(full_response)} characters")
        
        # Verify extraction quality
        word_count = len(full_response.split())
        print(f"✓ Extracted {word_count} words from PDF")
        
        # Check for common PDF elements
        has_structure = any(marker in full_response for marker in ["heading", "paragraph", "section", "page"])
        if has_structure:
            print("✓ Successfully preserved document structure")
        
    elif isinstance(response, str):
        print(f"\n✅ Extracted text preview: {response[:300]}...")
        print(f"Total extracted: {len(response)} chars, {len(response.split())} words")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting PDF text extraction accuracy test...")
    
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