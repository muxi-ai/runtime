#!/usr/bin/env python3
"""Quick test for DELETE buffer memory endpoints."""

import asyncio
import httpx
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "e2e/tests"))

from common import BaseE2ETest


class TestDeleteBuffer(BaseE2ETest):
    """Test DELETE buffer operations."""

    def __init__(self):
        super().__init__(
            test_name="test_delete_buffer",
            test_description="Test DELETE buffer endpoints",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    async def test_delete(self):
        """Test DELETE buffer operations."""
        print("1. Setting up formation...")
        await self.setup_formation(
            formation_path=Path(__file__).parent / "e2e/tests/19_api/formation-api",
        )
        await self.formation.start_server(block=False)
        await asyncio.sleep(2)
        print("✅ Server ready\n")

        user_id = "0"
        session1 = "test_session_1"
        session2 = "test_session_2"

        # Create some buffer content
        print("2. Creating buffer content...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Session 1
            response = await client.post(
                f"{self.base_url}/chat",
                headers=self.headers,
                json={
                    "session_id": session1,
                    "message": "Hello session 1",
                    "stream": False,
                },
            )
            print(f"   Session 1 chat: {response.status_code}")
            
            # Session 2
            response = await client.post(
                f"{self.base_url}/chat",
                headers=self.headers,
                json={
                    "session_id": session2,
                    "message": "Hello session 2",
                    "stream": False,
                },
            )
            print(f"   Session 2 chat: {response.status_code}")

        # Check buffer
        print("\n3. Checking buffer before delete...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/memory/buffer/{user_id}",
                headers=self.headers,
            )
            print(f"   GET buffer status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Buffer messages: {len(data['data']['messages'])}")

        # Test DELETE session
        print(f"\n4. Testing DELETE /v1/memory/buffer/{user_id}/{session1}...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.base_url}/memory/buffer/{user_id}/{session1}",
                headers=self.headers,
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:300]}")

        # Test DELETE all
        print(f"\n5. Testing DELETE /v1/memory/buffer/{user_id}...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.base_url}/memory/buffer/{user_id}",
                headers=self.headers,
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:300]}")

        # Verify cleared
        print("\n6. Verifying buffer cleared...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/memory/buffer/{user_id}",
                headers=self.headers,
            )
            print(f"   GET buffer status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Buffer messages after delete: {len(data['data']['messages'])}")

        print("\n✅ Test complete!")
        await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestDeleteBuffer()
    await test.test_delete()


if __name__ == "__main__":
    asyncio.run(main())
