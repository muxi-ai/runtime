#!/usr/bin/env python3
"""Check actual response types for all endpoints."""

import asyncio
import httpx
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class TestResponseTypes(BaseE2ETest):
    def __init__(self):
        super().__init__("test_types", "Check response types", "19_api")
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.client_key = "test-client-key-456"
        self.admin_headers = {"X-Muxi-Admin-Key": self.admin_key}
        self.client_headers = {"X-Muxi-Client-Key": self.client_key}

    async def test_response_types(self):
        try:
            print("Setting up formation...")
            await self.setup_formation(Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Server ready\n")

            async with httpx.AsyncClient(timeout=10.0) as client:
                endpoints = [
                    # Format: (method, path, headers, description)
                    ("GET", "/memory", self.admin_headers, "Get memory info"),
                    ("GET", "/memory/buffer/0", self.client_headers, "Get buffer memory for user"),
                    ("GET", "/users", self.admin_headers, "List users"),
                    ("GET", "/sessions", self.client_headers, "List sessions (all)"),
                    ("GET", "/sessions/0", self.client_headers, "List sessions for user 0"),
                    ("GET", "/agents", self.admin_headers, "List agents"),
                    ("GET", "/sops", self.client_headers, "List SOPs"),
                    ("GET", "/logs", self.admin_headers, "Get logs"),
                    ("GET", "/health", {}, "Health check"),
                    ("GET", "/status", self.admin_headers, "Get status"),
                    ("GET", "/config", self.admin_headers, "Get config"),
                    ("GET", "/formation", self.admin_headers, "Get formation"),
                    ("GET", "/overlord", self.admin_headers, "Get overlord"),
                    ("GET", "/admin/scheduler", self.admin_headers, "Scheduler status"),
                    ("GET", "/admin/llm/settings", self.admin_headers, "LLM settings"),
                    ("GET", "/admin/config", self.admin_headers, "Get admin config"),
                    ("GET", "/admin/memory", self.admin_headers, "Memory admin"),
                ]
                
                print("=" * 80)
                print(f"{'ENDPOINT':<40} {'OBJECT':<20} {'TYPE':<30}")
                print("=" * 80)
                
                for method, path, headers, desc in endpoints:
                    try:
                        r = await client.request(method, f"{self.base_url}{path}", headers=headers)
                        if r.status_code == 200:
                            data = r.json()
                            obj = data.get('object', '???')
                            typ = data.get('type', '???')
                            print(f"{desc:<40} {obj:<20} {typ:<30}")
                            # Print data keys for config and status endpoints
                            if "config" in path or "formation" in path or "status" in path or "overlord" in path:
                                data_keys = list(data.get('data', {}).keys())
                                print(f"  → data keys: {data_keys}")
                        else:
                            print(f"{desc:<40} {'ERROR':<20} {r.status_code:<30}")
                    except Exception as e:
                        print(f"{desc:<40} {'EXCEPTION':<20} {str(e)[:28]}")
                
                print("=" * 80)

        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.formation:
                await self.cleanup_formation()

async def main():
    test = TestResponseTypes()
    await test.test_response_types()

if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
