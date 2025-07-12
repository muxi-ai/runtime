"""
Debug webhook issues
"""

import sys
sys.path.insert(0, ".")

import asyncio
import time
import requests
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation
from utils.webhook_log_reader import WebhookLogReader


async def test_webhook_debug():
    """Debug webhook delivery"""
    
    print("\n=== Webhook Debug Test ===")
    
    # Clear logs
    reader = WebhookLogReader()
    reader.clear_logs()
    print("✓ Cleared webhook logs")
    
    # Check server is running
    try:
        response = requests.get("http://127.0.0.1:8765/logs")
        print(f"✓ Webhook server is running: {response.status_code}")
    except Exception as e:
        print(f"❌ Webhook server not accessible: {e}")
        return
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n📤 Sending async request...")
    
    # Send message with explicit async
    response = await overlord.chat(
        user_id="test_webhook_debug",
        message="hi",
        use_async=True,
    )
    
    print(f"Response type: {type(response)}")
    print(f"Response: {response}")
    
    if isinstance(response, dict) and response.get('status') == 'processing':
        request_id = response.get('request_id')
        print(f"\n✅ Got async response with request_id: {request_id}")
        
        # Wait and check for webhooks
        print("\n⏳ Waiting for webhook...")
        for i in range(30):
            time.sleep(1)
            
            # Check via API
            api_response = requests.get("http://127.0.0.1:8765/logs")
            if api_response.ok:
                data = api_response.json()
                count = data.get('count', 0)
                if count > 0:
                    print(f"\n✅ Webhook received after {i+1} seconds!")
                    print(f"Total webhooks: {count}")
                    
                    # Print webhook details
                    for idx, webhook in enumerate(data.get('logs', [])):
                        print(f"\nWebhook {idx + 1}:")
                        body = webhook.get('body', {})
                        print(f"  Timestamp: {webhook.get('timestamp')}")
                        if isinstance(body, dict):
                            print(f"  ID: {body.get('id')}")
                            print(f"  Request ID: {body.get('request_id')}")
                            print(f"  Status: {body.get('status')}")
                            print(f"  Object: {body.get('object')}")
                    break
            
            if i % 5 == 4:
                print(f"  Still waiting... ({i+1}s)")
        else:
            print("\n❌ No webhook received after 30 seconds")
            
            # Check if async task is still running
            print("\n📊 Checking async task status...")
            # This would require access to request tracker
    
    # Cleanup
    print("\n🧹 Shutting down...")
    try:
        await formation.stop_overlord()
    except:
        formation.kill_overlord()


if __name__ == "__main__":
    asyncio.run(test_webhook_debug())
    
    # Final check
    print("\n📊 Final webhook check:")
    response = requests.get("http://127.0.0.1:8765/logs")
    if response.ok:
        data = response.json()
        print(f"Total webhooks in log: {data.get('count', 0)}")
    
    import os
    os._exit(0)