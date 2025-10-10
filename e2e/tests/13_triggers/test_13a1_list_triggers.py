#!/usr/bin/env python3
"""
Test 13A1: List triggers endpoint
Tests the GET /formations/{formation_id}/triggers endpoint.
"""

import asyncio
import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def main():
    """Test list triggers endpoint."""
    print("🚀 MUXI Runtime - Test 13A1: List Triggers")
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
        client_key = "testing-api-key"  # Static key from formation config

        print(f"\n✅ Formation loaded: {formation_id}")
        print(f"📡 Server running at {base_url}")

        # Test list triggers
        print("\n📋 Testing GET /formations/{formation_id}/triggers...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{base_url}/formations/{formation_id}/triggers",
                headers={"X-Muxi-Client-Key": client_key},
            )

            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {data}")

                # Validate response structure
                assert "data" in data, "Response missing 'data' field"
                trigger_data = data["data"]

                assert "formation_id" in trigger_data, "Missing formation_id"
                assert "triggers" in trigger_data, "Missing triggers list"
                assert "count" in trigger_data, "Missing count"

                print(f"\n✅ Formation ID: {trigger_data['formation_id']}")
                print(f"✅ Trigger count: {trigger_data['count']}")
                print(f"✅ Triggers: {trigger_data['triggers']}")

                # Verify expected triggers
                expected_triggers = {"test-simple", "test-nested", "github-issue"}
                actual_triggers = set(trigger_data["triggers"])

                if expected_triggers <= actual_triggers:
                    print("\n✅ All expected triggers found")
                else:
                    missing = expected_triggers - actual_triggers
                    print(f"\n❌ Missing triggers: {missing}")
                    return False

                print("\n✅ Test 13A1 PASSED")
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
