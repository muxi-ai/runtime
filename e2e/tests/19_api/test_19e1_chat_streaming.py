#!/usr/bin/env python3
"""Test 19e1: Chat streaming endpoint."""

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


class TestChatStreaming(BaseE2ETest):
    """Test chat streaming endpoint."""

    def __init__(self):
        super().__init__(
            test_name="test_19e1_chat_streaming",
            test_description="Test POST /v1/chat with streaming",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    async def test_19e1_chat_streaming(self):
        """Test chat streaming endpoint."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19e1_chat_streaming",
            description="Test POST /v1/chat with streaming",
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

            # Test 1: Simple chat request (streaming)
            print("\n2. Testing POST /v1/chat with streaming...")
            
            chat_request = {
                "message": "Hello! Can you say 'test response'?",
                "user_id": "test_user",
                "session_id": "test_session",
                "mode": "sync",  # sync mode with streaming
            }
            
            # Use streaming to read SSE events
            received_tokens = []
            got_done_event = False
            
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json=chat_request,
                    timeout=30.0,
                ) as response:
                    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
                    
                    # Verify it's SSE stream
                    content_type = response.headers.get("content-type", "")
                    assert "text/event-stream" in content_type, f"Expected SSE stream, got: {content_type}"
                    
                    # Read SSE events
                    current_event = None
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue
                        
                        # Parse SSE format: "event: <type>" or "data: <json>"
                        if line.startswith("event: "):
                            current_event = line[7:]  # Extract event type
                        elif line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            
                            try:
                                event_data = json.loads(data_str)
                                
                                # Extract token from data events
                                if current_event is None and "token" in event_data:
                                    token = event_data["token"]
                                    # Token might be a dict or string - handle both
                                    if isinstance(token, dict):
                                        # Extract text if it's a dict
                                        if "content" in token:
                                            received_tokens.append(token["content"])
                                        elif "text" in token:
                                            received_tokens.append(token["text"])
                                        # Otherwise skip - it's metadata
                                    else:
                                        received_tokens.append(str(token))
                                
                                # Check for done event
                                if current_event == "done" and event_data.get("finished"):
                                    got_done_event = True
                                    break
                                    
                            except json.JSONDecodeError as e:
                                print(f"   Warning: Failed to parse event: {data_str[:100]}... Error: {e}")
                            
                            current_event = None  # Reset event type after processing data
            
            # Verify we received tokens
            assert len(received_tokens) > 0, "Should receive at least one token"
            print(f"   Received {len(received_tokens)} tokens")
            
            # Verify we got done event
            assert got_done_event, "Should receive 'done' event"
            
            # Verify we got actual response text
            full_message = "".join(received_tokens)
            assert len(full_message) > 0, "Should have non-empty response"
            print(f"   Received text length: {len(full_message)} chars")
            print(f"   First 100 chars: {full_message[:100]}...")
            print("✅ POST /v1/chat streaming passed")

            # Test 2: Chat without authentication (should fail)
            print("\n3. Testing POST /v1/chat without authentication...")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    json={"message": "test"},
                )
            
            assert response.status_code == 401, f"Expected 401, got {response.status_code}"
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "UNAUTHORIZED"
            print("✅ Authentication enforced")

            # Test 3: Chat with missing message (should fail)
            print("\n4. Testing POST /v1/chat with missing message...")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json={"user_id": "test"},  # Missing message
                )
            
            assert response.status_code == 422, f"Expected 422, got {response.status_code}"
            print("✅ Validation enforced")

            # Test 4: Chat with different user_id
            print("\n5. Testing POST /v1/chat with different user...")
            
            chat_request2 = {
                "message": "Say hello in one word",  # Simple message for faster response
                "user_id": "different_user",
                "session_id": "different_session",
            }
            
            received_events2 = []
            current_event = None
            
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json=chat_request2,
                    timeout=60.0,  # Increased timeout for LLM response
                ) as response:
                    assert response.status_code == 200
                    
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue
                        
                        if line.startswith("event: "):
                            current_event = line[7:]
                        elif line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                event_data = json.loads(data_str)
                                received_events2.append(event_data)
                                
                                # Check for done event
                                if current_event == "done":
                                    break
                            except:
                                pass
                            current_event = None
            
            assert len(received_events2) > 0, "Should receive events for different user"
            print(f"   Received {len(received_events2)} events for different user")
            print("✅ Multiple users supported")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19e1_chat_streaming",
                success=True,
                checks=[
                    f"POST /v1/chat streaming passed ({len(received_tokens)} tokens)",
                    "SSE format verified (text/event-stream)",
                    f"Received {len(received_tokens)} tokens, {len(full_message)} chars",
                    "Authentication enforced",
                    "Validation enforced (missing message)",
                    "Multiple users supported",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19e1_chat_streaming",
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
    test = TestChatStreaming()
    await test.test_19e1_chat_streaming()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
