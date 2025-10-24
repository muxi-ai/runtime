#!/usr/bin/env python3
"""Test 19r1: A2A (Agent-to-Agent) endpoints."""

import asyncio, time, sys, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter


class TestA2A(BaseE2ETest):
    def __init__(self):
        super().__init__(test_name="test_19r1_a2a", test_description="Test A2A endpoints", test_area="19_api")
        self.base_url, self.admin_key = "http://127.0.0.1:8271/v1", "test-admin-key-123"
        self.headers = {"X-Muxi-Admin-Key": self.admin_key, "Content-Type": "application/json"}

    async def test_19r1_a2a(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(test_name="test_19r1_a2a", description="Test A2A endpoints")
        try:
            print("\n1. Setting up formation...")
            await self.setup_formation(formation_path=Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready")

            async with httpx.AsyncClient(timeout=30.0) as client:
                # GET /v1/a2a
                print("\n2. Testing GET /v1/a2a...")
                r = await client.get(f"{self.base_url}/a2a", headers=self.headers)
                assert r.status_code == 200
                print("✅ GET /v1/a2a passed")

                # PATCH /v1/a2a/outbound
                print("\n3. Testing PATCH /v1/a2a/outbound...")
                r = await client.patch(f"{self.base_url}/a2a/outbound", headers=self.headers, json={"config": {}})
                assert r.status_code in [200, 204]
                print("✅ PATCH /v1/a2a/outbound passed")

                # DELETE /v1/a2a/outbound/{item}
                print("\n4. Testing DELETE /v1/a2a/outbound/{item}...")
                r = await client.delete(f"{self.base_url}/a2a/outbound/test_item", headers=self.headers)
                assert r.status_code in [200, 404]
                print("✅ DELETE /v1/a2a/outbound/{item} verified")

                # Auth test
                print("\n5. Testing authentication...")
                r = await client.get(f"{self.base_url}/a2a", headers={"Content-Type": "application/json"})
                assert r.status_code == 401
                print("✅ Authentication enforced")

            formatter.print_test_result(test_name="test_19r1_a2a", success=True, 
                checks=["GET a2a", "PATCH outbound", "DELETE outbound item", "Auth enforced"], 
                transcript=[], duration=time.time()-start_time)
        except Exception as e:
            formatter.print_test_result(test_name="test_19r1_a2a", success=False, checks=[f"Failed: {e}"], transcript=[], duration=time.time()-start_time)
            import traceback; traceback.print_exc()
            raise
        finally:
            if self.formation: await self.cleanup_formation()


async def main():
    await TestA2A().test_19r1_a2a()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
