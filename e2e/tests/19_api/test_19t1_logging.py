#!/usr/bin/env python3
"""Test 19t1: Logging endpoints."""

import asyncio, time, sys, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter


class TestLogging(BaseE2ETest):
    def __init__(self):
        super().__init__(test_name="test_19t1_logging", test_description="Test logging endpoints", test_area="19_api")
        self.base_url, self.admin_key = "http://127.0.0.1:8271/v1", "test-admin-key-123"
        self.headers = {"X-Muxi-Admin-Key": self.admin_key, "Content-Type": "application/json"}

    async def test_19t1_logging(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(test_name="test_19t1_logging", description="Test logging endpoints")
        try:
            print("\n1. Setting up formation...")
            await self.setup_formation(formation_path=Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready")

            async with httpx.AsyncClient(timeout=30.0) as client:
                # GET /v1/logging
                print("\n2. Testing GET /v1/logging...")
                r = await client.get(f"{self.base_url}/logging", headers=self.headers)
                assert r.status_code == 200
                print("✅ GET /v1/logging passed")

                # GET /v1/logging/destinations
                print("\n3. Testing GET /v1/logging/destinations...")
                r = await client.get(f"{self.base_url}/logging/destinations", headers=self.headers)
                assert r.status_code == 200
                print("✅ GET /v1/logging/destinations passed")

                # POST /v1/logging/destinations
                print("\n4. Testing POST /v1/logging/destinations...")
                r = await client.post(f"{self.base_url}/logging/destinations", headers=self.headers, 
                    json={"type": "file", "path": "/tmp/test.log"})
                assert r.status_code in [200, 201, 400]
                print("✅ POST /v1/logging/destinations verified")

                # PATCH /v1/logging/destinations/{destination_id}
                print("\n5. Testing PATCH /v1/logging/destinations/{destination_id}...")
                r = await client.patch(f"{self.base_url}/logging/destinations/test_dest", headers=self.headers, 
                    json={"enabled": True})
                assert r.status_code in [200, 204, 404]
                print("✅ PATCH /v1/logging/destinations/{destination_id} verified")

                # DELETE /v1/logging/destinations/{destination_id}
                print("\n6. Testing DELETE /v1/logging/destinations/{destination_id}...")
                r = await client.delete(f"{self.base_url}/logging/destinations/test_dest", headers=self.headers)
                assert r.status_code in [200, 404]
                print("✅ DELETE /v1/logging/destinations/{destination_id} verified")

                # Auth test
                print("\n7. Testing authentication...")
                r = await client.get(f"{self.base_url}/logging", headers={"Content-Type": "application/json"})
                assert r.status_code == 401
                print("✅ Authentication enforced")

            formatter.print_test_result(test_name="test_19t1_logging", success=True, 
                checks=["GET logging", "GET destinations", "POST destination", "PATCH destination", "DELETE destination", "Auth enforced"], 
                transcript=[], duration=time.time()-start_time)
        except Exception as e:
            formatter.print_test_result(test_name="test_19t1_logging", success=False, checks=[f"Failed: {e}"], transcript=[], duration=time.time()-start_time)
            import traceback; traceback.print_exc()
            raise
        finally:
            if self.formation: await self.cleanup_formation()


async def main():
    await TestLogging().test_19t1_logging()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
