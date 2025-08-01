"""
Debug test to examine what get_tool_registry is returning.
"""

import pytest
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation import Formation
from tests.utils.env_setup import load_api_keys


@pytest.mark.asyncio
async def test_get_tool_registry_debug():
    """Debug what get_tool_registry is actually returning."""
    load_api_keys()
    
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml"
    )
    
    print("\n" + "="*80)
    print("DEBUG: get_tool_registry() Method")
    print("="*80)
    
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    mcp_service = overlord.mcp_service
    
    print("\n🔍 DETAILED get_tool_registry() DEBUG:")
    
    for agent_id in ["it-support", "project-manager"]:
        print(f"\n--- Agent: {agent_id} ---")
        
        # Check what's in the agent_tool_registry for this agent
        print(f"agent_tool_registry['{agent_id}']:", mcp_service.agent_tool_registry.get(agent_id, "NOT_FOUND"))
        print(f"agent_tool_registry['_shared']:", list(mcp_service.agent_tool_registry.get("_shared", {}).keys()))
        
        # Call get_tool_registry and see what it returns
        result = mcp_service.get_tool_registry(agent_id)
        print(f"get_tool_registry('{agent_id}') returned {len(result)} servers:")
        for server_id in result.keys():
            print(f"  - {server_id}")
        
        # Check if the result is coming from global tool_registry
        if result == mcp_service.tool_registry:
            print(f"  ⚠️  PROBLEM: Returning global tool_registry instead of agent-specific!")
        
        # Manual check of the get_tool_registry logic
        print(f"  Manual check:")
        shared_tools = dict(mcp_service.agent_tool_registry.get("_shared", {}))
        print(f"    Shared tools: {list(shared_tools.keys())}")
        
        if agent_id in mcp_service.agent_tool_registry:
            agent_tools = mcp_service.agent_tool_registry[agent_id]
            print(f"    Agent-specific tools: {list(agent_tools.keys())}")
            shared_tools.update(agent_tools)
        else:
            print(f"    Agent-specific tools: NONE (agent not in registry)")
            
        print(f"    Expected result: {list(shared_tools.keys())}")


if __name__ == "__main__":
    asyncio.run(test_get_tool_registry_debug())