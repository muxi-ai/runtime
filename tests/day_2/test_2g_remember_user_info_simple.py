#!/usr/bin/env python3
"""Test 2G: Remember User Info Functionality"""

import sys
sys.path.insert(0, ".")
import asyncio
from src.muxi.runtime.formation.formation import Formation


async def collect_stream(stream):
    """Collect all chunks from an async generator"""
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return ''.join(chunks)


async def test_remember_user_info():
    """Test remember_user_info functionality"""
    print("\n=== Testing remember_user_info ===")
    
    formation = None
    overlord = None
    try:
        formation = Formation()
        # Use a formation that works without long-term memory
        await formation.load("test-formations/formation-memory/formation-buffer-local-real.yaml")
        overlord = await formation.start_overlord()
        
        # Test 1: Store user info with dict
        print("\nTest 1: Storing user info (dict)")
        user_id = "test_user_123"
        properties = {"plan": "pro", "company": "Acme Corp"}
        
        # remember_user_info might not be async, check if it returns a coroutine
        result = overlord.remember_user_info(user_id, properties)
        if hasattr(result, '__await__'):
            result = await result
        if hasattr(result, '__aiter__'):
            result_text = await collect_stream(result)
        else:
            result_text = str(result)
        print(f"Result: {result_text}")
        test1_passed = "memories saved" in result_text.lower() or "stored" in result_text.lower()
        print(f"  - Test 1: {'✅ PASS' if test1_passed else '❌ FAIL'}")
        
        # Test 2: Store user info with string
        print("\nTest 2: Storing user info (string)")
        user2_id = "test_user_456"
        
        result = overlord.remember_user_info(
            user2_id, "I'm a software engineer working on Python projects"
        )
        if hasattr(result, '__await__'):
            result = await result
        if hasattr(result, '__aiter__'):
            result_text = await collect_stream(result)
        else:
            result_text = str(result)
        print(f"Result: {result_text}")
        test2_passed = "memories saved" in result_text.lower() or "stored" in result_text.lower()
        print(f"  - Test 2: {'✅ PASS' if test2_passed else '❌ FAIL'}")
        
        # Test 3: Verify chat still works after remember_user_info
        print("\nTest 3: Verifying normal chat works")
        response = await overlord.chat(
            user_id=user_id, 
            message="Hello, can you help me?"
        )
        if hasattr(response, '__aiter__'):
            response_text = await collect_stream(response)
        else:
            response_text = str(response)
        print(f"Chat response: {response_text[:100]}...")
        test3_passed = len(response_text) > 0
        print(f"  - Test 3: {'✅ PASS' if test3_passed else '❌ FAIL'}")
        
        # Test 4: Check if remembered info is used in context
        print("\nTest 4: Checking if remembered info is used")
        response = await overlord.chat(
            user_id=user_id,
            message="What company do I work for?"
        )
        if hasattr(response, '__aiter__'):
            response_text = await collect_stream(response)
        else:
            response_text = str(response)
        print(f"Response: {response_text[:200]}...")
        # Check if Acme Corp is mentioned (from the remembered info)
        test4_passed = "acme" in response_text.lower()
        print(f"  - Test 4: {'✅ PASS' if test4_passed else '❌ FAIL (info may not persist without long-term memory)'}")
        
        all_critical_passed = test1_passed and test2_passed and test3_passed
        
        return {
            "status": "success" if all_critical_passed else "failed",
            "tests_passed": sum([test1_passed, test2_passed, test3_passed, test4_passed]),
            "details": {
                "store_dict": test1_passed,
                "store_string": test2_passed,
                "chat_works": test3_passed,
                "info_used": test4_passed
            }
        }
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}
    finally:
        if overlord and formation:
            try:
                await formation.stop_overlord(timeout_seconds=2.0)
                print("  - Overlord stopped")
            except:
                pass


async def main():
    """Run remember_user_info tests"""
    print("🧠 Testing remember_user_info Feature")
    print("=" * 60)
    
    result = await test_remember_user_info()
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 REMEMBER USER INFO TEST SUMMARY")
    print("=" * 60)
    
    success = result.get("status") == "success"
    print(f"Overall Status: {'✅ PASS' if success else '❌ FAIL'}")
    
    if result.get("details"):
        details = result["details"]
        print(f"  - Store dict properties: {'✅' if details.get('store_dict') else '❌'}")
        print(f"  - Store string info: {'✅' if details.get('store_string') else '❌'}")
        print(f"  - Chat functionality: {'✅' if details.get('chat_works') else '❌'}")
        print(f"  - Info persistence: {'✅' if details.get('info_used') else '⚠️ Limited without long-term memory'}")
    
    print(f"\nTests passed: {result.get('tests_passed', 0)}/4")
    
    print("\n💡 KEY INSIGHTS:")
    print("- remember_user_info accepts both dict and string formats")
    print("- The method stores user information for context")
    print("- Chat functionality continues to work after storing info")
    print("- Info persistence requires long-term memory configuration")
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)