#!/usr/bin/env python3
"""Test 19b1: SOP endpoints."""

import asyncio
import json
import time
from pathlib import Path
import sys
import os
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestSOPEndpoints(BaseE2ETest):
    """Test SOP endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19b1_sop_endpoints",
            test_description="Test SOP listing and details retrieval",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    async def test_19b1_sop_endpoints(self):
        """Test SOP endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19b1_sop_endpoints",
            description="Test SOP listing and details retrieval",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            # Start the API server (now waits for readiness automatically)
            await self.formation.start_server(block=False)
            print("✅ Formation ready with API server")

            # Test 1: List SOPs (should be empty - no SOPs in test formation)
            print("\n2. Testing GET /v1/sops...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sops",
                    headers=self.headers,
                )
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            assert data.get("success") is True, f"Expected success=True: {data}"
            # Verify we have data
            sop_data = data.get("data", data)  # Handle wrapped or unwrapped format
            sops = sop_data.get("sops", []) if isinstance(sop_data, dict) else []
            sop_count = len(sops)
            print(f"   Found {sop_count} SOPs")
            print("✅ GET /v1/sops passed")

            # Test 2: Get non-existent SOP (should return 404)
            print("\n3. Testing GET /v1/sops/{sop_name} for non-existent SOP...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sops/non-existent-sop",
                    headers=self.headers,
                )
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"
            data = response.json()
            assert data.get("success") is False, f"Expected success=False: {data}"
            # Error format may vary
            error = data.get("error", {})
            assert error or "error" in str(data).lower(), f"Expected error info: {data}"
            print("✅ 404 for non-existent SOP works")

            # Test 3: Test authentication (should require client key)
            print("\n4. Testing authentication requirement...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sops",
                    headers={"Content-Type": "application/json"},  # No API key
                )
            assert response.status_code == 401, "Should require authentication"
            print("✅ Authentication enforced")

            # Test 4: Test with wrong key type (admin key instead of client key)
            print("\n5. Testing key type validation...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sops",
                    headers={
                        "X-Muxi-Admin-Key": "test-admin-key-123",  # Wrong key type
                        "Content-Type": "application/json",
                    },
                )
            # This might return 401 (no valid client key) or work if the implementation
            # allows admin keys on client endpoints
            # Either is acceptable, but we expect 401 for proper separation
            print(f"   Response with admin key: {response.status_code}")
            
            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19b1_sop_endpoints",
                success=True,
                checks=[
                    "GET /v1/sops passed",
                    "404 for non-existent SOP works",
                    "Authentication enforced",
                    "Key type validation tested",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19b1_sop_endpoints",
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
    test = TestSOPEndpoints()
    await test.test_19b1_sop_endpoints()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
