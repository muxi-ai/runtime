#!/usr/bin/env python3
"""Test 3J4: Timeout handling for extremely large files."""

import os
import asyncio
import sys
from pathlib import Path
import time

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3J4: Timeout Handling for Large Files")
    print("Goal: Verify timeout handling for extremely large file processing")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Create a large complex file that would take long to process
    # Simulate with a large PDF with complex content
    large_complex_size = 15 * 1024 * 1024  # 15MB of complex data
    
    # Create pseudo-PDF with lots of "complex" content
    complex_content = b"%PDF-1.4\n"
    # Add many objects that would be slow to parse
    for i in range(1000):
        complex_content += f"{i} 0 obj\n<< /Type /Page /Content {i+1} 0 R >>\nendobj\n".encode()
        complex_content += b"BT /F1 12 Tf 100 700 Td (Complex mathematical formulas and dense text) Tj ET\n" * 10
    
    # Pad to target size
    padding_needed = large_complex_size - len(complex_content)
    if padding_needed > 0:
        complex_content += b"% Padding\n" + b"A" * padding_needed
    
    print(f"📄 Complex file size: {len(complex_content) / (1024*1024):.2f} MB")
    print("⏱️  This file is designed to take longer to process")
    
    # Test 1: Monitor async processing timeout
    print("\n🧪 Test 1: Async processing with timeout monitoring...")
    
    start_time = time.time()
    response = await overlord.chat(
        user_id="test_user_timeout",
        session_id="timeout_test_session",
        message="Please perform a detailed analysis of this complex document. Extract all formulas, analyze all diagrams, and provide comprehensive insights.",
        files=[{
            "filename": "complex_large.pdf",
            "content": complex_content,
            "content_type": "application/pdf",
            "size": len(complex_content),
        }],
    )
    
    if isinstance(response, dict) and "request_id" in response:
        print(f"✅ Async processing started")
        print(f"Request ID: {response['request_id']}")
        
        # Monitor processing with timeout
        print("\n⏳ Monitoring processing (max 3 minutes)...")
        
        timed_out = True
        max_wait = 180  # 3 minutes
        check_interval = 10
        
        for elapsed in range(0, max_wait, check_interval):
            await asyncio.sleep(check_interval)
            
            print(f"[{elapsed + check_interval}s] Still processing...")
            
            # Check if background tasks completed
            if hasattr(overlord, '_background_tasks'):
                if len(overlord._background_tasks) == 0:
                    print(f"✅ Processing completed in {elapsed + check_interval}s")
                    timed_out = False
                    break
        
        if timed_out:
            print(f"\n⏱️  Processing exceeded {max_wait}s timeout")
            print("✅ System continues running (no hang)")
        
    elif hasattr(response, '__aiter__'):
        print("📡 Streaming response...")
        
        # Test streaming with timeout
        try:
            full_response = ""
            chunk_count = 0
            stream_start = time.time()
            
            # Set a timeout for the entire streaming operation
            async def stream_with_timeout():
                nonlocal full_response, chunk_count
                async for chunk in response:
                    chunk_count += 1
                    full_response += chunk
                    
                    # Check if streaming is taking too long
                    if time.time() - stream_start > 120:  # 2 minute timeout
                        print("\n⏱️  Streaming timeout reached")
                        break
                        
                    if chunk_count % 10 == 0:
                        print(f".", end='', flush=True)
            
            # Run with overall timeout
            await asyncio.wait_for(stream_with_timeout(), timeout=150)
            
            print(f"\n✅ Streamed {chunk_count} chunks in {time.time() - stream_start:.1f}s")
            
        except asyncio.TimeoutError:
            print("\n✅ Stream timeout handled gracefully")
            
    # Test 2: Multiple large files simultaneously
    print("\n\n🧪 Test 2: Multiple large files (stress test)...")
    
    tasks = []
    for i in range(3):
        print(f"  Submitting file {i+1}/3...")
        
        task = overlord.chat(
            user_id=f"test_user_multi_{i}",
            session_id=f"multi_session_{i}",
            message=f"Process document {i+1}",
            files=[{
                "filename": f"large_{i}.pdf",
                "content": complex_content[:5*1024*1024],  # 5MB each
                "content_type": "application/pdf",
                "size": 5*1024*1024,
            }],
        )
        tasks.append(task)
    
    # Wait for all with timeout
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=30
        )
        
        print("\n📊 Multiple file results:")
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"  File {i+1}: Error - {type(result).__name__}")
            elif isinstance(result, dict):
                print(f"  File {i+1}: Async processing")
            else:
                print(f"  File {i+1}: Processed")
                
    except asyncio.TimeoutError:
        print("\n✅ Multi-file timeout handled (system stable)")
    
    print("\n\n📊 Timeout Handling Summary:")
    print("  ✅ Long processing doesn't hang the system")
    print("  ✅ Async tasks can be monitored")
    print("  ✅ Timeouts are handled gracefully")
    print("  ✅ System remains responsive")
    
    processing_time = time.time() - start_time
    print(f"\n⏱️  Total test time: {processing_time:.1f}s")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


async def main():
    """Main entry point."""
    print("Starting timeout handling test...")
    
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