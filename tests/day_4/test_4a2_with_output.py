#!/usr/bin/env python3
"""Test 4A2: System Info MCP - System information retrieval via MCP with full output"""

import sys
sys.path.insert(0, '.')
import asyncio
import json

from src.muxi.runtime.formation.formation import Formation

async def test_system_info_mcp():
    """Test system info MCP operations with detailed output"""
    print("\n=== Test 4A2: System Info MCP (Enhanced Output) ===")
    print("Goal: Validate CPU, memory, and system stats retrieval via MCP with full visibility")
    
    try:
        # Load formation with MCP enabled
        formation = Formation()
        await formation.load("test-formations/formation-mcp")
        overlord = await formation.start_overlord()
        
        # Ensure overlord is started
        await overlord.ensure_started()
        
        # Test 1: CPU and Memory
        print("\n" + "="*80)
        print("TEST 1: CPU and Memory Usage")
        print("="*80)
        print("\nPrompt sent to overlord.chat:")
        prompt1 = "What is the current CPU usage and available memory on this system?"
        print(f'"{prompt1}"')
        
        response_gen = await overlord.chat(prompt1, user_id="user1", use_async=False)
        
        print("\nCollecting response...")
        response = ""
        async for chunk in response_gen:
            response += chunk
        
        print("\nRaw response from overlord.chat:")
        print("-" * 40)
        print(response)
        print("-" * 40)
        
        # Check if we got actual data
        if "cpu" in response.lower() and ("%" in response or "percent" in response.lower()):
            print("\n✅ CPU information retrieved successfully")
        else:
            print("\n❌ No CPU percentage found in response")
            
        if "memory" in response.lower() and ("gb" in response.lower() or "mb" in response.lower()):
            print("✅ Memory information retrieved successfully")
        else:
            print("❌ No memory information found in response")
        
        # Test 2: Disk Space
        print("\n" + "="*80)
        print("TEST 2: Disk Space Information")
        print("="*80)
        print("\nPrompt sent to overlord.chat:")
        prompt2 = "Show me the available disk space on the main drive"
        print(f'"{prompt2}"')
        
        response_gen = await overlord.chat(prompt2, user_id="user1", use_async=False)
        
        print("\nCollecting response...")
        response = ""
        async for chunk in response_gen:
            response += chunk
            
        print("\nRaw response from overlord.chat:")
        print("-" * 40)
        print(response)
        print("-" * 40)
        
        # Check if we got actual disk data
        if "gb" in response.lower() and ("free" in response.lower() or "available" in response.lower()):
            print("\n✅ Disk space information retrieved successfully")
        else:
            print("\n❌ No disk space information found in response")
        
        # Stop the overlord
        await formation.stop_overlord()
        
        print("\n" + "="*80)
        print("TEST COMPLETED")
        print("="*80)
        return True
            
    except Exception as e:
        print(f"\n❌ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_system_info_mcp())
    sys.exit(0 if success else 1)