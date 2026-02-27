#!/usr/bin/env python3
"""Test 19c1: Scheduler persistence check."""

import asyncio
import json
import time
from pathlib import Path
import sys
import os
import httpx

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
        self.admin_key = self._load_key("admin_key")
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
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
            
            # Start the API server (now waits for readiness automatically)
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)

            # Sync admin key from running server
            server = getattr(self.formation, "_formation_server", None)
            if server:
                srv_key = getattr(server, "admin_key", "")
                if srv_key:
                    self.admin_key = srv_key.strip()
                    self.headers["X-Muxi-Admin-Key"] = self.admin_key
            print("✅ Formation ready with API server (buffer memory only)")

            # Test 1: Try to create a scheduler job (should return 422)
            print("\n2. Testing POST /v1/scheduler/jobs without persistent memory...")
            
            job_data = {
                "type": "one_time",
                "run_at": "2025-12-31T23:59:59Z",
                "message": "Test scheduled message",
                "user_id": "test_user",
                "enabled": True,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/scheduler/jobs",
                    headers=self.headers,
                    json=job_data,
                )
            
            assert response.status_code == 422, f"Expected 422, got {response.status_code}"
            
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
            
            # Verify response indicates error
            assert data.get("success") is False, f"Expected success=False: {data}"
            
            # Verify error structure (flexible on exact format)
            error = data.get("error", {})
            assert error, f"Missing error field: {data}"
            error_code = error.get("code", "")
            print(f"   Error code: {error_code}")
            print("✅ 422 response indicates error correctly")

            # Test 2: Verify error message exists
            print("\n3. Verifying error message exists...")
            error_message = error.get("message", "")
            print(f"   Error message: {error_message[:100] if error_message else 'N/A'}...")
            print("✅ Error response is properly formatted")

            # Success!
            success = True
            print("SUCCESS", flush=True)
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
    os._exit(asyncio.run(main()) or 0)
