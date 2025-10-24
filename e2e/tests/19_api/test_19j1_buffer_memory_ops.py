#!/usr/bin/env python3
"""Test 19j1: Buffer memory operations (DELETE operations)."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestBufferMemoryOps(BaseE2ETest):
    """Test buffer memory DELETE operations."""

    def __init__(self):
        super().__init__(
            test_name="test_19j1_buffer_memory_ops",
            test_description="Test buffer memory DELETE operations",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    async def test_19j1_buffer_memory_ops(self):
        """Test buffer memory DELETE operations."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19j1_buffer_memory_ops",
            description="Test buffer memory DELETE operations",
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

            user_id = "0"  # Single-user mode

            # Create some buffer content via chat
            print("\n2. Creating buffer content via chat...")
            session1 = "session_buffer_ops_1"
            session2 = "session_buffer_ops_2"
            
            # Session 1 messages
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json={
                        "user_id": user_id,
                        "session_id": session1,
                        "message": "Hello session 1",
                        "stream": False,
                    },
                )
            assert response.status_code == 200
            
            # Session 2 messages
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json={
                        "user_id": user_id,
                        "session_id": session2,
                        "message": "Hello session 2",
                        "stream": False,
                    },
                )
            assert response.status_code == 200
            print("✅ Created messages in 2 sessions")

            # Test 1: GET buffer (should have messages from both sessions)
            print("\n3. Testing GET /v1/memory/buffer/{user_id} (before delete)...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            initial_messages = len(data["data"]["messages"])
            print(f"   Initial buffer messages: {initial_messages}")
            print("✅ Buffer has messages from multiple sessions")

            # Test 2: DELETE /v1/memory/buffer/{user_id}/{session_id}
            print(f"\n4. Testing DELETE /v1/memory/buffer/{{user_id}}/{{session_id}} for {session1}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memory/buffer/{user_id}/{session1}",
                    headers=self.headers,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: DELETE returned {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print(f"   Deleted session: {session1}")
            print("✅ DELETE /v1/memory/buffer/{user_id}/{session_id} passed")

            # Test 3: Verify session was deleted
            print("\n5. Verifying session was deleted...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            after_session_delete = len(data["data"]["messages"])
            assert after_session_delete < initial_messages, "Message count should decrease"
            
            # Verify session2 messages still exist
            session_ids = set(msg.get("metadata", {}).get("session_id") for msg in data["data"]["messages"])
            assert session1 not in session_ids or session_ids == {None}, f"Session {session1} should be deleted"
            assert session2 in session_ids, f"Session {session2} should still exist"
            print(f"   Messages remaining: {after_session_delete}")
            print("✅ Session deletion verified")

            # Test 4: DELETE /v1/memory/buffer/{user_id} (delete all)
            print("\n6. Testing DELETE /v1/memory/buffer/{user_id} (delete all)...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memory/buffer/{user_id}",
                    headers=self.headers,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: DELETE returned {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print("   Deleted all buffer messages")
            print("✅ DELETE /v1/memory/buffer/{user_id} passed")

            # Test 5: Verify all buffer cleared
            print("\n7. Verifying buffer was cleared...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            final_messages = len(data["data"]["messages"])
            assert final_messages == 0, "Buffer should be empty"
            print("✅ Buffer completely cleared")

            # Test 6: Authentication (without client key)
            print("\n8. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memory/buffer/{user_id}",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19j1_buffer_memory_ops",
                success=True,
                checks=[
                    "Created messages in 2 sessions",
                    f"Initial buffer: {initial_messages} messages",
                    f"DELETE session {session1} passed",
                    "Session deletion verified",
                    "DELETE all buffer messages passed",
                    "Buffer completely cleared",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19j1_buffer_memory_ops",
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
    test = TestBufferMemoryOps()
    await test.test_19j1_buffer_memory_ops()


if __name__ == "__main__":
    asyncio.run(main())
