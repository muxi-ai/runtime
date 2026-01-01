#!/usr/bin/env python3
"""Minimal memory test."""

import asyncio
import httpx
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class TestMinimal(BaseE2ETest):
    def __init__(self):
        super().__init__("test_minimal_memory", "Minimal memory test", "19_api")
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {"X-Muxi-Admin-Key": self.admin_key}

    async def test_minimal_memory(self):
        try:
            print("Setting up formation...")
            await self.setup_formation(Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Server ready\n")

            # Test GET /v1/memory
            print("Test: GET /v1/memory")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/memory", headers=self.headers)
            
            print(f"Status: {r.status_code}")
            data = r.json()
            print(f"Response keys: {data.keys()}")
            print(f"Object: {data.get('object')}")
            print(f"Type: {data.get('type')}")
            print(f"Success: {data.get('success')}")
            
            if r.status_code == 200:
                print("✅ Test passed!")
            else:
                print(f"❌ Test failed: {r.status_code}")
                print(f"Full response: {data}")

        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.formation:
                await self.cleanup_formation()

async def main():
    test = TestMinimal()
    await test.test_minimal_memory()

if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
