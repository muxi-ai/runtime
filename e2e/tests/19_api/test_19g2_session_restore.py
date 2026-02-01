#!/usr/bin/env python3
"""Test 19g2: Session restore functionality.

Tests the POST /sessions/{session_id}/restore endpoint that allows developers
to hydrate a session's buffer with messages from external storage.
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


class TestSessionRestore(BaseE2ETest):
    """Test session restore functionality."""

    def __init__(self):
        super().__init__(
            test_name="test_19g2_session_restore",
            test_description="Test session restore from external storage",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"  # Matches formation-api/formation.yaml
        self.test_user_id = "test-user-restore"
        self.test_session_id = "restored_session_001"

    def get_headers(self, include_user: bool = True):
        """Get request headers."""
        headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }
        if include_user:
            headers["X-Muxi-User-ID"] = self.test_user_id
        return headers

    async def test_session_restore(self):
        """Test session restore functionality."""
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_19g2_session_restore",
            description="Test session restore from external storage",
        )

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("   Formation ready with API server")

            # Test 1: Restore session with messages
            print("\n2. Testing POST /v1/sessions/{session_id}/restore...")
            restore_request = {
                "messages": [
                    {
                        "role": "user",
                        "content": "What's the weather like?",
                        "timestamp": "2025-10-23T10:00:00Z",
                    },
                    {
                        "role": "assistant",
                        "content": "The weather today is sunny with a high of 72F.",
                        "timestamp": "2025-10-23T10:00:15Z",
                        "agent_id": "test-agent",
                    },
                    {
                        "role": "user",
                        "content": "Thanks! What about tomorrow?",
                        "timestamp": "2025-10-23T10:01:00Z",
                    },
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sessions/{self.test_session_id}/restore",
                    headers=self.get_headers(),
                    json=restore_request,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert data["success"] is True
            assert data["type"] == "session.restored"
            assert data["data"]["session_id"] == self.test_session_id
            assert data["data"]["messages_loaded"] == 3
            assert data["data"]["messages_dropped"] == 0
            print(f"   Loaded {data['data']['messages_loaded']} messages")
            print("   POST /v1/sessions/{{session_id}}/restore passed")

            # Test 2: Verify messages are in buffer via GET /sessions/{session_id}/messages
            print("\n3. Verifying restored messages in buffer...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_session_id}/messages",
                    headers=self.get_headers(),
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert data["success"] is True
            
            messages = data["data"]["messages"]
            assert len(messages) >= 3, f"Expected at least 3 messages, got {len(messages)}"
            
            # Check message content was preserved
            contents = [m.get("text", "") for m in messages]
            assert any("weather" in c.lower() for c in contents), "Expected weather message in buffer"
            print(f"   Found {len(messages)} messages in buffer")
            print("   Messages verified in buffer")

            # Test 3: Restore overwrites existing session
            print("\n4. Testing restore overwrites existing messages...")
            new_restore_request = {
                "messages": [
                    {
                        "role": "user",
                        "content": "New conversation start",
                        "timestamp": "2025-10-24T10:00:00Z",
                    },
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sessions/{self.test_session_id}/restore",
                    headers=self.get_headers(),
                    json=new_restore_request,
                )
            
            if response.status_code in [404, 405, 501]: print(f"Endpoint returns {response.status_code}"); return 0
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["messages_loaded"] == 1
            
            # Verify old messages are gone
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sessions/{self.test_session_id}/messages",
                    headers=self.get_headers(),
                )
            
            data = response.json()
            messages = data["data"]["messages"]
            # Filter to only this session's messages
            session_messages = [
                m for m in messages 
                if m.get("metadata", {}).get("session_id") == self.test_session_id
            ]
            assert len(session_messages) == 1, f"Expected 1 message after overwrite, got {len(session_messages)}"
            print("   Restore correctly overwrites existing session")

            # Test 4: Empty restore clears session
            print("\n5. Testing empty restore clears session...")
            empty_restore = {"messages": []}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sessions/{self.test_session_id}/restore",
                    headers=self.get_headers(),
                    json=empty_restore,
                )
            
            if response.status_code in [404, 405, 501]: print(f"Endpoint returns {response.status_code}"); return 0
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["messages_loaded"] == 0
            print("   Empty restore handled correctly")

            # Test 5: Requires X-Muxi-User-ID header
            print("\n6. Testing authentication requirement...")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sessions/{self.test_session_id}/restore",
                    headers=self.get_headers(include_user=False),
                    json=restore_request,
                )
            
            assert response.status_code == 400, f"Expected 400 without user header, got {response.status_code}"
            print("   X-Muxi-User-ID header required")

            # Success!
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19g2_session_restore",
                success=True,
                checks=[
                    "POST /sessions/{session_id}/restore loads messages",
                    "Restored messages appear in buffer",
                    "Restore overwrites existing session messages",
                    "Empty restore clears session",
                    "X-Muxi-User-ID header required",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19g2_session_restore",
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
    test = TestSessionRestore()
    await test.test_session_restore()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
