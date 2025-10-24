#!/usr/bin/env python3
"""Test 19d1: Health and status endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestHealthStatus(BaseE2ETest):
    """Test health and status endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19d1_health_status",
            test_description="Test health and status endpoints",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271"
        self.admin_key = "test-admin-key-123"
        self.admin_headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "Content-Type": "application/json",
        }

    async def test_19d1_health_status(self):
        """Test health and status endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19d1_health_status",
            description="Test health and status endpoints",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            # Start the API server
            await self.formation.start_server(block=False)
            print("✅ Formation ready with API server")

            # Test 1: Root status endpoint (/)
            print("\n2. Testing GET /...")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/")
            
            # Should return HTML status page with "Up" or "Down"
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            assert "text/html" in response.headers.get("content-type", ""), "Should return HTML"
            assert "Up" in response.text or "Down" in response.text, "Should contain status"
            print("✅ GET / passed")

            # Test 2: /v1 status endpoint
            print("\n3. Testing GET /v1...")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/v1")
            
            # Should return same HTML status page
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")
            print("✅ GET /v1 passed")

            # Test 3: Health check endpoint
            print("\n4. Testing GET /v1/health...")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/v1/health")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            # Verify response structure
            assert data["object"] == "status", f"Wrong object type: {data['object']}"
            assert data["type"] == "status.retrieved", f"Wrong event type: {data['type']}"
            assert data["success"] is True, "Success should be True"
            assert "data" in data, "Missing data field"
            assert data["data"]["status"] == "healthy", f"Status should be healthy: {data['data']['status']}"
            assert data["data"]["formation_id"] == "api-test-formation", "Wrong formation ID"
            
            print(f"   Status: {data['data']['status']}")
            print(f"   Formation ID: {data['data']['formation_id']}")
            print("✅ GET /v1/health passed")

            # Test 4: Status endpoint (requires admin key)
            print("\n5. Testing GET /v1/status...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v1/status",
                    headers=self.admin_headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            # Verify response structure
            assert data["object"] == "formation_status"
            assert data["type"] == "status.retrieved"
            assert data["success"] is True
            assert "data" in data
            
            # Verify status data contains expected fields
            status_data = data["data"]
            assert "formation" in status_data
            assert "agents" in status_data
            assert "stats" in status_data
            assert status_data["formation"]["id"] == "api-test-formation"
            assert "count" in status_data["agents"]
            assert "running" in status_data["stats"]
            
            print(f"   Formation ID: {status_data['formation']['id']}")
            print(f"   Agents count: {status_data['agents']['count']}")
            print(f"   Uptime: {status_data['stats']['running']['seconds']}s")
            print("✅ GET /v1/status passed")

            # Test 5: Status without auth (should fail)
            print("\n6. Testing GET /v1/status without authentication...")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/v1/status")
            
            assert response.status_code == 401, f"Expected 401, got {response.status_code}"
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "UNAUTHORIZED"
            print("✅ Authentication enforced on /v1/status")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19d1_health_status",
                success=True,
                checks=[
                    "GET / passed (HTML status page)",
                    "GET /v1 passed (HTML status page)",
                    "GET /v1/health passed (healthy status)",
                    "GET /v1/status passed (detailed status with auth)",
                    "Authentication enforced on /v1/status",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19d1_health_status",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=elapsed_time,
            )
            raise
        finally:
            # Cleanup
            if self.formation:
                await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestHealthStatus()
    await test.test_19d1_health_status()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
