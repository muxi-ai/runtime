"""
Diagnostic test to verify MCP tool isolation is working correctly.
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
async def test_7b1_tool_isolation_diagnostic():
    """Diagnose if MCP tool isolation is working correctly."""
    load_api_keys()
    
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml"
    )
    
    print("\n" + "="*80)
    print("DIAGNOSTIC: MCP Tool Isolation Test")
    print("="*80)
    
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    # Check MCP service tool registries
    mcp_service = overlord.mcp_service
    
    print("\n📋 GLOBAL TOOL REGISTRY:")
    for server_id, tools in mcp_service.tool_registry.items():
        print(f"  Server: {server_id}")
        for tool_name in tools.keys():
            print(f"    - {tool_name}")
    
    print("\n📋 AGENT-SPECIFIC TOOL REGISTRIES:")
    for agent_or_shared, server_tools in mcp_service.agent_tool_registry.items():
        print(f"  Agent/Shared: {agent_or_shared}")
        for server_id, tools in server_tools.items():
            print(f"    Server: {server_id}")
            for tool_name in tools.keys():
                print(f"      - {tool_name}")
    
    print("\n🔍 AGENT TOOL ACCESS VERIFICATION:")
    for agent_id, agent in overlord.agents.items():
        print(f"\n  Agent: {agent_id}")
        
        # Get tools this agent should have access to
        agent_tools = mcp_service.get_tool_registry(agent_id)
        print(f"    Tool registry size: {len(agent_tools)}")
        
        for server_id, tools in agent_tools.items():
            print(f"    Server: {server_id}")
            for tool_name in tools.keys():
                print(f"      - {tool_name}")
    
    # Test if agents are properly isolated
    it_support_tools = mcp_service.get_tool_registry("it-support")
    pm_tools = mcp_service.get_tool_registry("project-manager")
    
    print("\n✅ ISOLATION VERIFICATION:")
    print(f"  IT Support has {len(it_support_tools)} servers")
    print(f"  Project Manager has {len(pm_tools)} servers")
    
    # Check if IT Support has filesystem tools
    has_filesystem = any("filesystem" in server_id for server_id in it_support_tools.keys())
    print(f"  IT Support has filesystem tools: {has_filesystem}")
    
    # Check if Project Manager has Linear tools
    has_linear = any("linear" in server_id for server_id in pm_tools.keys())
    print(f"  Project Manager has Linear tools: {has_linear}")
    
    # Check if agents are isolated (don't share tools)
    it_servers = set(it_support_tools.keys())
    pm_servers = set(pm_tools.keys())
    shared_servers = it_servers.intersection(pm_servers)
    
    print(f"  Shared servers between agents: {shared_servers}")
    print(f"  Proper isolation: {len(shared_servers) == 0 or shared_servers == {'_shared'}}")


if __name__ == "__main__":
    asyncio.run(test_7b1_tool_isolation_diagnostic())