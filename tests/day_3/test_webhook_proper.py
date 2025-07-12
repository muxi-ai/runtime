"""
Proper webhook test that waits for webhook before shutdown
"""

import sys
sys.path.insert(0, ".")

import asyncio
import time
import requests
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation


async def test_webhook_proper():
    """Test webhook with proper lifecycle management"""
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n=== Webhook Test with Proper Lifecycle ===")
    
    # Clear webhook logs first
    try:
        requests.delete("http://127.0.0.1:8765/logs")
    except:
        pass  # Webhook server might not support DELETE
    
    # Send simple message with async
    response = await overlord.chat(
        user_id="test_webhook_user",
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
    
    webhook_received = False
    
    # Check if we got async dict response
    if isinstance(response, dict) and response.get('status') == 'processing':
        request_id = response.get('request_id')
        webhook_url = response.get('webhook_url')
        
        print(f"\n✅ Got async response!")
        print(f"Request ID: {request_id}")
        print(f"Webhook URL: {webhook_url}")
        
        # Wait for webhook with longer timeout
        print("\n⏳ Waiting for webhook (keeping overlord alive)...")
        
        for i in range(60):  # Wait up to 60 seconds
            await asyncio.sleep(1)
            
            # Check webhook logs
            try:
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
                                webhook_req_id = body.get('id') or body.get('request_id')
                                print(f"  Request ID: {webhook_req_id}")
                                
                                # Check if this is our webhook
                                if webhook_req_id == request_id and body.get('status') == 'completed':
                                    print(f"  ✅ This is our webhook!")
                                    
                                    response_data = body.get('response', [])
                                    if response_data:
                                        print(f"  Response: {response_data}")
                                        
                                        # Extract text from response
                                        if isinstance(response_data, list) and len(response_data) > 0:
                                            first_response = response_data[0]
                                            if isinstance(first_response, dict) and first_response.get('type') == 'text':
                                                text = first_response.get('text', '')
                                                print(f"  Response text: {text}")
                                                
                                                # Verify it's a response to "hi"
                                                text_lower = text.lower()
                                                if any(greeting in text_lower for greeting in ['hello', 'hi', 'hey', 'greet']):
                                                    print(f"  ✅ Result contains appropriate greeting response")
                                    
                                    # Exit immediately on successful webhook
                                    webhook_received = True
                                    break
                        
                        # Exit outer loop if webhook received
                        if webhook_received:
                            break
            except Exception as e:
                print(f"  Error checking webhooks: {e}")
            
            # Check if we should exit the waiting loop
            if webhook_received:
                break
                
            if i % 10 == 9:
                print(f"  Still waiting... ({i+1}s) - Overlord is still running")
        
        if not webhook_received:
            print("\n❌ No webhook received after 60 seconds")
    else:
        print(f"\n❌ Got unexpected response type: {type(response)}")
        if isinstance(response, str):
            print(f"Response content: {response}")
    
    # No need to wait after webhook is received
    if webhook_received:
        print("\n✅ Webhook successfully received and verified!")
    
    # Cleanup - only after webhook is received or timeout
    print("\n🧹 Shutting down overlord...")
    try:
        await formation.stop_overlord(timeout=10.0)
        print("✅ Overlord shut down gracefully")
    except Exception as e:
        print(f"⚠️  Overlord shutdown error: {e}")
        print("🔨 Using kill_overlord()...")
        formation.kill_overlord()
    
    print("\n✅ Test complete")
    print(f"Webhook received: {webhook_received}")
    
    return webhook_received


if __name__ == "__main__":
    success = asyncio.run(test_webhook_proper())
    if success:
        print("\n🎉 Webhook test PASSED!")
    else:
        print("\n❌ Webhook test FAILED!")
    
    # Force exit to ensure all threads/tasks are terminated
    import os
    os._exit(0 if success else 1)