#!/usr/bin/env python3
"""Test 19k1: Jobs endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestJobs(BaseE2ETest):
    """Test jobs endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19k1_jobs",
            test_description="Test job management endpoints",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    async def test_19k1_jobs(self):
        """Test jobs endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19k1_jobs",
            description="Test job management endpoints",
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

            user_id = "test_jobs_user_19k1"

            # Test 1: GET /v1/jobs/{user_id} (empty initially)
            print("\n2. Testing GET /v1/jobs/{user_id} (empty)...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/jobs/{user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            assert "jobs" in data["data"]
            initial_count = len(data["data"]["jobs"])
            print(f"   Initial job count: {initial_count}")
            print("✅ GET /v1/jobs/{user_id} passed")

            # Note: Jobs are typically created by the system during async operations
            # For this test, we'll check if we can list and delete them
            # If no jobs exist, we'll just verify the endpoints work

            if initial_count > 0:
                # Test 2: DELETE /v1/jobs/{user_id}/{job_id}
                print(f"\n3. Testing DELETE /v1/jobs/{{user_id}}/{{job_id}}...")
                job_id = data["data"]["jobs"][0]["id"]
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.delete(
                        f"{self.base_url}/jobs/{user_id}/{job_id}",
                        headers=self.headers,
                    )
                
                if response.status_code != 200:
                    print(f"   ERROR: DELETE returned {response.status_code}")
                    print(f"   Response: {response.text}")
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                print(f"   Deleted job: {job_id}")
                print("✅ DELETE /v1/jobs/{user_id}/{job_id} passed")

                # Test 3: Verify job was deleted
                print("\n4. Verifying job was deleted...")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self.base_url}/jobs/{user_id}",
                        headers=self.headers,
                    )
                
                assert response.status_code == 200
                data = response.json()
                final_count = len(data["data"]["jobs"])
                assert final_count == initial_count - 1, "Job count should decrease by 1"
                
                # Verify deleted job is not in list
                job_ids = [j["id"] for j in data["data"]["jobs"]]
                assert job_id not in job_ids, "Deleted job should not be in list"
                print("✅ Job deletion verified")
            else:
                print("\n   ℹ️  No jobs to test deletion (jobs are created by async operations)")

            # Test 4: DELETE non-existent job (should 404)
            print("\n5. Testing DELETE non-existent job...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/jobs/{user_id}/non_existent_job_id",
                    headers=self.headers,
                )
            
            # Should return 404 or 200 with success=false
            assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
            if response.status_code == 200:
                data = response.json()
                # If 200, should indicate failure
                assert data["success"] is False or "not found" in str(data).lower()
            print("✅ Proper handling of non-existent job")

            # Test 5: Authentication (without client key)
            print("\n6. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/jobs/{user_id}",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            checks = [
                f"GET /v1/jobs/{user_id} passed (count: {initial_count})",
            ]
            if initial_count > 0:
                checks.extend([
                    "DELETE /v1/jobs/{user_id}/{job_id} passed",
                    "Job deletion verified",
                ])
            else:
                checks.append("No jobs to test deletion (expected for new user)")
            checks.extend([
                "Proper handling of non-existent job",
                "Authentication enforced",
            ])
            
            formatter.print_test_result(
                test_name="test_19k1_jobs",
                success=True,
                checks=checks,
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19k1_jobs",
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
    test = TestJobs()
    await test.test_19k1_jobs()


if __name__ == "__main__":
    asyncio.run(main())
