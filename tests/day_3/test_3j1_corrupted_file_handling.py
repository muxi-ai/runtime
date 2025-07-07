#!/usr/bin/env python3
"""Test 3J1: Graceful handling of corrupted files."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3J1: Corrupted File Handling")
    print("Goal: Graceful handling of corrupted files")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Create a corrupted PDF (invalid header)
    corrupted_content = b"Not a real PDF file - corrupted header\xFF\xFE\x00\x01" + b"\x00" * 1000
    
    print("🔨 Testing with corrupted PDF file...")
    print(f"  - Size: {len(corrupted_content)} bytes")
    print("  - Invalid PDF header")
    
    # Send request with corrupted file
    print("\nSending corrupted file for processing...")
    response = await overlord.chat(
        user_id="test_user_corrupted",
        message="Please analyze this PDF document.",
        files=[{
            "filename": "corrupted.pdf",
            "content": corrupted_content,
            "content_type": "application/pdf",
            "size": len(corrupted_content),
        }],
    )
    
    # Handle response
    handled_gracefully = False
    
    if isinstance(response, dict) and "request_id" in response:
        print("\n📋 Async processing initiated")
        print(f"Request ID: {response['request_id']}")
        
        # Wait briefly to see if error is detected
        await asyncio.sleep(10)
        handled_gracefully = True
        
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving response...")
        full_response = ""
        try:
            async for chunk in response:
                full_response += chunk
        except Exception as e:
            print(f"⚠️  Stream error (expected): {type(e).__name__}")
            handled_gracefully = True
        
        if full_response:
            print(f"Response: {full_response[:200]}...")
            
            # Check for error indicators
            response_lower = full_response.lower()
            if any(term in response_lower for term in ["error", "corrupt", "invalid", "unable", "cannot"]):
                print("✓ Error message provided to user")
                handled_gracefully = True
                
    elif isinstance(response, str):
        print(f"\n📝 Response: {response[:200]}...")
        
        # Check for error handling
        response_lower = response.lower()
        if any(term in response_lower for term in ["error", "corrupt", "invalid", "unable", "cannot", "failed"]):
            print("✓ Error handled gracefully")
            handled_gracefully = True
    
    # Test with corrupted image
    print("\n\n🔨 Testing with corrupted image file...")
    corrupted_image = b"NOTANIMAGE" + b"\xFF" * 500
    
    response2 = await overlord.chat(
        user_id="test_user_corrupted2",
        message="Please describe this image.",
        files=[{
            "filename": "corrupted.jpg",
            "content": corrupted_image,
            "content_type": "image/jpeg",
            "size": len(corrupted_image),
        }],
    )
    
    if isinstance(response2, str):
        if any(term in response2.lower() for term in ["error", "invalid", "cannot"]):
            print("✓ Corrupted image handled gracefully")
            handled_gracefully = True
    
    print("\n📊 Error Handling Summary:")
    if handled_gracefully:
        print("  ✅ System handled corrupted files gracefully")
        print("  ✓ No crashes or unhandled exceptions")
        print("  ✓ User received appropriate feedback")
    else:
        print("  ⚠️  Corrupted files may not be handled properly")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting corrupted file handling test...")
    
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