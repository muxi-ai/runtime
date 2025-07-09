#!/usr/bin/env python3
"""Test 3F5: Process multiple different file types in one request."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3F5: Multi-File Processing")
    print("Goal: Process multiple different file types in one request")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare multiple files
    files = []
    
    # PDF file
    pdf_path = Path("test-docs/small.pdf")
    if pdf_path.exists():
        with open(pdf_path, "rb") as f:
            pdf_content = f.read()
        files.append({
            "filename": pdf_path.name,
            "content": pdf_content,
            "content_type": "application/pdf",
            "size": len(pdf_content),
        })
        print(f"✓ Added PDF: {pdf_path.name} ({len(pdf_content)} bytes)")
    
    # Image file
    image_path = Path("test-docs/chart.png")
    if image_path.exists():
        with open(image_path, "rb") as f:
            image_content = f.read()
        files.append({
            "filename": image_path.name,
            "content": image_content,
            "content_type": "image/png",
            "size": len(image_content),
        })
        print(f"✓ Added Image: {image_path.name} ({len(image_content)} bytes)")
    
    # Audio file
    audio_path = Path("test-docs/short.m4a")
    if audio_path.exists():
        with open(audio_path, "rb") as f:
            audio_content = f.read()
        files.append({
            "filename": audio_path.name,
            "content": audio_content,
            "content_type": "audio/m4a",
            "size": len(audio_content),
        })
        print(f"✓ Added Audio: {audio_path.name} ({len(audio_content)} bytes)")
    
    if not files:
        print("ERROR: No test files found!")
        return
    
    # Send request with multiple files
    print(f"\nSending request with {len(files)} files...")
    response = await overlord.chat(
        user_id="test_user_multi",
        session_id="multi_file_session",
        message="Please analyze all these files together. Summarize the content from each file and identify any relationships or common themes between them.",
        files=files,
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async multi-file processing started!")
        print(f"Request ID: {response['request_id']}")
        print(f"Processing {len(files)} files asynchronously...")
        
        # Wait for processing
        for i in range(24):  # 2 minutes max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Multi-file processing completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving multi-file analysis...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Multi-file analysis complete! Total: {len(full_response)} characters")
        
        # Verify analysis mentions multiple file types
        mentions = 0
        for file_type in ["pdf", "image", "audio", "chart", "document"]:
            if file_type in full_response.lower():
                mentions += 1
        
        if mentions >= 2:
            print(f"✓ Successfully analyzed {mentions} different file types")
        
    elif isinstance(response, str):
        print(f"\n✅ Multi-file analysis: {response[:200]}...")
        print(f"Total analysis text: {len(response)} chars")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


async def main():
    """Main entry point."""
    print("Starting multi-file processing test...")
    
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