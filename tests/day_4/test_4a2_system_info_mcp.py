#!/usr/bin/env python3
"""Test 4A2: System Info MCP - System information retrieval via MCP"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation.formation import Formation

async def test_system_info_mcp():
    """Test system info MCP operations"""
    print("\n=== Test 4A2: System Info MCP ===")
    print("Goal: Validate CPU, memory, and system stats retrieval via MCP")
    
    try:
        # Load formation with MCP enabled
        formation = Formation()
        await formation.load("test-formations/formation-mcp")
        overlord = await formation.start_overlord()
        
        # Ensure overlord is started
        await overlord.ensure_started()
        
        print("\n1. Testing CPU and memory usage retrieval...")
        response_gen = await overlord.chat(
            "What is the current CPU usage and available memory on this system?",
            user_id="user1",
            use_async=False
        )
        
        # Collect streaming response
        response = ""
        async for chunk in response_gen:
            response += chunk
        print(f"Response: {response}")
        
        # Verify response contains system stats
        response_lower = response.lower()
        assert any(term in response_lower for term in ["cpu", "processor"]), \
            "Response should mention CPU"
        assert any(term in response_lower for term in ["memory", "ram", "gb", "mb"]), \
            "Response should mention memory"
        assert any(char in response for char in ["%", "percent"]) or "usage" in response_lower, \
            "Response should include usage statistics"
        print("✓ CPU and memory stats retrieved successfully")
        
        print("\n2. Testing detailed system information...")
        response_gen = await overlord.chat(
            "Give me detailed system information including CPU cores, total memory, and disk usage",
            user_id="user1",
            use_async=False
        )
        
        # Collect streaming response
        response = ""
        async for chunk in response_gen:
            response += chunk
        print(f"Response: {response}")
        
        # Should have more detailed information
        response_lower = response.lower()
        assert any(term in response_lower for term in ["core", "thread", "processor"]), \
            "Response should mention CPU cores/threads"
        assert len(response) > 100, "Detailed response should be substantial"
        print("✓ Detailed system information retrieved successfully")
        
        print("\n3. Testing specific metric queries...")
        response_gen = await overlord.chat(
            "What percentage of memory is currently being used?",
            user_id="user1",
            use_async=False
        )
        
        # Collect streaming response
        response = ""
        async for chunk in response_gen:
            response += chunk
        print(f"Response: {response}")
        
        # Should have memory percentage
        assert any(char in response for char in ["%", "percent"]) or \
               any(term in response_lower for term in ["memory", "ram"]), \
            "Response should include memory percentage"
        print("✓ Specific metric query successful")
        
        print("\n4. Testing system uptime information...")
        response_gen = await overlord.chat(
            "How long has this system been running (uptime)?",
            user_id="user1",
            use_async=False
        )
        
        # Collect streaming response
        response = ""
        async for chunk in response_gen:
            response += chunk
        print(f"Response: {response}")
        
        # Should have uptime information
        response_lower = response.lower()
        assert any(term in response_lower for term in 
                  ["uptime", "running", "hours", "days", "minutes", "boot", "started"]), \
            "Response should include uptime information"
        print("✓ System uptime query successful")
        
        print("\n5. Testing disk space information...")
        response_gen = await overlord.chat(
            "Show me the available disk space on the main drive",
            user_id="user1",
            use_async=False
        )
        
        # Collect streaming response
        response = ""
        async for chunk in response_gen:
            response += chunk
        print(f"Response: {response}")
        
        # Should have disk space information
        response_lower = response.lower()
        assert any(term in response_lower for term in 
                  ["disk", "space", "storage", "gb", "tb", "available", "free"]), \
            "Response should include disk space information"
        print("✓ Disk space query successful")
        
        # Stop the overlord
        await formation.stop_overlord()
        
        print("\n✅ Test 4A2 PASSED: All system info MCP operations successful")
        return True
            
    except Exception as e:
        print(f"\n❌ Test 4A2 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_system_info_mcp())
    sys.exit(0 if success else 1)