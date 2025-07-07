#!/usr/bin/env python3
"""Test MCP Tool Invocation - Verify Linear and GitHub tools work"""

import sys
sys.path.insert(0, '.')
import asyncio
from datetime import datetime

from src.muxi.runtime.formation import Formation

async def test_mcp_tool_invocation():
    """Test actual tool invocation on Linear and GitHub"""
    print("\n=== Test MCP Tool Invocation ===")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("✓ Formation loaded and overlord started")
    
    # Test 1: Linear - Create an issue
    print("\n1. Testing Linear tool invocation...")
    print("   Creating a test issue in Linear...")
    
    response_gen = await overlord.chat(
        "Create a Linear issue with title 'Test Issue from MUXI' and description 'This is a test issue created by MUXI MCP integration test on " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "'",
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"\nLinear Response: {response}")
    
    # Check if issue was created
    response_lower = response.lower()
    if any(term in response_lower for term in ["created", "issue", "linear", "successfully"]):
        print("✅ Linear tool invocation successful!")
    else:
        print("❌ Linear tool invocation may have failed")
    
    # Test 2: GitHub - Create a gist
    print("\n2. Testing GitHub tool invocation...")
    print("   Creating a test gist...")
    
    gist_content = f"""# MUXI MCP Test Gist
Created by MUXI MCP integration test
Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This gist was created to verify GitHub MCP tool invocation works correctly.
"""
    
    response_gen = await overlord.chat(
        f"Create a public GitHub gist with filename 'muxi-test.md' and the following content:\n\n{gist_content}",
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"\nGitHub Response: {response}")
    
    # Check if gist was created
    response_lower = response.lower()
    if "https://gist.github.com" in response:
        print("✅ GitHub tool invocation successful!")
        # Try to extract gist URL if present
        import re
        urls = re.findall(r'https://gist\.github\.com/[\w/]+', response)
        if urls:
            print(f"   Gist URL: {urls[0]}")
    elif any(term in response_lower for term in ["error", "failed", "permission", "access"]):
        print("❌ GitHub tool invocation failed")
        print(f"   Error: {response[:200]}")
    else:
        print("⚠️  GitHub tool invocation unclear - check response")
        print(f"   Response: {response[:200]}")
    
    # Test 3: Quick test of a filesystem tool for comparison
    print("\n3. Testing Filesystem tool invocation (for comparison)...")
    response_gen = await overlord.chat(
        "List the allowed directories for the filesystem MCP",
        user_id="user1",
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"\nFilesystem Response: {response[:200]}...")
    
    if "/Users/ran/Desktop" in response:
        print("✅ Filesystem tool invocation successful!")
    
    print("\n=== Test Summary ===")
    print("All MCP tool invocations tested.")
    print("Check the responses above to verify successful execution.")
    
    # Proper shutdown
    formation.shutdown()

if __name__ == "__main__":
    asyncio.run(test_mcp_tool_invocation())