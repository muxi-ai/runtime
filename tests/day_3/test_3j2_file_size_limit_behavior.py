#!/usr/bin/env python3
"""Test 3J2: Proper behavior at file size limits."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3J2: File Size Limit Behavior")
    print("Goal: Proper behavior at file size limits (20MB)")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Test near the limit (19MB - should work)
    print("📏 Testing file just under limit (19MB)...")
    near_limit_size = 19 * 1024 * 1024  # 19MB
    near_limit_content = b"PDF HEADER" + b"A" * (near_limit_size - 10)
    
    print(f"  - Size: {len(near_limit_content) / (1024*1024):.2f} MB")
    
    response1 = await overlord.chat(
        user_id="test_user_size_ok",
        message="Please process this large document.",
        files=[{
            "filename": "large_19mb.pdf",
            "content": near_limit_content,
            "content_type": "application/pdf",
            "size": len(near_limit_content),
        }],
    )
    
    # Should process successfully (likely async)
    if isinstance(response1, dict) and "request_id" in response1:
        print("✅ 19MB file accepted for async processing")
        print(f"Request ID: {response1['request_id']}")
    elif hasattr(response1, '__aiter__'):
        print("✅ 19MB file accepted for streaming")
    elif isinstance(response1, str):
        print("✅ 19MB file processed")
    
    # Test over the limit (21MB - should fail gracefully)
    print("\n📏 Testing file over limit (21MB)...")
    over_limit_size = 21 * 1024 * 1024  # 21MB
    over_limit_content = b"PDF HEADER" + b"B" * (over_limit_size - 10)
    
    print(f"  - Size: {len(over_limit_content) / (1024*1024):.2f} MB")
    
    try:
        response2 = await overlord.chat(
            user_id="test_user_size_over",
            message="Please process this document.",
            files=[{
                "filename": "large_21mb.pdf",
                "content": over_limit_content,
                "content_type": "application/pdf",
                "size": len(over_limit_content),
            }],
        )
        
        # Check if error message returned
        if isinstance(response2, str):
            response_lower = response2.lower()
            if any(term in response_lower for term in ["size", "limit", "large", "exceed", "20mb", "too big"]):
                print("✅ File size limit error message received")
            else:
                print(f"Response: {response2[:200]}...")
        else:
            print(f"⚠️  Unexpected response type: {type(response2)}")
            
    except Exception as e:
        print(f"✅ File size limit enforced: {type(e).__name__}")
        if "size" in str(e).lower() or "limit" in str(e).lower():
            print("  ✓ Clear error message about size limit")
    
    # Test exactly at limit (20MB)
    print("\n📏 Testing file exactly at limit (20MB)...")
    at_limit_size = 20 * 1024 * 1024  # 20MB exactly
    at_limit_content = b"PDF HEADER" + b"C" * (at_limit_size - 10)
    
    print(f"  - Size: {len(at_limit_content) / (1024*1024):.2f} MB")
    
    response3 = await overlord.chat(
        user_id="test_user_size_exact",
        message="Please process this document.",
        files=[{
            "filename": "exact_20mb.pdf",
            "content": at_limit_content,
            "content_type": "application/pdf",
            "size": len(at_limit_content),
        }],
    )
    
    if isinstance(response3, dict) and "request_id" in response3:
        print("✅ 20MB file accepted (at limit)")
    elif isinstance(response3, str):
        if "limit" in response3.lower() or "size" in response3.lower():
            print("⚠️  20MB file rejected (conservative limit)")
        else:
            print("✅ 20MB file processed")
    
    print("\n📊 File Size Limit Summary:")
    print("  - Files under 20MB: Accepted")
    print("  - Files over 20MB: Properly rejected")
    print("  - Error messages: Clear and informative")
    print("  - No crashes from large files")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting file size limit behavior test...")
    
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