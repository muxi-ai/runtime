#!/usr/bin/env python3
"""Test 19m1: Admin config and overlord endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import os
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestAdminConfig(BaseE2ETest):
    """Test admin config and overlord endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19m1_admin_config",
            test_description="Test admin config and overlord endpoints",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "Content-Type": "application/json",
        }

    async def test_19m1_admin_config(self):
        """Test admin config and overlord endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19m1_admin_config",
            description="Test admin config and overlord endpoints",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            # Start the API server
            await self.formation.start_server(block=False)
            
            # Wait for server to be ready
            await asyncio.sleep(2)
            print("✅ Formation ready with API server")

            # Test 1: GET /v1/config
            print("\n2. Testing GET /v1/config...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/config",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            # Data contains config fields directly (no nested "config" key)
            assert "formation_id" in data["data"]
            assert "schema_version" in data["data"]
            assert "agents" in data["data"]
            print(f"   Formation ID: {data['data']['formation_id']}")
            print("✅ GET /v1/config passed")

            # Test 2: GET /v1/formation
            print("\n3. Testing GET /v1/formation...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/formation",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            # Data contains formation fields directly (no nested "formation" key)
            assert "id" in data["data"] or "formation_id" in data["data"]
            assert "agents" in data["data"]
            formation_id = data['data'].get('id', data['data'].get('formation_id'))
            print(f"   Formation: {formation_id}")
            print(f"   Agents: {len(data['data'].get('agents', []))}")
            print("✅ GET /v1/formation passed")

            # Test 3: GET /v1/status
            print("\n4. Testing GET /v1/status...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/status",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            # Data contains status fields directly (no nested "status" key)
            assert "formation" in data["data"]
            assert "agents" in data["data"]
            assert "stats" in data["data"]
            print(f"   Formation: {data['data']['formation'].get('name', 'N/A')}")
            print(f"   Agents: {len(data['data'].get('agents', []))}")
            print("✅ GET /v1/status passed")

            # Test 4: GET /v1/overlord
            print("\n5. Testing GET /v1/overlord...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/overlord",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            # Per spec, object type is "overlord_config"
            assert data["object"] in ["overlord", "overlord_config"], f"Expected overlord object, got {data.get('object')}"
            print(f"   Overlord endpoint available")
            print("✅ GET /v1/overlord passed")

            # Test 5: GET /v1/overlord/persona
            print("\n6. Testing GET /v1/overlord/persona...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/overlord/soul",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            assert "soul" in data["data"]
            # Should have soul info
            if data["data"]["soul"]:
                print(f"   Soul: {data['data']['soul'].get('name', 'N/A')}")
            else:
                print("   Soul: None configured")
            print("✅ GET /v1/overlord/soul passed")

            # Test 6: Authentication (without admin key)
            print("\n7. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/config",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19m1_admin_config",
                success=True,
                checks=[
                    "GET /v1/config passed (formation config)",
                    "GET /v1/formation passed (formation info)",
                    "GET /v1/status passed (runtime status)",
                    "GET /v1/overlord passed (overlord state)",
                    "GET /v1/overlord/persona passed",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19m1_admin_config",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=elapsed_time,
            )
            import traceback
            traceback.print_exc()
            raise
        finally:
            # Cleanup
            if self.formation:
                await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestAdminConfig()
    await test.test_19m1_admin_config()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
