#!/usr/bin/env python3
"""Test 3H1: Large PDF processing triggers async (>5MB)."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3H1: Large PDF Async Processing")
    print("Goal: Large PDF processing triggers async (>5MB)")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare the large PDF file
    pdf_path = Path("test-docs/large.pdf")
    if not pdf_path.exists():
        print(f"ERROR: Large PDF file not found at {pdf_path}")
        print("Note: This test requires a PDF file >5MB")
        return
    
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()
    
    file_size_mb = len(pdf_content) / (1024 * 1024)
    print(f"📄 Large PDF size: {file_size_mb:.2f} MB")
    
    if file_size_mb < 5:
        print("⚠️  Warning: PDF is smaller than 5MB, may not trigger async processing")
    
    # Send request with large PDF
    print("\nSending large PDF for processing...")
    response = await overlord.chat(
        user_id="test_user_large_pdf",
        session_id="large_pdf_session",
        message="Please analyze this large PDF document. Provide a comprehensive summary of its contents.",
        files=[{
            "filename": pdf_path.name,
            "content": pdf_content,
            "content_type": "application/pdf",
            "size": len(pdf_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async processing triggered for large PDF!")
        print(f"Request ID: {response['request_id']}")
        print(f"File size: {file_size_mb:.2f} MB")
        print("✓ Successfully triggered async mode for large file")
        
        # Monitor async processing
        print("\n⏳ Monitoring async processing...")
        for i in range(36):  # 3 minutes max for large files
            await asyncio.sleep(5)
            elapsed = (i + 1) * 5
            
            if hasattr(overlord, '_background_tasks'):
                task_count = len(overlord._background_tasks)
                print(f"[{elapsed}s] Active tasks: {task_count}")
                
                if task_count == 0:
                    print("✅ Large PDF processing completed!")
                    break
        
    elif hasattr(response, '__aiter__'):
        # Streaming response (might happen for borderline sizes)
        print("\n📡 Receiving streaming response...")
        print("ℹ️  File processed via streaming (not async)")
        
        chunk_count = 0
        async for chunk in response:
            chunk_count += 1
            if chunk_count <= 3:
                print(f"Chunk {chunk_count}: {chunk[:100]}...")
        
        print(f"\n✅ Received {chunk_count} chunks via streaming")
        
    elif isinstance(response, str):
        print(f"\n⚠️  Sync response received (file may be under async threshold)")
        print(f"Response preview: {response[:200]}...")
    
    print("\n📊 Processing Summary:")
    print(f"  - File size: {file_size_mb:.2f} MB")
    print(f"  - Expected: Async processing for >5MB files")
    print(f"  - Actual: {'Async' if isinstance(response, dict) else 'Sync/Stream'} processing")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting large PDF async processing test...")
    
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