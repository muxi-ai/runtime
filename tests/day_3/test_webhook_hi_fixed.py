"""
Fixed webhook test that waits for completion
"""

import sys
sys.path.insert(0, ".")

import asyncio
import time
import requests
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation


async def test_hi_with_wait():
    """Simple 'hi' test with async and proper waiting"""
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n=== Simple 'hi' Test with Webhook Waiting ===")
    
    # Clear webhook logs first
    requests.delete("http://127.0.0.1:8765/logs")
    
    # Send simple message with async
    response = await overlord.chat(
        user_id="test_hi_user",
        message="hi",
        use_async=True,
    )
    
    # Handle async generator if needed
    if hasattr(response, '__aiter__'):
        chunks = []
        async for chunk in response:
            chunks.append(chunk)
        response = "".join(chunks)
    
    print(f"\nResponse: {response}")
    print(f"Response type: {type(response)}")
    
    # Check if we got async dict response
    if isinstance(response, dict) and response.get('status') == 'processing':
        request_id = response.get('request_id')
        webhook_url = response.get('webhook_url')
        
        print(f"\n✅ Got async response!")
        print(f"Request ID: {request_id}")
        print(f"Webhook URL: {webhook_url}")
        
        # Wait for webhook
        print("\n⏳ Waiting for webhook...")
        webhook_received = False
        for i in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            
            # Check webhook logs
            logs_response = requests.get("http://127.0.0.1:8765/logs")
            if logs_response.ok:
                logs_data = logs_response.json()
                if logs_data.get('count', 0) > 0:
                    print(f"\n✅ Webhook received after {i+1} seconds!")
                    webhook_received = True
                    
                    # Show webhook details
                    for webhook in logs_data['logs']:
                        print(f"\nWebhook details:")
                        print(f"  Timestamp: {webhook.get('timestamp')}")
                        print(f"  Path: {webhook.get('path')}")
                        
                        body = webhook.get('body', {})
                        if isinstance(body, dict):
                            print(f"  Status: {body.get('status')}")
                            print(f"  Request ID: {body.get('request_id')}")
                            
                            result = body.get('result')
                            if result:
                                print(f"  Result type: {type(result).__name__}")
                                print(f"  Result: {str(result)[:200]}...")
                    break
            
            if i % 5 == 4:
                print(f"  Still waiting... ({i+1}s)")
        
        if not webhook_received:
            print("\n❌ No webhook received after 30 seconds")
    else:
        print(f"\n❌ Got unexpected response type: {type(response)}")
        if isinstance(response, str):
            print(f"Response content: {response}")
    
    # Don't shut down immediately - give async tasks time to complete
    print("\n⏳ Giving async tasks 5 more seconds to complete...")
    await asyncio.sleep(5)
    
    # Cleanup
    print("\n🧹 Shutting down overlord...")
    await formation.stop_overlord()
    
    print("\n✅ Test complete")


if __name__ == "__main__":
    asyncio.run(test_hi_with_wait())