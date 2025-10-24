#!/usr/bin/env python3
"""Test 19h1: Users endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestUsers(BaseE2ETest):
    """Test users endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19h1_users",
            test_description="Test user management endpoints",
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
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19h1_users",
            description="Test user management endpoints",
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

            # First, create a user by making a chat request
            print("\n2. Creating user via chat (to generate identifier)...")
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json={
                        "user_id": "test_user_19h1",
                        "session_id": "session_19h1",
                        "message": "Hello",
                        "stream": False,
                    },
                )
            
            assert response.status_code == 200
            print("✅ User created via chat")

            # Test 1: GET /v1/users/identifiers/{user_id}
            print("\n3. Testing GET /v1/users/identifiers/{user_id}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/users/identifiers/test_user_19h1",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            assert "identifiers" in data["data"]
            print(f"   Found {len(data['data']['identifiers'])} identifiers")
            print("✅ GET /v1/users/identifiers/{user_id} passed")

            # Test 2: GET /v1/users/{identifier}
            print("\n4. Testing GET /v1/users/{identifier}...")
            # Get first identifier from previous response
            if data["data"]["identifiers"]:
                identifier = data["data"]["identifiers"][0]
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self.base_url}/users/{identifier}",
                        headers=self.headers,
                    )
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert "user" in data["data"]
                print(f"   User data retrieved for identifier: {identifier}")
                print("✅ GET /v1/users/{identifier} passed")
            else:
                print("   ⚠️  No identifiers to test user retrieval")

            # Test 3: DELETE /v1/users/identifiers/{identifier}
            print("\n5. Testing DELETE /v1/users/identifiers/{identifier}...")
            # Create another user to delete
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json={
                        "user_id": "test_user_delete_19h1",
                        "session_id": "session_delete_19h1",
                        "message": "Hello",
                        "stream": False,
                    },
                )
            
            # Get identifiers for this user
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/users/identifiers/test_user_delete_19h1",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            
            if data["data"]["identifiers"]:
                identifier_to_delete = data["data"]["identifiers"][0]
                
                # Delete the identifier
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.delete(
                        f"{self.base_url}/users/identifiers/{identifier_to_delete}",
                        headers=self.headers,
                    )
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                print(f"   Deleted identifier: {identifier_to_delete}")
                print("✅ DELETE /v1/users/identifiers/{identifier} passed")
            else:
                print("   ⚠️  No identifiers to test deletion")

            # Test 4: Authentication (without client key)
            print("\n6. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/users/identifiers/test_user_19h1",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19h1_users",
                success=True,
                checks=[
                    "User created via chat",
                    "GET /v1/users/identifiers/{user_id} passed",
                    "GET /v1/users/{identifier} passed",
                    "DELETE /v1/users/identifiers/{identifier} passed",
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
            # Cleanup
            if self.formation:
                await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestUsers()
    await test.test_19h1_users()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
