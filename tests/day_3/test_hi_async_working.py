"""
Test simple 'hi' with async - working version based on test_webhook_basic
"""

import sys
sys.path.insert(0, ".")

import asyncio
import time
import requests
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import setup_webhook_test


async def test_hi_async_working():
    """Simple 'hi' test with async that actually works"""
    
    # Setup webhook testing
    setup_webhook_test()
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n=== Simple 'hi' Test with Async (Working Version) ===")
    
    # Send simple message with explicit use_async=True
    response = await overlord.chat(
        user_id="test_hi_async_working",
        message="hi",
        use_async=True,
    )
    
    print(f"\nResponse type: {type(response)}")
    print(f"Response: {response}")
    
    webhook_received = False
    webhook_result = None
    
    if isinstance(response, dict) and response.get('status') == 'processing':
        request_id = response.get('request_id')
        webhook_url = response.get('webhook_url')
        
        print(f"\n✅ Got async response!")
        print(f"  Request ID: {request_id}")
        print(f"  Webhook URL: {webhook_url}")
        
        # Keep checking for webhook while keeping overlord alive
        print("\n⏳ Waiting for webhook...")
        
        for i in range(30):
            await asyncio.sleep(1)
            
            try:
                logs_response = requests.get("http://127.0.0.1:8765/logs")
                if logs_response.ok:
                    data = logs_response.json()
                    if data.get('count', 0) > 0:
                        # Check if our webhook arrived
                        for webhook in data.get('logs', []):
                            body = webhook.get('body', {})
                            if isinstance(body, dict) and body.get('id') == request_id:
                                print(f"\n✅ Webhook received after {i+1} seconds!")
                                webhook_received = True
                                
                                # Extract response
                                response_data = body.get('response', [])
                                if isinstance(response_data, list) and len(response_data) > 0:
                                    for item in response_data:
                                        if isinstance(item, dict) and item.get('type') == 'text':
                                            webhook_result = item.get('text', '')
                                            print(f"  Response: {webhook_result}")
                                            break
                                
                                # Verify it's a greeting
                                if webhook_result:
                                    result_lower = webhook_result.lower()
                                    if any(greeting in result_lower for greeting in ['hello', 'hi', 'hey', 'how can i']):
                                        print("  ✅ Response is a valid greeting!")
                                    else:
                                        print(f"  ⚠️  Unexpected response: {webhook_result}")
                                
                                break
                        
                        if webhook_received:
                            break
                            
            except Exception as e:
                print(f"  Error checking webhooks: {e}")
            
            if i % 5 == 4:
                print(f"  Still waiting... ({i+1}s)")
        
        if not webhook_received:
            print("\n❌ No webhook received after 30 seconds")
    else:
        print("\n❌ Did not get async response as expected")
    
    # Give a moment for cleanup
    await asyncio.sleep(2)
    
    # Cleanup
    print("\n🧹 Shutting down overlord...")
    try:
        await formation.stop_overlord()
        print("✅ Overlord shut down gracefully")
    except Exception as e:
        print(f"⚠️  Overlord shutdown error: {e}")
        formation.kill_overlord()
        print("✅ Overlord killed")
    
    return webhook_received, webhook_result


if __name__ == "__main__":
    start_time = time.time()
    
    received, result = asyncio.run(test_hi_async_working())
    
    elapsed = time.time() - start_time
    print(f"\n🎉 Test completed in {elapsed:.2f} seconds")
    print(f"📊 Webhook received: {received}")
    if result:
        print(f"📝 Response: {result}")
    
    # Final check
    try:
        response = requests.get("http://127.0.0.1:8765/logs")
        if response.ok:
            data = response.json()
            print(f"📊 Total webhooks in log: {data.get('count', 0)}")
    except:
        pass
    
    import os
    os._exit(0 if received else 1)