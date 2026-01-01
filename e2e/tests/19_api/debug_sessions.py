#!/usr/bin/env python3
"""Debug sessions endpoint to understand why session count is 0."""

import asyncio
import httpx
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class DebugSessions(BaseE2ETest):
    def __init__(self):
        super().__init__("debug_sessions", "Debug sessions", "19_api")
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {"X-Muxi-Client-Key": self.client_key}
        self.test_user_id = "0"
        self.test_session_id = "test_session_001"

    async def debug_sessions(self):
        try:
            print("Setting up formation...")
            await self.setup_formation(Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Server ready\n")

            # Step 1: Check initial buffer memory
            print("Step 1: Check initial buffer memory")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/memory/buffer/{self.test_user_id}", headers=self.headers)
            print(f"Status: {r.status_code}")
            data = r.json()
            print(f"Total messages: {data['data'].get('total_messages', 'N/A')}")
            print(f"Sessions: {data['data'].get('sessions', 'N/A')}\n")

            # Step 2: Send a chat message
            print("Step 2: Sending chat message...")
            chat_request = {
                "message": "Say hi",
                "user_id": self.test_user_id,
                "session_id": self.test_session_id,
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", f"{self.base_url}/chat", headers=self.headers, json=chat_request) as response:
                    print(f"Chat response status: {response.status_code}")
                    current_event = None
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("event: "):
                            current_event = line[7:]
                        elif line.startswith("data: "):
                            if current_event == "done":
                                print(f"Chat completed: {line}")
                                break
                            current_event = None
            
            print("✅ Chat sent\n")

            # Step 3: Check buffer memory again
            print("Step 3: Check buffer memory after chat")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/memory/buffer/{self.test_user_id}", headers=self.headers)
            data = r.json()
            print(f"Total messages: {data['data'].get('total_messages', 'N/A')}")
            print(f"Sessions: {data['data'].get('sessions', 'N/A')}\n")

            # Step 4: Check sessions list
            print("Step 4: Check sessions list")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/sessions/{self.test_user_id}", headers=self.headers)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"Object: {data.get('object')}")
                print(f"Type: {data.get('type')}")
                print(f"Session count: {data['data'].get('count', 'N/A')}")
                print(f"Sessions: {data['data'].get('sessions', [])}")
            else:
                print(f"Error: {r.text}\n")

            # Step 5: Try to get specific session
            print("\nStep 5: Try to get specific session")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/sessions/{self.test_user_id}/{self.test_session_id}", headers=self.headers)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"Session found: {data.get('object')}")
            else:
                print(f"Session not found: {r.text}")

        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.formation:
                await self.cleanup_formation()

async def main():
    test = DebugSessions()
    await test.debug_sessions()

if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
