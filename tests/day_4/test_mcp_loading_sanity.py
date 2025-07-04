#!/usr/bin/env python3
"""Sanity check: Test that MCP servers are loaded from formation"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_sanity_check():
    """Check if MCP servers are loaded correctly."""
    
    print("\nMCP LOADING SANITY CHECK")
    print("Goal: Verify that MCP servers are loaded from the formation")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-mcp")
    formation = Formation()
    
    # Run sync operation in executor
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    
    # Check if MCP servers are loaded
    print("Formation loaded successfully")
    
    # Access internal configuration
    if hasattr(formation, '_config') and formation._config:
        print(f"\nFormation ID: {formation._config.get('formation_id', 'N/A')}")
        
        # Check for MCP configuration
        mcp_config = formation._config.get('mcp_config', {})
        if mcp_config:
            print(f"MCP config found: {type(mcp_config)}")
            
            # Check if MCP servers are loaded
            if hasattr(mcp_config, 'servers'):
                servers = mcp_config.servers
                print(f"\nMCP servers loaded: {len(servers)}")
                for server_id, server in servers.items():
                    print(f"  - {server_id}: {server.description if hasattr(server, 'description') else 'No description'}")
                    if hasattr(server, 'type'):
                        print(f"    Type: {server.type}")
                    if hasattr(server, 'active'):
                        print(f"    Active: {server.active}")
            else:
                print("❌ No servers attribute found in MCP config")
        else:
            print("❌ No MCP config found in formation")
    else:
        print("❌ Formation config not accessible")
    
    # Try to start overlord and check MCP service
    try:
        print("\nStarting overlord to check MCP service...")
        overlord = await loop.run_in_executor(None, formation.start_overlord)
        
        # Check if MCP service is available
        if hasattr(overlord, 'mcp_service'):
            print("✓ MCP service is available on overlord")
            mcp_service = overlord.mcp_service
            
            # Check registered servers
            if hasattr(mcp_service, '_servers'):
                print(f"\nRegistered MCP servers: {len(mcp_service._servers)}")
                for server_id in mcp_service._servers:
                    print(f"  - {server_id}")
            else:
                print("❌ No _servers attribute on MCP service")
                
            # Check available tools per server
            if hasattr(mcp_service, 'tool_registry'):
                print(f"\n✓ Tool registry found")
                total_tools = 0
                
                for server_id, tools in mcp_service.tool_registry.items():
                    tool_count = len(tools) if isinstance(tools, dict) else 0
                    total_tools += tool_count
                    print(f"\nServer: {server_id}")
                    print(f"  Tools available: {tool_count}")
                    
                    if tool_count > 0 and isinstance(tools, dict):
                        for tool_name, tool_def in list(tools.items())[:5]:  # Show first 5
                            desc = tool_def.get('description', 'No description')
                            if len(desc) > 50:
                                desc = desc[:47] + "..."
                            print(f"    - {tool_name}: {desc}")
                        
                        if tool_count > 5:
                            print(f"    ... and {tool_count - 5} more tools")
                
                print(f"\n✓ Total tools across all servers: {total_tools}")
            else:
                print("❌ No tool_registry attribute on MCP service")
        else:
            print("❌ No MCP service found on overlord")
            
        # Check agents for MCP service access
        if hasattr(overlord, 'agents'):
            print(f"\nAgents loaded: {len(overlord.agents)}")
            for agent_id, agent in overlord.agents.items():
                print(f"\nAgent: {agent_id}")
                if hasattr(agent, '_mcp_service'):
                    print(f"  ✓ Has MCP service access")
                    
                    # Check if agent can see the tools
                    try:
                        mcp_service = agent._mcp_service
                        if hasattr(mcp_service, 'tool_registry'):
                            total_tools = sum(len(tools) for tools in mcp_service.tool_registry.values())
                            print(f"  ✓ Can access {total_tools} tools via MCP service")
                        else:
                            print(f"  ❌ MCP service has no tool_registry")
                    except Exception as e:
                        print(f"  ❌ Error accessing MCP service: {e}")
                else:
                    print("  ❌ No MCP service access")
                    
        # Stop overlord
        await loop.run_in_executor(None, formation.stop_overlord, 10.0)
        
    except Exception as e:
        print(f"\n❌ Error starting overlord: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nSanity check complete!")


def main():
    """Main entry point."""
    print("Running MCP loading sanity check...")
    
    try:
        asyncio.run(run_sanity_check())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()