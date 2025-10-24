#!/usr/bin/env python3
"""Test 19h1: Users endpoints (simplified).

Note: This test is simplified to avoid chat timeouts.
Tests endpoint behavior with non-existent users (404 cases).
"""

import asyncio
import time
from pathlib import Path
import sys
import os
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestUsers(BaseE2ETest):
    """Test users endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19h1_users",
            test_description="Test user endpoints (404 cases)",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    async def test_19h1_users(self):
        """Test users endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_19h1_users",
            description="Test user endpoints (404 cases)",
        )

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready with API server")

            # Test 1: GET /v1/users/identifiers/{user_id} (non-existent)
            print("\n2. Testing GET /v1/users/identifiers/{user_id} (non-existent)...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/users/identifiers/nonexistent_user",
                    headers=self.headers,
                )
            
            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
            print("✅ Returns 404 for non-existent user")

            # Test 2: GET /v1/users/{identifier} (non-existent)
            print("\n3. Testing GET /v1/users/{identifier} (non-existent)...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/users/nonexistent_identifier",
                    headers=self.headers,
                )
            
            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
            print("✅ Returns 404 for non-existent identifier")

            # Test 3: Authentication
            print("\n4. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/users/identifiers/test_user",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19h1_users",
                success=True,
                checks=[
                    "GET /v1/users/identifiers/{user_id} returns 404 for non-existent user",
                    "GET /v1/users/{identifier} returns 404 for non-existent identifier",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19h1_users",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=elapsed_time,
            )
            import traceback
            traceback.print_exc()
            raise
        finally:
            if self.formation:
                await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestUsers()
    await test.test_19h1_users()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
