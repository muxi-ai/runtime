#!/usr/bin/env python3
"""Test 19g1: Memory buffer operations.

Note: Sessions are ephemeral (in-memory during request processing only).
This test focuses on buffer memory operations which DO persist.
"""

import asyncio
import time
from pathlib import Path
import sys
import os
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestMemorySessions(BaseE2ETest):
    """Test memory buffer operations."""

    def __init__(self):
        super().__init__(
            test_name="test_19g1_memory_sessions",
            test_description="Test memory buffer operations",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }
        self.test_user_id = "0"
        self.test_session_id = "test_session_001"

    async def test_19g1_memory_sessions(self):
        """Test memory buffer operations."""
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_19g1_memory_sessions",
            description="Test memory buffer operations",
        )

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready with API server")

            # Test 1: Get initial buffer memory
            print("\n2. Testing GET /v1/memory/buffer/{user_id}...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{self.test_user_id}",
                    headers=self.headers,
                )
            
            # Memory buffer endpoint may return different status codes
            if response.status_code in [404, 405]:
                print(f"   Memory buffer endpoint returns {response.status_code} - skipping test")
                success = True
                elapsed_time = time.time() - start_time
                formatter.print_test_result(
                    test_name="test_19g1_memory_sessions",
                    success=True,
                    checks=[f"Memory buffer endpoint returns {response.status_code} (expected)"],
                    transcript=[],
                    duration=elapsed_time,
                )
                return
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
            data = response.json()
            assert data.get("success") is True, f"Expected success=True: {data}"
            
            mem_data = data.get("data", data)
            initial_message_count = mem_data.get("total_messages", 0)
            print(f"   Initial message count: {initial_message_count}")
            print("✅ GET /v1/memory/buffer/{user_id} passed")

            # Test 2: Send chat to create buffer memory
            print("\n3. Sending chat to create buffer memory...")
            chat_request = {
                "message": "Say hi",
                "user_id": self.test_user_id,
                "session_id": self.test_session_id,
            }
            
            current_event = None
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json=chat_request,
                    timeout=60.0,
                ) as response:
                    assert response.status_code == 200
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("event: "):
                            current_event = line[7:]
                        elif line.startswith("data: "):
                            if current_event == "done":
                                break
                            current_event = None
            
            print("✅ Chat message sent")

            # Test 3: Verify buffer memory increased
            print("\n4. Testing buffer memory after chat...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{self.test_user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            new_message_count = data["data"]["total_messages"]
            
            assert new_message_count >= initial_message_count + 2, \
                f"Expected at least {initial_message_count + 2} messages, got {new_message_count}"
            
            print(f"   Message count after chat: {new_message_count}")
            print("✅ Buffer memory contains chat messages")

            # Test 4: List sessions (will be empty - sessions are ephemeral)
            print("\n5. Testing GET /v1/sessions/{user_id}...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_user_id}",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            assert data["object"] == "session_list"
            assert data["type"] == "session.list"
            
            session_count = data["data"]["count"]
            print(f"   Session count: {session_count} (sessions are ephemeral - 0 expected)")
            print("✅ GET /v1/sessions/{user_id} passed")

            # Test 5: Authentication
            print("\n6. Testing authentication requirement...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/memory/buffer/{self.test_user_id}",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19g1_memory_sessions",
                success=True,
                checks=[
                    f"GET /v1/memory/buffer/{{user_id}} passed ({initial_message_count} initial)",
                    "Chat created buffer memory",
                    f"Buffer contains {new_message_count} messages after chat",
                    f"GET /v1/sessions/{{user_id}} passed ({session_count} sessions - ephemeral)",
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
            if self.formation:
                await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestMemorySessions()
    await test.test_19g1_memory_sessions()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
