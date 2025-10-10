#!/usr/bin/env python3
"""
Test 13B2: Error handling - Missing required data field
Tests POST /formations/{formation_id}/triggers/{trigger_name} with incomplete data.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test error handling for missing required data fields."""
    print("🚀 MUXI Runtime - Test 13B2: Error - Missing Required Data")
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
        base_url = "http://localhost:18271/v1"
        client_key = "testing-api-key"

        print(f"\n✅ Formation loaded: {formation_id}")
        print(f"📡 Server running at {base_url}")

        # Test trigger with missing data field
        # The github-issue template requires: data.repository, data.issue.number, etc.
        print("\n📋 Testing POST with missing required data.issue.number field...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/formations/{formation_id}/triggers/github-issue",
                headers={
                    "X-Muxi-Client-Key": client_key,
                    "X-Muxi-User-Id": "test-user"
                },
                json={
                    "data": {
                        "repository": "muxi/runtime",
                        "issue": {
                            # Missing "number" field - should cause error
                            "title": "Test issue",
                            "author": "test-user",
                            "state": "open"
                        }
                    }
                }
            )

            print(f"   Status: {response.status_code}")

            # Should return 400 Bad Request or 500 Internal Error
            if response.status_code in [400, 500]:
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
                print(f"\n✅ Correct error status: {response.status_code}")
                print(f"✅ Error code: {error_info['code']}")
                print(f"✅ Error message: {message}")

                # The error should mention the missing field or template rendering failure
                assert any(keyword in message.lower() for keyword in ["missing", "not found", "number", "template"]), \
                    f"Error message should indicate missing data: {message}"

                print("\n✅ Test 13B2 PASSED")
                return True
            else:
                print(f"❌ Expected 400 or 500, got {response.status_code}")
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
