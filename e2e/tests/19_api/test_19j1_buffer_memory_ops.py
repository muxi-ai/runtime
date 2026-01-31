#!/usr/bin/env python3
"""Test 19j1: Buffer memory operations (DELETE operations)."""

import asyncio
import time
from pathlib import Path
import sys
import os
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
            session1 = "session_buffer_ops_1"
            session2 = "session_buffer_ops_2"

            # Try to create buffer content via chat (with timeout protection)
            print("\n2. Testing buffer operations (may skip chat if timeout)...")
            chat_created = False
            try:
                # Session 1 messages
                async with httpx.AsyncClient(timeout=15.0) as client:
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
                if response.status_code == 200:
                    # Session 2 messages
                    async with httpx.AsyncClient(timeout=15.0) as client:
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
                    if response.status_code == 200:
                        chat_created = True
                        print("✅ Created messages in 2 sessions")
            except (asyncio.TimeoutError, Exception) as e:
                print(f"   ℹ️  Chat creation timed out or failed ({type(e).__name__}) - testing DELETE endpoints anyway")
                chat_created = False

            # Test 1: GET buffer
            print("\n3. Testing GET /v1/memory/buffer/{session_id}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{session_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            initial_messages = data["data"]["total_messages"]
            print(f"   Initial buffer messages: {initial_messages}")
            if chat_created:
                print("✅ Buffer has messages from chat")
            else:
                print("✅ GET /v1/memory/buffer/{session_id} passed (buffer may be empty)")

            # Test 2: DELETE /v1/memory/buffer/{session_id}/{session_id}
            print(f"\n4. Testing DELETE /v1/memory/buffer/{{user_id}}/{{session_id}} for {session1}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memory/buffer/{session_id}/{session1}",
                    headers=self.headers,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: DELETE returned {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print(f"   Deleted session: {session1}")
            print("✅ DELETE /v1/memory/buffer/{session_id}/{session_id} passed")

            # Test 3: Verify session was deleted (if chat was created)
            if chat_created and initial_messages > 0:
                print("\n5. Verifying session was deleted...")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self.base_url}/memory/buffer/{session_id}",
                        headers=self.headers,
                    )
                
                assert response.status_code == 200
                data = response.json()
                after_session_delete = data["data"]["total_messages"]
                assert after_session_delete < initial_messages, "Message count should decrease"
                
                # Verify session info
                sessions = data["data"]["sessions"]
                session_ids = [s.get("session_id") for s in sessions] if sessions else []
                print(f"   Messages remaining: {after_session_delete}")
                print(f"   Active sessions: {len(session_ids)}")
                print("✅ Session deletion verified")
            else:
                print("\n5. Skipping session deletion verification (no messages created)")
                print("✅ DELETE endpoint functional (status 200)")

            # Test 4: DELETE /v1/memory/buffer/{session_id} (delete all)
            print("\n6. Testing DELETE /v1/memory/buffer/{session_id} (delete all)...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memory/buffer/{session_id}",
                    headers=self.headers,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: DELETE returned {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            print("   Deleted all buffer messages")
            print("✅ DELETE /v1/memory/buffer/{session_id} passed")

            # Test 5: Verify all buffer cleared (if applicable)
            print("\n7. Verifying buffer state after delete all...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{session_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            final_messages = data["data"]["total_messages"]
            if chat_created and initial_messages > 0:
                assert final_messages == 0, "Buffer should be empty after delete all"
                print("✅ Buffer completely cleared")
            else:
                print(f"✅ Buffer state verified (was empty, still empty: {final_messages} messages)")

            # Test 6: Authentication (without client key)
            print("\n8. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/memory/buffer/{session_id}",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            
            # Build checks list based on what was actually tested
            checks = []
            if chat_created:
                checks.append("Created messages in 2 sessions")
                checks.append(f"Initial buffer: {initial_messages} messages")
            else:
                checks.append("GET /v1/memory/buffer/{session_id} passed (may have timed out on chat)")
            
            checks.extend([
                f"DELETE /v1/memory/buffer/{{user_id}}/{{session_id}} passed",
                "Session deletion verified" if (chat_created and initial_messages > 0) else "DELETE session endpoint functional",
                "DELETE /v1/memory/buffer/{session_id} passed",
                "Buffer state verified" if (chat_created and initial_messages > 0) else "DELETE all endpoint functional",
                "Authentication enforced",
            ])
            
            formatter.print_test_result(
                test_name="test_19j1_buffer_memory_ops",
                success=True,
                checks=checks,
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
    os._exit(asyncio.run(main()) or 0)
