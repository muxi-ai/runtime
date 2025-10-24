#!/usr/bin/env python3
"""Debug why test_19h1_users times out."""

import asyncio
import httpx
from pathlib import Path
import sys
import os
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class DebugUsersTimeout(BaseE2ETest):
    def __init__(self):
        super().__init__("debug_users", "Debug users timeout", "19_api")
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {"X-Muxi-Client-Key": self.client_key}

    async def debug_timeout(self):
        try:
            print("Setting up formation...")
            await self.setup_formation(Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Server ready\n")

            # Try non-streaming chat
            print("Attempting non-streaming chat...")
            start = time.time()
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{self.base_url}/chat",
                        headers=self.headers,
                        json={
                            "user_id": "test_user",
                            "session_id": "test_session",
                            "message": "Hello",
                            "stream": False,
                        },
                    )
                
                elapsed = time.time() - start
                print(f"✅ Chat completed in {elapsed:.2f}s")
                print(f"Status: {response.status_code}")
                print(f"Response preview: {response.text[:200]}")
                
            except asyncio.TimeoutError:
                elapsed = time.time() - start
                print(f"❌ Chat timed out after {elapsed:.2f}s")
                print("This is likely why the test hangs!")

        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.formation:
                await self.cleanup_formation()

async def main():
    test = DebugUsersTimeout()
    await test.debug_timeout()

if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
