#!/usr/bin/env python3
"""Quick test for non-streaming chat endpoint."""

import asyncio
import httpx
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "e2e/tests"))

from common import BaseE2ETest


class TestChatNonStreaming(BaseE2ETest):
    """Quick test for non-streaming chat."""

    def __init__(self):
        super().__init__(
            test_name="test_chat_nonstreaming",
            test_description="Test non-streaming chat mode",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = "test-client-key-456"
        self.headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }

    async def test_chat(self):
        """Test non-streaming chat."""
        print("1. Setting up formation with API server...")
        await self.setup_formation(
            formation_path=Path(__file__).parent / "e2e/tests/19_api/formation-api",
        )
        
        # Start the API server
        await self.formation.start_server(block=False)
        
        # Wait for server to be ready
        await asyncio.sleep(2)
        print("✅ Formation ready with API server")

        print("\n2. Testing non-streaming chat...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat",
                headers=self.headers,
                json={
                    "message": "What is 2+2?",
                    "stream": False,
                },
            )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        
        # Check response
        assert response.status_code == 200
        data = response.json()
        print(f"Success: {data.get('success')}")
        print(f"Data keys: {data.get('data', {}).keys()}")
        print("✅ Non-streaming chat works!")
        
        # Cleanup
        await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestChatNonStreaming()
    await test.test_chat()


if __name__ == "__main__":
    asyncio.run(main())
