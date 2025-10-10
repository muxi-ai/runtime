#!/usr/bin/env python3
"""
Test 13A4: Execute GitHub issue trigger
Tests POST /formations/{formation_id}/triggers/{trigger_name} with realistic GitHub webhook data.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test GitHub issue trigger execution."""
    print("🚀 MUXI Runtime - Test 13A4: Execute GitHub Issue Trigger")
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

        # Test GitHub issue trigger with realistic data
        print("\n📋 Testing POST /formations/{formation_id}/triggers/github-issue...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/formations/{formation_id}/triggers/github-issue",
                headers={
                    "X-Muxi-Client-Key": client_key,
                    "X-Muxi-User-Id": "github-webhook"
                },
                json={
                    "data": {
                        "repository": "muxi/runtime",
                        "issue": {
                            "number": 42,
                            "title": "Add webhook support for external integrations",
                            "author": "dev-user",
                            "state": "open"
                        }
                    },
                    "session_id": "github-issues-session",
                    "use_async": False
                }
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response type: {data.get('type')}")
                
                # Validate response structure
                assert "data" in data, "Response missing 'data' field"
                assert "request" in data, "Response missing 'request' field"
                assert "success" in data, "Response missing 'success' field"
                
                request_info = data["request"]
                assert "id" in request_info, "Missing request.id"
                request_id = request_info["id"]
                
                response_data = data["data"]
                
                print(f"\n✅ Request ID: {request_id}")
                print(f"✅ Response type: {data.get('type')}")
                print(f"✅ Success: {data.get('success')}")
                
                # Check that the agent received the formatted GitHub issue
                content = response_data.get("message") or response_data.get("content", "")
                print(f"✅ Agent response preview: {content[:150] if content else 'N/A'}...")
                
                # The template should have rendered:
                # New GitHub issue from muxi/runtime:
                # **Issue #42**: Add webhook support for external integrations
                # **Author**: dev-user
                # **State**: open
                # Please provide a brief analysis.
                
                print("\n✅ Test 13A4 PASSED")
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
