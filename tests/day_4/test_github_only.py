#!/usr/bin/env python3
"""Test GitHub MCP Tool - Focused test to see exact responses"""

import sys
sys.path.insert(0, '.')
import asyncio
from datetime import datetime
import json

from src.muxi.runtime.formation import Formation

async def test_github_mcp():
    """Test GitHub MCP tool specifically"""
    print("\n=== Test GitHub MCP Tool ===")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("✓ Formation loaded and overlord started")
    
    # First, let's check what GitHub tools are available
    print("\n1. Checking available GitHub tools...")
    response_gen = await overlord.chat(
        "What GitHub tools are available? List them briefly.",
        user_id="user1",
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
    print(f"Available tools response: {response[:500]}...")
    
    # Test creating a gist
    print("\n2. Testing GitHub gist creation...")
    gist_content = f"""# MUXI MCP Test Gist
Created by MUXI MCP integration test
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This gist was created to verify GitHub MCP tool invocation works correctly.
"""
    
    filename = f"muxi-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    response_gen = await overlord.chat(
        f"Create a GitHub gist with filename '{filename}' and the following content:\n\n{gist_content}",
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"\nFull GitHub Response:")
    print("="*80)
    print(response)
    print("="*80)
    
    # Look for URLs in response
    import re
    urls = re.findall(r'https://[^\s\)]+', response)
    if urls:
        print(f"\nFound URLs in response:")
        for url in urls:
            print(f"  - {url}")
    
    # Test getting user info
    print("\n3. Testing GitHub get_me tool...")
    response_gen = await overlord.chat(
        "Use the GitHub get_me tool to get information about the authenticated user",
        user_id="user1",
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"\nGitHub get_me response:")
    print("="*80)
    print(response)
    print("="*80)
    
    # Proper shutdown
    formation.shutdown()

if __name__ == "__main__":
    asyncio.run(test_github_mcp())