"""
Print the exact contents of mcp_service.agent_tool_registry after formation loading.
"""

import pytest
import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation import Formation
from tests.utils.env_setup import load_api_keys


@pytest.mark.asyncio
async def test_agent_tool_registry_dump():
    """Print the exact contents of agent_tool_registry after formation loading."""
    load_api_keys()
    
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml"
    )
    
    print("\n" + "="*80)
    print("AGENT TOOL REGISTRY DUMP")
    print("="*80)
    
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    mcp_service = overlord.mcp_service
    
    print("\n🔍 RAW agent_tool_registry contents:")
    print(json.dumps(mcp_service.agent_tool_registry, indent=2, default=str))
    
    print("\n📋 SUMMARY:")
    for agent_or_shared, server_dict in mcp_service.agent_tool_registry.items():
        print(f"  {agent_or_shared}: {len(server_dict)} servers")
        for server_id, tools in server_dict.items():
            print(f"    {server_id}: {len(tools)} tools")
            for tool_name in tools.keys():
                print(f"      - {tool_name}")
    
    print("\n🌐 GLOBAL tool_registry contents:")
    print(f"Global registry has {len(mcp_service.tool_registry)} servers:")
    for server_id, tools in mcp_service.tool_registry.items():
        print(f"  {server_id}: {len(tools)} tools")
        for tool_name in tools.keys():
            print(f"    - {tool_name}")


if __name__ == "__main__":
    asyncio.run(test_agent_tool_registry_dump())