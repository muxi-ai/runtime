#!/usr/bin/env python3
"""Test 19o1: Memory admin endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestMemoryAdmin(BaseE2ETest):
    """Test memory admin endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19o1_memory_admin",
            test_description="Test memory admin management endpoints",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {"X-Muxi-Admin-Key": self.admin_key, "Content-Type": "application/json"}

    async def test_19o1_memory_admin(self):
        """Test memory admin endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(test_name="test_19o1_memory_admin", description="Test memory admin management endpoints")

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(formation_path=Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready")

            # GET /v1/memory
            print("\n2. Testing GET /v1/memory...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.base_url}/memory", headers=self.headers)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print("✅ GET /v1/memory passed")

            # GET /v1/memory/buffers
            print("\n3. Testing GET /v1/memory/buffers...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.base_url}/memory/buffers", headers=self.headers)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print("✅ GET /v1/memory/buffers passed")

            # DELETE /v1/memory/buffers
            print("\n4. Testing DELETE /v1/memory/buffers...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(f"{self.base_url}/memory/buffers", headers=self.headers)
            assert response.status_code == 200
            print("✅ DELETE /v1/memory/buffers passed")

            # PATCH /v1/memory
            print("\n5. Testing PATCH /v1/memory...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(f"{self.base_url}/memory", headers=self.headers, json={"config": {"buffer_size": 100}})
            # Might return 200 or 204
            assert response.status_code in [200, 204]
            print("✅ PATCH /v1/memory passed")

            # DELETE /v1/memory/{item}
            print("\n6. Testing DELETE /v1/memory/{item}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(f"{self.base_url}/memory/test_item", headers=self.headers)
            # Expected to fail gracefully
            assert response.status_code in [200, 404]
            print("✅ DELETE /v1/memory/{item} endpoint verified")

            # Auth test
            print("\n7. Testing authentication...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.base_url}/memory", headers={"Content-Type": "application/json"})
            assert response.status_code == 401
            print("✅ Authentication enforced")

            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19o1_memory_admin",
                success=True,
                checks=[
                    "GET /v1/memory passed",
                    "GET /v1/memory/buffers passed",
                    "DELETE /v1/memory/buffers passed",
                    "PATCH /v1/memory passed",
                    "DELETE /v1/memory/{item} verified",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(test_name="test_19o1_memory_admin", success=False, checks=[f"Failed: {str(e)}"], transcript=[], duration=elapsed_time)
            import traceback
            traceback.print_exc()
            raise
        finally:
            if self.formation:
                await self.cleanup_formation()


async def main():
    test = TestMemoryAdmin()
    await test.test_19o1_memory_admin()


if __name__ == "__main__":
    asyncio.run(main())
