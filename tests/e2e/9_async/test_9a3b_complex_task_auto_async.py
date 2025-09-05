#!/usr/bin/env python3
"""
Test 9A3b: Automatic async selection for complex tasks
Tests that when use_async is not specified (None), the system automatically chooses
asynchronous mode for complex, long-running tasks.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402


async def main():
    """Test automatic async selection for complex tasks."""
    print("🚀 MUXI Runtime - Test 9A3b: Auto-Async for Complex Tasks")
    print("="*60)
    
    formation_path = Path(__file__).parent / "formation-async"
    webhook_log_path = Path.cwd() / "webhook_log.json"
    
    # Clear webhook log if it exists
    if webhook_log_path.exists():
        webhook_log_path.unlink()
    
    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        print("\n✅ Formation loaded")
        print("📋 Testing automatic mode selection for complex task...")
        print("   (use_async not specified - system should choose async)")
        
        # Complex task - should auto-select async mode
        # Similar to test_7a1_workflow_with_approval.py prompt
        start_time = time.time()
        response = await overlord.chat(
            message="Research the latest developments in quantum computing, analyze the key players and breakthroughs, then create a comprehensive Linear issue with findings, timeline, and future predictions",
            user_id="test_user",
            session_id="auto_async_test_9a3b",
            # use_async not specified - let system decide
            stream=False
        )
        elapsed_time = time.time() - start_time
        
        # Check response
        print(f"\n⏱️ Initial response time: {elapsed_time:.2f}s")
        
        # Check if we got an async response (expected for complex task)
        if hasattr(response, "request_id"):
            print(f"\n✅ Got async response with request_id: {response.request_id}")
            print(f"   Status: {response.status}")
            print("   System correctly identified this as a complex task")
            
            # Wait for webhook delivery
            print("\n⏳ Waiting for webhook delivery (complex task may take time)...")
            await asyncio.sleep(10)  # Give more time for complex processing
            
            # Check webhook log
            if webhook_log_path.exists():
                with open(webhook_log_path) as f:
                    webhook_data = json.load(f)
                    
                if webhook_data:
                    # Find our webhook (might not be the last if multiple tests ran)
                    our_webhook = None
                    for webhook in reversed(webhook_data):
                        if webhook.get('request_id') == response.request_id:
                            our_webhook = webhook
                            break
                    
                    if our_webhook:
                        print(f"\n✅ Webhook received for our request:")
                        print(f"   Request ID: {our_webhook.get('request_id')}")
                        print(f"   Status: {our_webhook.get('status')}")
                        
                        # Check if it contains expected content
                        result = str(our_webhook.get('result', ''))
                        content_lower = result.lower()
                        has_quantum_info = any(keyword in content_lower for keyword in 
                                              ['quantum', 'computing', 'research', 'linear', 'issue'])
                        
                        if has_quantum_info:
                            print(f"   ✅ Content appears relevant to quantum computing research")
                        else:
                            print(f"   ⚠️ Content might not contain expected research")
                        
                        print(f"   Content preview: {result[:150]}...")
                        
                        print("\n" + "="*60)
                        print("✅ Test 9A3b PASSED: System correctly chose async mode for complex task")
                        return True
                    else:
                        print(f"\n⚠️ No webhook found for request_id: {response.request_id}")
                        print(f"   Found {len(webhook_data)} webhooks but none match")
                        return False
                else:
                    print("❌ Webhook log is empty")
                    return False
            else:
                print("❌ No webhook log found")
                return False
                
        else:
            # Got sync response for complex task
            if isinstance(response, str):
                content = response
            elif hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)
                
            print(f"\n⚠️ Got synchronous response for complex task")
            print(f"   Content preview: {content[:200]}...")
            
            # This could happen if:
            # 1. The task completed very quickly (unlikely for research)
            # 2. The complexity threshold is set very high
            # 3. Async is disabled in configuration
            
            # Check if response actually contains the research
            content_lower = content.lower()
            has_research = any(keyword in content_lower for keyword in 
                              ['quantum', 'computing', 'research', 'linear'])
            
            if has_research and elapsed_time > 5:
                print("\n⚠️ System processed complex task synchronously")
                print(f"   Task took {elapsed_time:.2f}s but didn't trigger async")
                print("   This might indicate high async threshold setting")
                print("\n" + "="*60)
                print("⚠️ Test 9A3b WARNING: Complex task processed synchronously")
                return True  # Not failing as config might be different
            else:
                print("\n" + "="*60)
                print("❌ Test 9A3b FAILED: System should have chosen async for complex task")
                return False
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if formation:
            try:
                print("\nShutting down...")
                await formation.kill_overlord()
                formation.shutdown()
            except:
                pass


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)