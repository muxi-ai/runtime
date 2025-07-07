#!/usr/bin/env python3
"""Test to get the correct GitHub username"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation import Formation

async def test_github_username():
    """Get GitHub username and create repo properly"""
    print("\n=== Test GitHub Username ===")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("\n✓ Formation loaded")
    
    # First get the authenticated user info
    print("\n1. Getting GitHub user info...")
    response_gen = await overlord.chat(
        "Use the GitHub get_me tool to get information about the authenticated user. Tell me the username.",
        user_id="user1",
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
    print(f"Response: {response}")
    
    # Now try to create/update a file in an existing repo
    print("\n2. Testing file creation in existing repo...")
    response_gen = await overlord.chat(
        "Create or update a file named 'test-cpu.json' in the GitHub repository 'ranaroussi/cpu-monitor' with the content: {\"test\": \"data\", \"timestamp\": \"2025-01-07\"}",
        user_id="user1",
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
    print(f"\nFile creation response: {response}")
    
    # Proper shutdown
    formation.shutdown()

if __name__ == "__main__":
    asyncio.run(test_github_username())