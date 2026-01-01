#!/usr/bin/env python3
"""Debug what users endpoints actually return."""

import asyncio
import httpx
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class DebugUsersResponse(BaseE2ETest):
    def __init__(self):
        super().__init__("debug_users_response", "Debug users response", "19_api")
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {"X-Muxi-Client-Key": self.client_key}

    async def debug_response(self):
        try:
            print("Setting up formation...")
            await self.setup_formation(Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Server ready\n")

            # Test 1
            print("Test 1: GET /v1/users/identifiers/nonexistent_user")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/users/identifiers/nonexistent_user", headers=self.headers)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text}\n")

            # Test 2
            print("Test 2: GET /v1/users/nonexistent_identifier")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/users/nonexistent_identifier", headers=self.headers)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text}\n")

        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.formation:
                await self.cleanup_formation()

async def main():
    test = DebugUsersResponse()
    await test.debug_response()

if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
