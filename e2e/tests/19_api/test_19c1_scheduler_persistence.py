#!/usr/bin/env python3
"""Test 19c1: Scheduler persistence check."""

import asyncio
import json
import time
from pathlib import Path
import sys
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestSchedulerPersistence(BaseE2ETest):
    """Test scheduler persistence check."""

    def __init__(self):
        super().__init__(
            test_name="test_19c1_scheduler_persistence",
            test_description="Test 422 response for SQLite/no persistent memory",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "Content-Type": "application/json",
        }

    async def test_19c1_scheduler_persistence(self):
        """Test scheduler persistence check."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19c1_scheduler_persistence",
            description="Test 422 response for SQLite/no persistent memory",
        )

        try:
            # Setup formation (buffer memory only - no persistent memory)
            print("\n1. Setting up formation with buffer memory only...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            print("✅ Formation ready with API server (buffer memory only)")

            # Wait for server to be fully ready
            await asyncio.sleep(2)

            # Test 1: Try to create a scheduler job (should return 422)
            print("\n2. Testing POST /v1/scheduler/jobs without persistent memory...")
            
            job_data = {
                "type": "one_time",
                "run_at": "2025-12-31T23:59:59Z",
                "message": "Test scheduled message",
                "user_id": "test_user",
                "enabled": True,
            }
            
            response = requests.post(
                f"{self.base_url}/scheduler/jobs",
                headers=self.headers,
                json=job_data,
            )
            
            assert response.status_code == 422, f"Expected 422, got {response.status_code}"
            
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
            
            # Verify response structure matches spec
            assert data["object"] == "error", f"Wrong object type: {data['object']}"
            assert data["type"] == "error.validation", f"Wrong event type: {data['type']}"
            assert data["success"] is False, "Success should be False"
            
            # Verify error structure
            assert "error" in data, "Missing error field"
            assert data["error"]["code"] == "UNPROCESSABLE_ENTITY", f"Wrong error code: {data['error']['code']}"
            assert "persistent memory" in data["error"]["message"].lower(), "Missing persistent memory in message"
            
            # Verify error.data field (critical for spec compliance)
            assert data["error"]["data"] is not None, "error.data should not be None"
            assert "reason" in data["error"]["data"], "Missing 'reason' in error.data"
            assert "required" in data["error"]["data"], "Missing 'required' in error.data"
            assert "current_memory_type" in data["error"]["data"], "Missing 'current_memory_type' in error.data"
            
            # Verify data field is empty dict (per spec)
            assert data["data"] == {}, f"data should be empty dict, got: {data['data']}"
            
            print("✅ 422 response format matches spec exactly")
            print(f"   Error code: {data['error']['code']}")
            print(f"   Reason: {data['error']['data']['reason']}")
            print(f"   Required: {data['error']['data']['required']}")
            print(f"   Current memory type: {data['error']['data']['current_memory_type']}")

            # Test 2: Verify error message is helpful
            print("\n3. Verifying error message is helpful...")
            error_message = data["error"]["message"]
            assert "PostgreSQL" in data["error"]["data"]["required"] or "MySQL" in data["error"]["data"]["required"]
            assert "SQLite" in data["error"]["data"]["current_memory_type"] or "none" in data["error"]["data"]["current_memory_type"]
            print("✅ Error message provides clear guidance")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19c1_scheduler_persistence",
                success=True,
                checks=[
                    "422 response format matches spec exactly",
                    "Error message provides clear guidance",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19c1_scheduler_persistence",
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
    test = TestSchedulerPersistence()
    await test.test_19c1_scheduler_persistence()


if __name__ == "__main__":
    asyncio.run(main())
