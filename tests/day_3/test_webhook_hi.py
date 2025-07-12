"""
Simplest possible webhook test
"""

import sys
sys.path.insert(0, ".")

import asyncio
from pathlib import Path
from src.muxi.runtime.formation.formation import Formation


async def test_hi():
    """Simple 'hi' test with async"""
    
    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    print("\n=== Simple 'hi' Test with use_async=True ===")
    
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
    print(f"Response length: {len(str(response))}")
    
    # Check if it's async
    if isinstance(response, str):
        response_lower = response.lower()
        if "async" in response_lower and "request" in response_lower:
            print("\n✅ Got async response!")
            # Look for request ID
            import re
            match = re.search(r'req_[a-zA-Z0-9_-]+', response)
            if match:
                request_id = match.group(0)
                print(f"Request ID: {request_id}")
                
                # Check webhook logs
                print("\nChecking webhook logs...")
                import time
                time.sleep(5)  # Wait a bit
                
                # Check via API
                import requests
                logs_response = requests.get("http://127.0.0.1:8765/logs")
                if logs_response.ok:
                    logs_data = logs_response.json()
                    print(f"Webhook count: {logs_data.get('count', 0)}")
                    if logs_data.get('logs'):
                        print("Webhooks received:")
                        for webhook in logs_data['logs']:
                            print(f"  - {webhook.get('timestamp')}: {webhook.get('path')}")
                            body = webhook.get('body', {})
                            if isinstance(body, dict) and body.get('request_id') == request_id:
                                print(f"    ✅ Found webhook for {request_id}!")
                                result = body.get('result')
                                if result:
                                    print(f"    Result: {str(result)[:100]}...")
        else:
            print("\n❌ Got synchronous response (not async)")
    
    # Cleanup
    await formation.stop_overlord()


if __name__ == "__main__":
    asyncio.run(test_hi())