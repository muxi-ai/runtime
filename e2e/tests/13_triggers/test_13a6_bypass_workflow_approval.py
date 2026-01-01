#!/usr/bin/env python3
"""
Test 13A6: Verify triggers bypass workflow approval
Tests that complex trigger requests execute immediately without blocking on approval.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def main():
    """Test that triggers bypass workflow approval."""
    print("🚀 MUXI Runtime - Test 13A6: Bypass Workflow Approval")
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

        # Test complex trigger that would normally require approval
        print("\n📋 Testing POST /triggers/complex-workflow...")
        print("   This is a complex request that would normally require approval")
        print("   But triggers should bypass approval automatically")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/triggers/complex-workflow",
                headers={"X-Muxi-Client-Key": client_key, "X-Muxi-User-Id": "test-trigger-user"},
                json={
                    "data": {
                        "source": "webhook",
                        "project": "payment-service",
                        "operation": "database migration",
                        "priority": "critical"
                    },
                    "use_async": False,  # Synchronous to verify immediate execution
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
                assert data["success"] is True, "Request was not successful"

                request_info = data["request"]
                assert "id" in request_info, "Missing request.id"
                request_id = request_info["id"]

                response_data = data["data"]

                # KEY VALIDATION: For sync mode, we should get the complete response
                # If approval was required, we would have gotten a different response
                # (clarification request or pending status)
                assert response_data.get("status") == "completed", \
                    f"Expected 'completed' status, got: {response_data.get('status')}"

                # Should have actual content, not an approval request
                content = response_data.get("content") or response_data.get("message", "")
                assert content, "No response content received"

                # KEY VALIDATION: Verify it's NOT an approval/clarification request
                content_lower = content.lower()
                is_approval_request = (
                    "would you like me to proceed" in content_lower or
                    "should i proceed" in content_lower or
                    "review the plan" in content_lower or
                    "approve this workflow" in content_lower
                )

                # The response should NOT be asking for approval
                assert not is_approval_request, \
                    f"Response appears to be an approval request: {content[:200]}"

                print(f"\n✅ Request ID: {request_id}")
                print(f"✅ Response type: {data.get('type')}")
                print(f"✅ Status: {response_data.get('status')}")
                print(f"✅ Agent executed immediately (no approval requested)")
                print(f"✅ Response preview: {content[:150]}...")

                # The important thing is that we got a response immediately
                # without being asked for approval, even though the request
                # was complex enough to trigger workflow orchestration
                print("\n✅ Test 13A6 PASSED")
                print("✅ Trigger bypassed workflow approval as expected")
                print("✅ Request completed synchronously without approval gate")
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
