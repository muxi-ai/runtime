#!/usr/bin/env python3
"""Test 19g1: Memory and sessions endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestMemorySessions(BaseE2ETest):
    """Test memory and sessions endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19g1_memory_sessions",
            test_description="Test memory buffer and sessions management",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }
        self.test_user_id = "test_memory_user"
        self.test_session_id = "test_session_001"

    async def test_19g1_memory_sessions(self):
        """Test memory and sessions endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19g1_memory_sessions",
            description="Test memory buffer and sessions management",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            # Start the API server
            await self.formation.start_server(block=False)
            print("✅ Formation ready with API server")

            # Test 1: Get buffer memory for user (initially empty)
            print("\n2. Testing GET /v1/memory/buffer/{user_id}...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{self.test_user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            assert data["object"] == "buffer_memory"
            assert data["type"] == "buffer.retrieved"
            assert data["success"] is True
            assert "messages" in data["data"]
            assert "count" in data["data"]
            
            initial_message_count = data["data"]["count"]
            print(f"   Initial message count: {initial_message_count}")
            print("✅ GET /v1/memory/buffer/{user_id} passed")

            # Test 2: Send a chat message to create buffer memory
            print("\n3. Sending chat to create buffer memory...")
            chat_request = {
                "message": "Hello, this is a test message for memory.",
                "user_id": self.test_user_id,
                "session_id": self.test_session_id,
            }
            
            # Consume the stream to complete the chat
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json=chat_request,
                    timeout=30.0,
                ) as response:
                    assert response.status_code == 200
                    async for line in response.aiter_lines():
                        if line.startswith("data: [DONE]"):
                            break
            
            print("✅ Chat message sent")

            # Test 3: Get buffer memory again (should have messages now)
            print("\n4. Testing buffer memory after chat...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{self.test_user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            new_message_count = data["data"]["count"]
            
            # Should have at least 2 messages (user message + assistant response)
            assert new_message_count >= initial_message_count + 2, \
                f"Expected at least {initial_message_count + 2} messages, got {new_message_count}"
            
            messages = data["data"]["messages"]
            print(f"   Message count after chat: {new_message_count}")
            print(f"   Messages: {len(messages)} in response")
            print("✅ Buffer memory contains chat messages")

            # Test 4: Get sessions for user
            print("\n5. Testing GET /v1/sessions/{user_id}...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["object"] == "session_list"
            assert data["type"] == "sessions.list"
            assert "sessions" in data["data"]
            assert "count" in data["data"]
            
            session_count = data["data"]["count"]
            sessions = data["data"]["sessions"]
            
            # Should have at least our test session
            assert session_count >= 1, f"Expected at least 1 session, got {session_count}"
            session_ids = [s["session_id"] for s in sessions]
            assert self.test_session_id in session_ids, "Test session should be in list"
            
            print(f"   Session count: {session_count}")
            print("✅ GET /v1/sessions/{user_id} passed")

            # Test 5: Get specific session
            print("\n6. Testing GET /v1/sessions/{user_id}/{session_id}...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_user_id}/{self.test_session_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["object"] == "session"
            assert data["type"] == "session.retrieved"
            assert data["data"]["session_id"] == self.test_session_id
            assert data["data"]["user_id"] == self.test_user_id
            
            print(f"   Session ID: {data['data']['session_id']}")
            print(f"   Message count: {data['data']['message_count']}")
            print("✅ GET /v1/sessions/{user_id}/{session_id} passed")

            # Test 6: Get session messages
            print("\n7. Testing GET /v1/sessions/{user_id}/{session_id}/messages...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_user_id}/{self.test_session_id}/messages",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["object"] == "message_list"
            assert data["type"] == "messages.list"
            assert "messages" in data["data"]
            assert "count" in data["data"]
            
            message_count = data["data"]["count"]
            assert message_count >= 2, f"Expected at least 2 messages, got {message_count}"
            
            print(f"   Message count: {message_count}")
            print("✅ GET /v1/sessions/{user_id}/{session_id}/messages passed")

            # Test 7: Delete buffer memory for specific session
            print("\n8. Testing DELETE /v1/memory/buffer/{user_id}/{session_id}...")
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/memory/buffer/{self.test_user_id}/{self.test_session_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["object"] == "buffer_memory"
            assert data["type"] == "buffer.cleared"
            assert "deleted_count" in data["data"]
            
            deleted_count = data["data"]["deleted_count"]
            print(f"   Deleted {deleted_count} messages for session")
            print("✅ DELETE /v1/memory/buffer/{user_id}/{session_id} passed")

            # Test 8: Verify session messages were deleted
            print("\n9. Verifying session messages cleared...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_user_id}/{self.test_session_id}/messages",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            remaining_messages = data["data"]["count"]
            assert remaining_messages == 0, f"Expected 0 messages, got {remaining_messages}"
            print("✅ Session messages cleared")

            # Test 9: Delete entire session
            print("\n10. Testing DELETE /v1/sessions/{user_id}/{session_id}...")
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/sessions/{self.test_user_id}/{self.test_session_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["object"] == "session"
            assert data["type"] == "session.deleted"
            assert data["data"]["session_id"] == self.test_session_id
            
            print(f"   Deleted session: {data['data']['session_id']}")
            print("✅ DELETE /v1/sessions/{user_id}/{session_id} passed")

            # Test 10: Verify session was deleted
            print("\n11. Verifying session was deleted...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_user_id}/{self.test_session_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"
            print("✅ Session deletion verified")

            # Test 11: Authentication check
            print("\n12. Testing authentication requirement...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{self.test_user_id}",
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19g1_memory_sessions",
                success=True,
                checks=[
                    f"GET /v1/memory/buffer/{{user_id}} passed ({initial_message_count} initial)",
                    "Chat created buffer memory",
                    f"Buffer contains messages ({new_message_count} after chat)",
                    f"GET /v1/sessions/{{user_id}} passed ({session_count} sessions)",
                    "GET /v1/sessions/{user_id}/{session_id} passed",
                    f"GET /v1/sessions/{{user_id}}/{{session_id}}/messages passed ({message_count} messages)",
                    f"DELETE /v1/memory/buffer/{{user_id}}/{{session_id}} passed ({deleted_count} deleted)",
                    "Session messages cleared",
                    "DELETE /v1/sessions/{user_id}/{session_id} passed",
                    "Session deletion verified (404)",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19g1_memory_sessions",
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
    test = TestMemorySessions()
    await test.test_19g1_memory_sessions()


if __name__ == "__main__":
    asyncio.run(main())
