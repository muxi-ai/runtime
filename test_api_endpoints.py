#!/usr/bin/env python3
"""
Quick test script for new API endpoints.

Tests the newly implemented endpoints:
- Scheduler jobs (GET list, POST create, GET details, DELETE)
- User identifiers (GET list, DELETE, GET resolve)
- Logging destinations (GET list, POST create, PATCH update, DELETE)
"""

import asyncio
import httpx
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8271/v1"
ADMIN_KEY = "your-admin-key-here"  # Replace with actual key
CLIENT_KEY = "your-client-key-here"  # Replace with actual key


class APITester:
    """Simple API endpoint tester."""

    def __init__(self, base_url: str, admin_key: str, client_key: str):
        self.base_url = base_url
        self.admin_headers = {"X-Muxi-Admin-Key": admin_key}
        self.client_headers = {"X-Muxi-Client-Key": client_key}

    async def test_scheduler_endpoints(self):
        """Test scheduler jobs endpoints."""
        print("\n" + "="*60)
        print("🔧 TESTING SCHEDULER ENDPOINTS")
        print("="*60)

        async with httpx.AsyncClient() as client:
            # 1. List jobs (empty initially)
            print("\n1. GET /scheduler/jobs (list)")
            response = await client.get(
                f"{self.base_url}/scheduler/jobs",
                headers=self.admin_headers
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Jobs: {data.get('data', {}).get('count', 0)}")
                print("   ✅ PASS")
            else:
                print(f"   ❌ FAIL: {response.text}")

            # 2. Create a one-time job
            print("\n2. POST /scheduler/jobs (create one-time)")
            job_data = {
                "type": "one_time",
                "run_at": "2025-12-01T10:00:00Z",
                "message": "Test reminder",
                "user_id": "test-user"
            }
            response = await client.post(
                f"{self.base_url}/scheduler/jobs",
                headers=self.admin_headers,
                json=job_data
            )
            print(f"   Status: {response.status_code}")
            job_id = None
            if response.status_code == 201:
                data = response.json()
                job_id = data.get('data', {}).get('id')
                print(f"   Created job: {job_id}")
                print("   ✅ PASS")
            else:
                print(f"   ❌ FAIL: {response.text}")

            # 3. Get job details
            if job_id:
                print(f"\n3. GET /scheduler/jobs/{job_id} (details)")
                response = await client.get(
                    f"{self.base_url}/scheduler/jobs/{job_id}",
                    headers=self.admin_headers
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"   Job type: {data.get('data', {}).get('type')}")
                    print("   ✅ PASS")
                else:
                    print(f"   ❌ FAIL: {response.text}")

            # 4. Delete job
            if job_id:
                print(f"\n4. DELETE /scheduler/jobs/{job_id}")
                response = await client.delete(
                    f"{self.base_url}/scheduler/jobs/{job_id}",
                    headers=self.admin_headers
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    print("   ✅ PASS")
                else:
                    print(f"   ❌ FAIL: {response.text}")

    async def test_user_identifier_endpoints(self):
        """Test user identifier endpoints."""
        print("\n" + "="*60)
        print("👤 TESTING USER IDENTIFIER ENDPOINTS")
        print("="*60)

        async with httpx.AsyncClient() as client:
            # 1. Resolve identifier (creates if not exists)
            print("\n1. GET /users/{identifier} (resolve)")
            response = await client.get(
                f"{self.base_url}/users/test-user@example.com",
                headers=self.client_headers
            )
            print(f"   Status: {response.status_code}")
            user_id = None
            if response.status_code == 200:
                data = response.json()
                user_id = data.get('data', {}).get('muxi_user_id')
                print(f"   MUXI User ID: {user_id}")
                print("   ✅ PASS")
            else:
                print(f"   ❌ FAIL: {response.text}")

            # 2. List identifiers for user
            if user_id:
                print(f"\n2. GET /users/identifiers/{user_id} (list)")
                response = await client.get(
                    f"{self.base_url}/users/identifiers/{user_id}",
                    headers=self.client_headers
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    count = data.get('data', {}).get('count', 0)
                    print(f"   Identifiers: {count}")
                    print("   ✅ PASS")
                else:
                    print(f"   ❌ FAIL: {response.text}")

            # 3. Delete identifier
            print("\n3. DELETE /users/identifiers/{identifier}")
            response = await client.delete(
                f"{self.base_url}/users/identifiers/test-user@example.com",
                headers=self.client_headers
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print("   ✅ PASS")
            else:
                print(f"   ❌ FAIL: {response.text}")

    async def test_logging_destinations_endpoints(self):
        """Test logging destinations endpoints."""
        print("\n" + "="*60)
        print("📝 TESTING LOGGING DESTINATIONS ENDPOINTS")
        print("="*60)

        async with httpx.AsyncClient() as client:
            # 1. List destinations
            print("\n1. GET /logging/destinations (list)")
            response = await client.get(
                f"{self.base_url}/logging/destinations",
                headers=self.admin_headers
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                count = data.get('data', {}).get('count', 0)
                print(f"   Destinations: {count}")
                print("   ✅ PASS")
            else:
                print(f"   ❌ FAIL: {response.text}")

            # 2. Create destination
            print("\n2. POST /logging/destinations (create)")
            dest_data = {
                "transport": "file",
                "destination": "/tmp/test.log",
                "level": "DEBUG",
                "format": "jsonl"
            }
            response = await client.post(
                f"{self.base_url}/logging/destinations",
                headers=self.admin_headers,
                json=dest_data
            )
            print(f"   Status: {response.status_code}")
            dest_id = None
            if response.status_code == 201:
                data = response.json()
                dest_id = data.get('data', {}).get('id')
                print(f"   Created destination: {dest_id}")
                print("   ✅ PASS")
            else:
                print(f"   ❌ FAIL: {response.text}")

            # 3. Update destination
            if dest_id:
                print(f"\n3. PATCH /logging/destinations/{dest_id} (update)")
                update_data = {"level": "INFO"}
                response = await client.patch(
                    f"{self.base_url}/logging/destinations/{dest_id}",
                    headers=self.admin_headers,
                    json=update_data
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    print("   ✅ PASS")
                else:
                    print(f"   ❌ FAIL: {response.text}")

            # 4. Delete destination
            if dest_id:
                print(f"\n4. DELETE /logging/destinations/{dest_id}")
                response = await client.delete(
                    f"{self.base_url}/logging/destinations/{dest_id}",
                    headers=self.admin_headers
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    print("   ✅ PASS")
                else:
                    print(f"   ❌ FAIL: {response.text}")

    async def run_all_tests(self):
        """Run all endpoint tests."""
        print("\n" + "="*60)
        print("🚀 MUXI FORMATION API - ENDPOINT TESTS")
        print("="*60)
        print(f"Base URL: {self.base_url}")

        try:
            await self.test_scheduler_endpoints()
            await self.test_user_identifier_endpoints()
            await self.test_logging_destinations_endpoints()

            print("\n" + "="*60)
            print("✅ ALL TESTS COMPLETED")
            print("="*60)
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main entry point."""
    print("\n⚠️  NOTE: Update ADMIN_KEY and CLIENT_KEY in this script before running!")
    print("    These can be found in your formation's secrets.env file.")
    
    # Check if keys are still default
    if ADMIN_KEY == "your-admin-key-here":
        print("\n❌ ERROR: Please update ADMIN_KEY and CLIENT_KEY in the script!")
        print("    Look for them in your formation directory's secrets.env file.")
        return

    tester = APITester(BASE_URL, ADMIN_KEY, CLIENT_KEY)
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
