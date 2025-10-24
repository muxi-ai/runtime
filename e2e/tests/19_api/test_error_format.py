#!/usr/bin/env python3
"""Quick test to check error response format."""

import asyncio
import httpx
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest

class TestErrorFormat(BaseE2ETest):
    """Test error response format."""

    def __init__(self):
        super().__init__(
            test_name="test_error_format",
            test_description="Check error response format",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "Content-Type": "application/json",
        }

    async def test_error_format(self):
        """Test error response format."""
        try:
            # Setup formation
            print("Setting up formation...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            # Start the API server
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Server ready\n")

            # Test 1: Non-existent agent (404)
            print("Test 1: GET non-existent agent")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/agents/non_existent_agent_xyz",
                    headers=self.headers,
                )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            data = response.json()
            print(f"Parsed JSON: {data}\n")
            
            # Test 2: No authentication (401)
            print("Test 2: GET without auth")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/agents",
                    headers={"Content-Type": "application/json"},
                )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            data = response.json()
            print(f"Parsed JSON: {data}\n")

            # Test 3: Invalid agent creation (400)
            print("Test 3: POST invalid agent (missing required fields)")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/agents",
                    headers=self.headers,
                    json={"name": "Test"},  # Missing required fields
                )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            try:
                data = response.json()
                print(f"Parsed JSON: {data}\n")
            except:
                print("Could not parse as JSON\n")

        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            if self.formation:
                await self.cleanup_formation()

async def main():
    test = TestErrorFormat()
    await test.test_error_format()

if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
