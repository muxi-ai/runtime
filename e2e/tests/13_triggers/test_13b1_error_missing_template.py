#!/usr/bin/env python3
"""
Test 13B1: Error handling - Missing trigger template
Tests POST /triggers/{trigger_name} with non-existent trigger.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def main():
    """Test error handling for missing trigger template."""
    print("🚀 MUXI Runtime - Test 13B1: Error - Missing Trigger Template")
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

        # Test non-existent trigger
        print("\n📋 Testing POST /triggers/non-existent...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/triggers/non-existent",
                headers={"X-Muxi-Client-Key": client_key, "X-Muxi-User-Id": "test-user"},
                json={"data": {"message": "This should fail"}},
            )

            print(f"   Status: {response.status_code}")

            # Should return 404 Not Found
            if response.status_code == 404:
                data = response.json()
                print(f"   Response: {data}")

                # Validate error response structure
                assert "error" in data, "Response missing 'error' field"
                assert "success" in data, "Response missing 'success' field"
                assert data["success"] is False, "Success should be false for errors"

                error_info = data["error"]
                assert "code" in error_info, "Missing error.code"
                assert "message" in error_info, "Missing error.message"

                # Check error message mentions the missing trigger
                message = error_info["message"]
                assert (
                    "non-existent" in message.lower() or "not found" in message.lower()
                ), f"Error message should mention missing trigger: {message}"

                print("\n✅ Correct status code: 404")
                print(f"✅ Error code: {error_info['code']}")
                print(f"✅ Error message: {message}")

                print("\n✅ Test 13B1 PASSED")
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
        if "formation" in locals():
            formation.stop()
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    import os; os._exit(0 if success else 1)
