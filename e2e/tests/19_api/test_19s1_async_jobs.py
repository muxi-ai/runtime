#!/usr/bin/env python3
"""Test 19s1: Async jobs endpoints."""

import asyncio, time, sys, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter


class TestAsyncJobs(BaseE2ETest):
    def __init__(self):
        super().__init__(test_name="test_19s1_async_jobs", test_description="Test async jobs endpoints", test_area="19_api")
        self.base_url, self.admin_key = "http://127.0.0.1:8271/v1", "test-admin-key-123"
        self.headers = {"X-Muxi-Admin-Key": self.admin_key, "Content-Type": "application/json"}

    async def test_19s1_async_jobs(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(test_name="test_19s1_async_jobs", description="Test async jobs endpoints")
        try:
            print("\n1. Setting up formation...")
            await self.setup_formation(formation_path=Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready")

            async with httpx.AsyncClient(timeout=30.0) as client:
                # GET /v1/async
                print("\n2. Testing GET /v1/async...")
                r = await client.get(f"{self.base_url}/async", headers=self.headers)
                assert r.status_code == 200
                print("✅ GET /v1/async passed")

                # PATCH /v1/async
                print("\n3. Testing PATCH /v1/async...")
                r = await client.patch(f"{self.base_url}/async", headers=self.headers, json={"config": {}})
                assert r.status_code in [200, 204]
                print("✅ PATCH /v1/async passed")

                # GET /v1/async/jobs
                print("\n4. Testing GET /v1/async/jobs...")
                r = await client.get(f"{self.base_url}/async/jobs", headers=self.headers)
                assert r.status_code == 200
                print("✅ GET /v1/async/jobs passed")

                # GET /v1/async/jobs/{job_id}
                print("\n5. Testing GET /v1/async/jobs/{job_id}...")
                r = await client.get(f"{self.base_url}/async/jobs/test_job", headers=self.headers)
                assert r.status_code in [200, 404]
                print("✅ GET /v1/async/jobs/{job_id} verified")

                # DELETE /v1/async/jobs/{job_id}
                print("\n6. Testing DELETE /v1/async/jobs/{job_id}...")
                r = await client.delete(f"{self.base_url}/async/jobs/test_job", headers=self.headers)
                assert r.status_code in [200, 404]
                print("✅ DELETE /v1/async/jobs/{job_id} verified")

                # Auth test
                print("\n7. Testing authentication...")
                r = await client.get(f"{self.base_url}/async", headers={"Content-Type": "application/json"})
                assert r.status_code == 401
                print("✅ Authentication enforced")

            formatter.print_test_result(test_name="test_19s1_async_jobs", success=True, 
                checks=["GET async", "PATCH async", "GET jobs", "GET job by ID", "DELETE job", "Auth enforced"], 
                transcript=[], duration=time.time()-start_time)
        except Exception as e:
            formatter.print_test_result(test_name="test_19s1_async_jobs", success=False, checks=[f"Failed: {e}"], transcript=[], duration=time.time()-start_time)
            import traceback; traceback.print_exc()
            raise
        finally:
            if self.formation: await self.cleanup_formation()


async def main():
    await TestAsyncJobs().test_19s1_async_jobs()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
