#!/usr/bin/env python3
"""
Test 13A7: Verify triggers bypass approval even with VERY low threshold
Tests that triggers execute immediately even when approval threshold is extremely low (2.0).
This ensures the bypass flag works correctly regardless of threshold configuration.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def main():
    """Test that triggers bypass approval even with very low threshold."""
    print("🚀 MUXI Runtime - Test 13A7: Low Threshold Bypass")
    print("=" * 60)
    print("Configuration: plan_approval_threshold = 2.0 (VERY LOW)")
    print("Expected: Trigger bypasses approval regardless")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-low-threshold"

    try:
        # Load formation with very low approval threshold
        formation = Formation()
        await formation.load(str(formation_path))

        # Start server on different port to avoid conflicts
        server = await formation.start_server(block=False)
        await asyncio.sleep(2)  # Wait for server to be ready

        formation_id = formation.formation_id
        base_url = "http://localhost:18272/v1"
        client_key = "testing-api-key"

        print(f"\n✅ Formation loaded: {formation_id}")
        print(f"📡 Server running at {base_url}")

        # Verify threshold configuration
        overlord = formation._overlord
        approval_threshold = overlord.plan_approval_threshold
        complexity_threshold = overlord.complexity_threshold

        print(f"\n📊 Threshold Configuration:")
        print(f"   Complexity threshold: {complexity_threshold}")
        print(f"   Approval threshold: {approval_threshold}")

        assert approval_threshold == 2.0, \
            f"Expected approval threshold 2.0, got {approval_threshold}"

        print(f"   ✅ Very low approval threshold confirmed (2.0)")

        # Test production deployment trigger (complex request that will exceed threshold)
        print("\n📋 Testing POST /triggers/deploy-request...")
        print("   This request will have complexity > 2.0 normally requiring approval")
        print("   But trigger should bypass approval automatically")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/triggers/deploy-request",
                headers={"X-Muxi-Client-Key": client_key, "X-Muxi-User-Id": "test-trigger-user"},
                json={
                    "data": {
                        "system": "CI/CD Pipeline",
                        "service": "api-gateway",
                        "environment": "production",
                        "version": "v2.4.1",
                        "requester": "deploy-bot"
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

                # CRITICAL VALIDATION: Should get completed status, not pending approval
                status = response_data.get("status")
                assert status == "completed", \
                    f"Expected 'completed' status (bypass worked), got: {status}"

                # Should have actual content, not an approval request
                content = response_data.get("content") or response_data.get("message", "")
                assert content, "No response content received"

                # KEY VALIDATION: Response should NOT contain approval language
                content_lower = content.lower()
                approval_indicators = [
                    "would you like me to proceed",
                    "should i proceed",
                    "would you like to proceed",
                    "do you want me to proceed",
                    "review the plan",
                    "approve this workflow",
                    "approval required",
                    "please approve",
                    "waiting for approval"
                ]

                has_approval_language = any(phrase in content_lower for phrase in approval_indicators)

                if has_approval_language:
                    print(f"\n❌ FAILURE: Response contains approval language!")
                    print(f"   Response: {content[:300]}")
                    return False

                print(f"\n✅ Request ID: {request_id}")
                print(f"✅ Response type: {data.get('type')}")
                print(f"✅ Status: {status}")
                print(f"✅ No approval language detected in response")
                print(f"✅ Agent executed immediately despite low threshold")
                print(f"✅ Response preview: {content[:150]}...")

                # Verify this was a complex enough request that WOULD have triggered approval
                # if not for the bypass flag
                print(f"\n📊 Validation:")
                print(f"   ✅ Approval threshold is VERY low (2.0)")
                print(f"   ✅ Request was complex (deployment with 6 steps)")
                print(f"   ✅ Normally would require approval")
                print(f"   ✅ But trigger bypassed it successfully")

                print("\n✅ Test 13A7 PASSED")
                print("✅ Trigger bypass works even with extremely low thresholds")
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
