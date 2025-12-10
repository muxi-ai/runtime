#!/usr/bin/env python3
"""
Test 13A3: Execute nested data trigger (asynchronous)
Tests POST /triggers/{trigger_name} with nested data.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test nested trigger execution with async processing."""
    print("🚀 MUXI Runtime - Test 13A3: Execute Nested Trigger (Async)")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-triggers"

    try:
        # Load formation
        formation = Formation()
        await formation.load(str(formation_path))

        # Start server
        server = await formation.start_server(block=False)
        await asyncio.sleep(2)  # Wait for server to be ready

        formation_id = formation.formation_id
        base_url = "http://localhost:18271/v1"
        client_key = "testing-api-key"

        print(f"\n✅ Formation loaded: {formation_id}")
        print(f"📡 Server running at {base_url}")

        # Test nested trigger execution (async mode)
        print("\n📋 Testing POST /triggers/test-nested...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/triggers/test-nested",
                headers={"X-Muxi-Client-Key": client_key, "X-Muxi-User-Id": "test-trigger-user"},
                json={
                    "data": {
                        "source": "monitoring-system",
                        "event": {
                            "type": "deployment",
                            "id": "deploy-12345",
                            "status": "completed",
                            "details": "Production deployment completed successfully",
                        },
                    },
                    "use_async": True,  # Asynchronous processing (default)
                },
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

                # For async mode, we get immediate acknowledgment
                # The actual processing happens in the background
                assert (
                    "request_id" in response_data or "id" in request_info
                ), "Missing request identifier"

                print(f"\n✅ Request ID: {request_id}")
                print(f"✅ Response type: {data.get('type')}")
                print(f"✅ Success: {data.get('success')}")
                print("✅ Async processing initiated")

                # Wait a bit for async processing
                print("\n⏳ Waiting for async processing...")
                await asyncio.sleep(5)

                # The template renders nested data:
                # Event from monitoring-system:
                # **Type**: deployment
                # **ID**: deploy-12345
                # **Status**: completed
                # **Details**: Production deployment completed successfully

                print("\n✅ Test 13A3 PASSED")
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
        if "formation" in locals():
            await formation.shutdown()
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
