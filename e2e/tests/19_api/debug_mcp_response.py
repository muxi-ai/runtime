#!/usr/bin/env python3
"""Debug MCP API response."""

import asyncio
import httpx
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest


async def main():
    test = BaseE2ETest(test_name="debug", test_description="Debug", test_area="19_api")
    
    try:
        print("Setting up formation...")
        await test.setup_formation(formation_path=Path(__file__).parent / "formation-api-full")
        await test.formation.start_server(block=False)
        await asyncio.sleep(2)
        print("Formation ready\n")
        
        base_url = "http://127.0.0.1:8271/v1"
        headers = {"X-Muxi-Admin-Key": "test-admin-key-123", "Content-Type": "application/json"}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            print("Testing GET /v1/mcp...")
            r = await client.get(f"{base_url}/mcp", headers=headers)
            print(f"Status: {r.status_code}")
            print(f"Response: {json.dumps(r.json(), indent=2)}\n")
            
    finally:
        if test.formation:
            await test.cleanup_formation()


if __name__ == "__main__":
    import os
    os._exit(asyncio.run(main()) or 0)
