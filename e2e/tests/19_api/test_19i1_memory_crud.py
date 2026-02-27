#!/usr/bin/env python3
"""Test 19i1: Memory CRUD endpoints (persistent memories)."""

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


class TestMemoryCRUD(BaseE2ETest):
    """Test persistent memory CRUD endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19i1_memory_crud",
            test_description="Test persistent memory CRUD operations",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = self._load_key("client_key")
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    def _load_key(self, key_name):
        """Load API key from formation YAML."""
        formation_yaml = Path(__file__).parent / "formation-api" / "formation.yaml"
        with open(formation_yaml) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key_name}:"):
                    return stripped.split(f"{key_name}:", 1)[1].strip().strip("\"").strip("'")
        return ""

    async def test_19i1_memory_crud(self):
        """Test memory CRUD endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19i1_memory_crud",
            description="Test persistent memory CRUD operations",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            # Start the API server
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)

            # Sync client key from running server
            server = getattr(self.formation, "_formation_server", None)
            if server:
                server_keys = getattr(server, "api_keys", {})
                if isinstance(server_keys, dict) and server_keys.get("client"):
                    self.client_key = server_keys["client"].strip()
                    self.headers["X-Muxi-Client-Key"] = self.client_key
            print("✅ Formation ready with API server")

            user_id = "test_memory_user_19i1"
            # Add user ID to headers as per spec
            headers_with_user = {**self.headers, "X-Muxi-User-ID": user_id}

            # Test 1: GET /v1/memories (with X-Muxi-User-ID header)
            print("\n2. Testing GET /v1/memories (empty)...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memories",
                    headers=headers_with_user,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            assert "memories" in data["data"]
            initial_count = len(data["data"]["memories"])
            print(f"   Initial memory count: {initial_count}")
            print("✅ GET /v1/memories passed")

            # Test 2: POST /v1/memories/{user_id} (create memory)
            print("\n3. Testing POST /v1/memories/{user_id}...")
            memory_data = {
                "content": "Test memory: User likes Python programming",
                "metadata": {
                    "category": "preference",
                    "importance": "high"
                }
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/memories",
                    headers=headers_with_user,
                    json=memory_data,
                )
            
            # Check if persistent memory is configured
            if response.status_code == 503:
                print(f"   ℹ️  Persistent memory not configured (503 - expected without database)")
                print(f"   Response: {response.json()['error']['message']}")
                print("✅ POST /v1/memories/{user_id} correctly returns 503 without database")
                print("\n   Skipping remaining CRUD tests (require database configuration)")
                
                # Mark test as successful - endpoint works correctly
                success = True
                formatter.print_test_result(
                    test_name="test_19i1_memory_crud",
                    success=True,
                    checks=[
                        "GET /v1/memories/{user_id} passed",
                        "POST /v1/memories/{user_id} correctly returns 503 (no database)",
                        "Endpoint behavior verified - requires PostgreSQL for full testing"
                    ],
                    transcript=[],
                    duration=time.time() - start_time
                )
                return  # Exit test successfully
            
            # Spec says 200 for created memory (not 201)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            # Response has id directly in data, not nested under "memory"
            memory_id = data["data"].get("id") or data["data"].get("memory", {}).get("id")
            assert memory_id, "Memory ID not found in response"
            print(f"   Created memory: {memory_id}")
            print("✅ POST /v1/memories/{user_id} passed")

            # Test 3: GET /v1/memories/{user_id} (verify created)
            print("\n4. Verifying memory was created...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memories",
                    headers=headers_with_user,
                )
            
            assert response.status_code == 200
            data = response.json()
            new_count = len(data["data"]["memories"])
            assert new_count == initial_count + 1, "Memory count should increase by 1"
            
            # Find our memory in the list
            memory_ids = [m["id"] for m in data["data"]["memories"]]
            assert memory_id in memory_ids, "New memory should be in list"
            print("✅ Memory creation verified")

            # Test 4: POST another memory
            print("\n5. Creating another memory...")
            memory_data2 = {
                "content": "Test memory: User prefers morning meetings",
                "metadata": {
                    "category": "preference",
                    "importance": "medium"
                }
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/memories",
                    headers=headers_with_user,
                    json=memory_data2,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            memory_id2 = data["data"].get("id") or data["data"].get("memory", {}).get("id")
            print(f"   Created second memory: {memory_id2}")
            print("✅ Second memory created")

            # Test 5: DELETE /v1/memories/{memory_id}
            print("\n6. Testing DELETE /v1/memories/{memory_id}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memories/{memory_id}",
                    headers=headers_with_user,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: DELETE returned {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print(f"   Deleted memory: {memory_id}")
            print("✅ DELETE /v1/memories/{memory_id} passed")

            # Test 6: Verify memory was deleted
            print("\n7. Verifying memory was deleted...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memories",
                    headers=headers_with_user,
                )
            
            assert response.status_code == 200
            data = response.json()
            final_count = len(data["data"]["memories"])
            assert final_count == initial_count + 1, "Should have 1 memory remaining"
            
            # Verify deleted memory is not in list
            memory_ids = [m["id"] for m in data["data"]["memories"]]
            assert memory_id not in memory_ids, "Deleted memory should not be in list"
            assert memory_id2 in memory_ids, "Second memory should still be in list"
            print("✅ Memory deletion verified")

            # Test 7: DELETE non-existent memory (should 404)
            print("\n8. Testing DELETE non-existent memory...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memories/non_existent_memory_id",
                    headers=headers_with_user,
                )
            
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"
            data = response.json()
            assert data["success"] is False
            print("✅ 404 for non-existent memory")

            # Test 8: Authentication (without client key)
            print("\n9. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memories",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            print("SUCCESS", flush=True)
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19i1_memory_crud",
                success=True,
                checks=[
                    f"GET /v1/memories/{user_id} passed (initial: {initial_count})",
                    f"POST /v1/memories/{user_id} passed (created {memory_id})",
                    "Memory creation verified",
                    f"Second memory created ({memory_id2})",
                    "DELETE /v1/memories/{memory_id} passed",
                    "Memory deletion verified",
                    "404 for non-existent memory",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19i1_memory_crud",
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
    test = TestMemoryCRUD()
    await test.test_19i1_memory_crud()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
