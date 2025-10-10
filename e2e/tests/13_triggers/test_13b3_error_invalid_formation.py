#!/usr/bin/env python3
"""
Test 13B3: Error handling - Invalid formation ID
Tests POST /formations/{formation_id}/triggers/{trigger_name} with wrong formation ID.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test error handling for invalid formation ID."""
    print("🚀 MUXI Runtime - Test 13B3: Error - Invalid Formation ID")
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

        # Test with wrong formation ID
        wrong_formation_id = "wrong-formation-id"
        print(f"\n📋 Testing POST with wrong formation ID: {wrong_formation_id}...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/formations/{wrong_formation_id}/triggers/test-simple",
                headers={
                    "X-Muxi-Client-Key": client_key,
                    "X-Muxi-User-Id": "test-user"
                },
                json={
                    "data": {
                        "message": "This should fail"
                    }
                }
            )
            
            print(f"   Status: {response.status_code}")
            
            # Should return 404 Not Found
            if response.status_code == 404:
                data = response.json()
                print(f"   Response type: {data.get('type')}")
                
                # Validate error response structure
                assert "error" in data, "Response missing 'error' field"
                assert "success" in data, "Response missing 'success' field"
                assert data["success"] is False, "Success should be false for errors"
                
                error_info = data["error"]
                assert "code" in error_info, "Missing error.code"
                assert "message" in error_info, "Missing error.message"
                
                message = error_info["message"]
                print(f"\n✅ Correct status code: 404")
                print(f"✅ Error code: {error_info['code']}")
                print(f"✅ Error message: {message}")
                
                # The error should mention formation not found
                assert "formation" in message.lower() and ("not found" in message.lower() or wrong_formation_id in message.lower()), \
                    f"Error message should indicate invalid formation: {message}"
                
                print("\n✅ Test 13B3 PASSED")
                return True
            else:
                print(f"❌ Expected 404, got {response.status_code}")
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
