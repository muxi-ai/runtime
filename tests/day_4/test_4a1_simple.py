#!/usr/bin/env python3
"""Test 4A1 Simple - Filesystem MCP operations without timeout issues"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation.formation import Formation

async def test_filesystem_operations():
    """Test filesystem MCP CRUD operations"""
    print("\n=== Test 4A1 Simple: Filesystem MCP Operations ===")
    
    # Load formation
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("\n1. Creating a file...")
    response_gen = await overlord.chat(
        "Create a file at /Users/ran/Desktop/test_file.txt with content 'Hello from MUXI MCP test!'",
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"Create Response: {response}")
    assert "created" in response.lower() or "wrote" in response.lower()
    
    print("\n2. Reading the file...")
    response_gen = await overlord.chat(
        "Read the file at /Users/ran/Desktop/test_file.txt",
        user_id="user1", 
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"Read Response: {response}")
    assert "hello from muxi" in response.lower()
    
    print("\n3. Updating the file...")
    response_gen = await overlord.chat(
        "Update the file at /Users/ran/Desktop/test_file.txt to say 'Updated content from MUXI!'",
        user_id="user1",
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"Update Response: {response}")
    
    print("\n4. Deleting the file...")
    response_gen = await overlord.chat(
        "Delete the file at /Users/ran/Desktop/test_file.txt",
        user_id="user1",
        use_async=False
    )
    
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"Delete Response: {response}")
    assert "deleted" in response.lower() or "removed" in response.lower()
    
    # Cleanup
    await formation.stop_overlord()
    
    print("\n✅ Test 4A1 PASSED: All filesystem operations successful")
    return True

if __name__ == "__main__":
    try:
        asyncio.run(test_filesystem_operations())
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)