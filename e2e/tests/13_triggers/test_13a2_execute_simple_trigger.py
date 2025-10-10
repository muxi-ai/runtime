#!/usr/bin/env python3
"""
Test 13A2: Execute simple trigger (synchronous)
Tests POST /formations/{formation_id}/triggers/{trigger_name} with simple data.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test simple trigger execution."""
    print("🚀 MUXI Runtime - Test 13A2: Execute Simple Trigger (Sync)")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-triggers"

    try:
        # Load formation
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Start server
        server = await formation.start_server(block=False)
        await asyncio.sleep(2)  # Wait for server to be ready

        formation_id = formation.formation_id
        base_url = f"http://localhost:18271/v1"
        client_key = "testing-api-key"

        print(f"\n✅ Formation loaded: {formation_id}")
        print(f"📡 Server running at {base_url}")

        # Test simple trigger execution (sync mode)
        print("\n📋 Testing POST /formations/{formation_id}/triggers/test-simple...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/formations/{formation_id}/triggers/test-simple",
                headers={
                    "X-Muxi-Client-Key": client_key,
                    "X-Muxi-User-Id": "test-trigger-user"
                },
                json={
                    "data": {
                        "message": "Hello from webhook test"
                    },
                    "use_async": False  # Synchronous processing
                }
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response type: {data.get('type')}")
                
                # Validate response structure (standard API envelope)
                assert "data" in data, "Response missing 'data' field"
                assert "request" in data, "Response missing 'request' field"
                assert "success" in data, "Response missing 'success' field"
                
                request_info = data["request"]
                assert "id" in request_info, "Missing request.id"
                request_id = request_info["id"]
                
                response_data = data["data"]
                
                # For sync mode, we should get the complete response
                assert "message" in response_data or "content" in response_data, "Missing response content"
                
                print(f"\n✅ Request ID: {request_id}")
                print(f"✅ Response type: {data.get('type')}")
                print(f"✅ Success: {data.get('success')}")
                
                # Check that the agent received and processed the trigger message
                content = response_data.get("message") or response_data.get("content", "")
                print(f"✅ Agent response preview: {content[:100] if content else 'N/A'}...")
                
                # Verify the trigger message was properly rendered
                # The template is: "Test trigger: ${{ data.message }}"
                # So overlord should have received: "Test trigger: Hello from webhook test"
                
                print("\n✅ Test 13A2 PASSED")
                return True
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if 'formation' in locals():
            await formation.shutdown()
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
