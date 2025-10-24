#!/usr/bin/env python3
"""Test 19l1: Secrets management endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestSecrets(BaseE2ETest):
    """Test secrets management endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19l1_secrets",
            test_description="Test secrets management endpoints",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "Content-Type": "application/json",
        }

    async def test_19l1_secrets(self):
        """Test secrets management endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19l1_secrets",
            description="Test secrets management endpoints",
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

            # Test 1: GET /v1/secrets (list all secrets - keys only)
            print("\n2. Testing GET /v1/secrets...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/secrets",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            assert "secrets" in data["data"]
            initial_count = len(data["data"]["secrets"])
            print(f"   Initial secret count: {initial_count}")
            print("✅ GET /v1/secrets passed")

            # Test 2: POST /v1/secrets (create new secret)
            print("\n3. Testing POST /v1/secrets...")
            secret_data = {
                "key": "TEST_API_KEY_19L1",
                "value": "test_secret_value_12345",
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/secrets",
                    headers=self.headers,
                    json=secret_data,
                )
            
            if response.status_code != 201:
                print(f"   ERROR: Got status {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 201, f"Expected 201, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            print(f"   Created secret: {secret_data['key']}")
            print("✅ POST /v1/secrets passed")

            # Test 3: GET /v1/secrets (verify created)
            print("\n4. Verifying secret was created...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/secrets",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            new_count = len(data["data"]["secrets"])
            assert new_count == initial_count + 1, "Secret count should increase by 1"
            
            # Find our secret in the list
            secret_keys = [s["key"] for s in data["data"]["secrets"]]
            assert "TEST_API_KEY_19L1" in secret_keys, "New secret should be in list"
            print("✅ Secret creation verified")

            # Test 4: PUT /v1/secrets/{key} (update secret)
            print("\n5. Testing PUT /v1/secrets/{key}...")
            update_data = {
                "value": "updated_secret_value_67890",
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(
                    f"{self.base_url}/secrets/TEST_API_KEY_19L1",
                    headers=self.headers,
                    json=update_data,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: Got status {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print(f"   Updated secret: TEST_API_KEY_19L1")
            print("✅ PUT /v1/secrets/{key} passed")

            # Test 5: DELETE /v1/secrets/{key}
            print("\n6. Testing DELETE /v1/secrets/{key}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/secrets/TEST_API_KEY_19L1",
                    headers=self.headers,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: DELETE returned {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print(f"   Deleted secret: TEST_API_KEY_19L1")
            print("✅ DELETE /v1/secrets/{key} passed")

            # Test 6: Verify secret was deleted
            print("\n7. Verifying secret was deleted...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/secrets",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            final_count = len(data["data"]["secrets"])
            assert final_count == initial_count, "Secret count should return to initial"
            
            # Verify deleted secret is not in list
            secret_keys = [s["key"] for s in data["data"]["secrets"]]
            assert "TEST_API_KEY_19L1" not in secret_keys, "Deleted secret should not be in list"
            print("✅ Secret deletion verified")

            # Test 7: DELETE non-existent secret (should 404)
            print("\n8. Testing DELETE non-existent secret...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/secrets/NON_EXISTENT_SECRET",
                    headers=self.headers,
                )
            
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"
            data = response.json()
            assert data["success"] is False
            print("✅ 404 for non-existent secret")

            # Test 8: Authentication (without admin key)
            print("\n9. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/secrets",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19l1_secrets",
                success=True,
                checks=[
                    f"GET /v1/secrets passed ({initial_count} secrets)",
                    "POST /v1/secrets passed (created TEST_API_KEY_19L1)",
                    "Secret creation verified",
                    "PUT /v1/secrets/{key} passed (updated value)",
                    "DELETE /v1/secrets/{key} passed",
                    "Secret deletion verified",
                    "404 for non-existent secret",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19l1_secrets",
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
    test = TestSecrets()
    await test.test_19l1_secrets()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
