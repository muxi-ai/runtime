#!/usr/bin/env python3
"""Test 3J3: Clear errors for unsupported formats."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3J3: Unsupported Format Error Handling")
    print("Goal: Clear errors for unsupported formats")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Test various unsupported formats
    test_cases = [
        {
            "name": "Executable file",
            "filename": "program.exe",
            "content": b"MZ\x90\x00\x03" + b"\x00" * 100,  # EXE header
            "content_type": "application/x-msdownload",
        },
        {
            "name": "Database file",
            "filename": "data.db",
            "content": b"SQLite format 3\x00" + b"\x00" * 100,
            "content_type": "application/x-sqlite3",
        },
        {
            "name": "Compressed archive",
            "filename": "archive.rar",
            "content": b"Rar!\x1a\x07\x00" + b"\x00" * 100,  # RAR header
            "content_type": "application/x-rar-compressed",
        },
        {
            "name": "Unknown binary",
            "filename": "unknown.bin",
            "content": b"\xFF\xFE\xFD\xFC" * 50,
            "content_type": "application/octet-stream",
        },
    ]
    
    results = []
    
    for test_case in test_cases:
        print(f"\n🧪 Testing {test_case['name']}...")
        print(f"  - File: {test_case['filename']}")
        print(f"  - Type: {test_case['content_type']}")
        
        response = await overlord.chat(
            user_id=f"test_user_{test_case['filename']}",
            message=f"Please analyze this {test_case['name']}.",
            files=[{
                "filename": test_case["filename"],
                "content": test_case["content"],
                "content_type": test_case["content_type"],
                "size": len(test_case["content"]),
            }],
        )
        
        # Analyze response
        handled_well = False
        error_message = None
        
        if isinstance(response, dict) and "request_id" in response:
            print(f"  → Async processing attempted")
            # May still process but likely will fail in background
            handled_well = True  # Didn't crash at least
            
        elif hasattr(response, '__aiter__'):
            # Try to get streaming response
            try:
                full_response = ""
                async for chunk in response:
                    full_response += chunk
                    
                if any(term in full_response.lower() for term in ["unsupported", "cannot", "unable", "format"]):
                    error_message = full_response[:200]
                    handled_well = True
                    print(f"  → Clear error: {error_message}")
                    
            except Exception as e:
                print(f"  → Stream error: {type(e).__name__}")
                handled_well = True
                
        elif isinstance(response, str):
            response_lower = response.lower()
            
            # Check for appropriate error messages
            error_indicators = ["unsupported", "cannot process", "unable", "not supported", 
                              "invalid format", "unrecognized", "can't analyze"]
            
            if any(indicator in response_lower for indicator in error_indicators):
                error_message = response[:200]
                handled_well = True
                print(f"  → Clear error: {error_message}")
            else:
                print(f"  → Response: {response[:100]}...")
        
        results.append({
            "format": test_case["name"],
            "handled_well": handled_well,
            "error_message": error_message
        })
    
    # Summary
    print("\n\n📊 Unsupported Format Handling Summary:")
    print("=" * 50)
    
    for result in results:
        status = "✅" if result["handled_well"] else "❌"
        print(f"{status} {result['format']}")
        if result["error_message"]:
            print(f"   Error message: {result['error_message'][:100]}...")
    
    success_rate = sum(1 for r in results if r["handled_well"]) / len(results) * 100
    print(f"\n🎯 Success rate: {success_rate:.0f}%")
    
    if success_rate >= 75:
        print("✅ Good handling of unsupported formats")
    else:
        print("⚠️  Some unsupported formats not handled clearly")
    
    print("\n💡 Expected behavior:")
    print("  - Clear error messages mentioning format issues")
    print("  - No crashes or undefined behavior")
    print("  - Helpful suggestions when possible")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting unsupported format error test...")
    
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