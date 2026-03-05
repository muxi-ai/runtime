#!/usr/bin/env python3
"""Test 20d1: MCP chat tool end-to-end.

Calls the chat tool via MCP, verifies an LLM response is returned,
then checks request tracking via get_request_status.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestMCPChatTool(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_20d1_chat_tool",
            test_description="Chat tool via MCP returns LLM response",
            test_area="20_mcp_server",
        )
        self.base_url = "http://127.0.0.1:8271"

    async def test_20d1_chat_tool(self):
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_20d1_chat_tool",
            description="Chat tool via MCP returns LLM response",
        )

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-mcp",
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("  Formation ready")

            from fastmcp import Client

            async with Client(f"{self.base_url}/mcp") as client:

                # Test 1: Send a chat message via MCP
                print("\n2. Calling chat tool via MCP...")
                result = await client.call_tool(
                    "chat",
                    {
                        "message": "What is 2+2? Reply with just the number.",
                        "user_id": "mcp-test-user",
                        "stream": False,
                    },
                )
                result_text = result.content[0].text if result.content else ""
                print(f"  Raw response length: {len(result_text)}")

                # The response could be the direct JSON from chat endpoint
                data = json.loads(result_text)
                print(f"  Response keys: {list(data.keys())}")
                print(f"  Data: {result_text[:1000]}")

                # Chat may return sync response or async response
                if data.get("status") == "processing":
                    # Async response -- poll for result
                    request_id = data.get("request_id")
                    print(f"  Got async response, request_id={request_id}")
                    assert request_id, "Async response must have request_id"

                    # Poll for completion
                    for i in range(30):
                        await asyncio.sleep(1)
                        poll_result = await client.call_tool(
                            "get_request_status",
                            {
                                "request_id": request_id,
                                "X-Muxi-User-ID": "mcp-test-user",
                            },
                        )
                        poll_data = json.loads(poll_result.content[0].text)
                        status = poll_data.get("data", {}).get("status", "")
                        if status in ("completed", "failed"):
                            break
                        print(f"  Polling... status={status} ({i+1}/30)")

                    assert status == "completed", f"Expected completed, got {status}"
                    result_data = poll_data.get("data", {}).get("result", {})
                    response_text = result_data.get("response", "")
                    print(f"  Async chat response: {response_text[:200]}")
                else:
                    # Sync response -- content is in data.data.message.content
                    msg_data = data.get("data", {})
                    message = msg_data.get("message", {})
                    response_text = message.get("content", "")
                    if not response_text:
                        # Fallback: try data.response or data.message
                        response_text = data.get("response", data.get("message", ""))
                    print(f"  Sync chat response: {response_text[:200]}")

                assert response_text, "Expected non-empty response from chat"
                assert "4" in response_text, f"Expected '4' in response to 2+2: {response_text}"
                print("  Chat response contains expected answer")

                # Test 2: Verify session was created
                print("\n3. Verifying session was created via MCP...")
                sessions_result = await client.call_tool(
                    "list_sessions",
                    {
                        "X-Muxi-User-ID": "mcp-test-user",
                    },
                )
                sessions_data = json.loads(sessions_result.content[0].text)
                assert sessions_data.get("success") is True
                sessions = sessions_data.get("data", {}).get("sessions", [])
                assert len(sessions) >= 1, f"Expected at least 1 session, got {len(sessions)}"
                print(f"  Found {len(sessions)} session(s) for mcp-test-user")

            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20d1_chat_tool",
                success=True,
                checks=[
                    "Chat tool invoked via MCP",
                    "LLM response received with correct answer",
                    "Session created and visible via list_sessions",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20d1_chat_tool",
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
    test = TestMCPChatTool()
    await test.test_20d1_chat_tool()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
