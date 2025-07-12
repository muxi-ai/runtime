"""
Basic webhook test - check if webhooks are being sent at all
"""

import sys
sys.path.insert(0, ".")

import asyncio
import time
import requests
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation


async def test_webhook_basic():
    """Test basic webhook functionality"""
    
    print("\n=== Basic Webhook Test ===")
    
    # Clear webhook logs first
    try:
        requests.delete("http://127.0.0.1:8765/logs")
        print("✓ Cleared webhook logs")
    except Exception as e:
        print(f"⚠️  Could not clear logs: {e}")
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n📤 Sending async request...")
    
    # Send message with explicit async
    response = await overlord.chat(
        user_id="test_webhook_basic",
        message="hi",
        use_async=True,
    )
    
    print(f"\nResponse type: {type(response)}")
    print(f"Response: {response}")
    
    if isinstance(response, dict) and response.get('status') == 'processing':
        request_id = response.get('request_id')
        webhook_url = response.get('webhook_url')
        
        print(f"\n✅ Got async response!")
        print(f"  Request ID: {request_id}")
        print(f"  Webhook URL: {webhook_url}")
        
        # Keep overlord alive for 30 seconds while checking for webhooks
        print("\n⏳ Keeping overlord alive and checking for webhooks...")
        
        for i in range(30):
            await asyncio.sleep(1)
            
            # Check webhook logs via API
            try:
                logs_response = requests.get("http://127.0.0.1:8765/logs")
                if logs_response.ok:
                    data = logs_response.json()
                    count = data.get('count', 0)
                    
                    if count > 0:
                        print(f"\n✅ Webhook received after {i+1} seconds!")
                        print(f"Total webhooks: {count}")
                        
                        # Print all webhook details
                        for idx, webhook in enumerate(data.get('logs', [])):
                            print(f"\n📨 Webhook {idx + 1}:")
                            print(f"  Timestamp: {webhook.get('timestamp')}")
                            
                            body = webhook.get('body', {})
                            if isinstance(body, dict):
                                print(f"  Keys in body: {list(body.keys())}")
                                print(f"  ID: {body.get('id')}")
                                print(f"  Status: {body.get('status')}")
                                print(f"  Object: {body.get('object')}")
                                
                                # Check for response/result
                                if 'response' in body:
                                    print(f"  Response type: {type(body['response'])}")
                                    if isinstance(body['response'], list):
                                        print(f"  Response items: {len(body['response'])}")
                                if 'result' in body:
                                    print(f"  Result type: {type(body['result'])}")
                        
                        break
                    else:
                        if i % 5 == 4:
                            print(f"  Still waiting... ({i+1}s) - No webhooks yet")
                            
            except Exception as e:
                print(f"  Error checking webhooks: {e}")
        
        else:
            print("\n❌ No webhook received after 30 seconds")
            
            # Check if async task is still in progress
            print("\n📊 Final check...")
            logs_response = requests.get("http://127.0.0.1:8765/logs")
            if logs_response.ok:
                data = logs_response.json()
                print(f"Final webhook count: {data.get('count', 0)}")
    
    else:
        print("❌ Did not get async response")
    
    # Keep overlord alive a bit longer
    print("\n⏳ Keeping overlord alive for 10 more seconds...")
    await asyncio.sleep(10)
    
    # Final cleanup
    print("\n🧹 Shutting down overlord...")
    try:
        await formation.stop_overlord()
        print("✅ Overlord shut down")
    except Exception as e:
        print(f"⚠️  Shutdown error: {e}")
        formation.kill_overlord()
        print("✅ Overlord killed")


if __name__ == "__main__":
    asyncio.run(test_webhook_basic())
    
    # Final webhook check
    print("\n📊 Final webhook status:")
    try:
        response = requests.get("http://127.0.0.1:8765/logs")
        if response.ok:
            data = response.json()
            print(f"Total webhooks: {data.get('count', 0)}")
            
            if data.get('count', 0) > 0:
                print("\nWebhook payloads:")
                for webhook in data.get('logs', []):
                    body = webhook.get('body', {})
                    print(f"\n{body}")
    except Exception as e:
        print(f"Could not check: {e}")
    
    import os
    os._exit(0)