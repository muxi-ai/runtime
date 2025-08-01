"""
Patch to ensure agents only see their own MCP tools, forcing A2A communication.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation.agents.agent import Agent


def patch_agent_tools():
    """Monkey patch the agent's tool discovery to only show agent-specific tools."""
    
    # Store the original method
    original_process = Agent.process_message
    
    async def patched_process(self, *args, **kwargs):
        """Patched process_message method that filters tools based on agent configuration."""
        
        # Store original get tools logic
        original_mcp_service = None
        if self.overlord and hasattr(self.overlord, "mcp_service"):
            original_mcp_service = self.overlord.mcp_service
            
            # Create a filtered view of tools for this agent
            if hasattr(self, '_mcp_server_ids') and self._mcp_server_ids:
                # Create a mock service that only shows this agent's tools
                class FilteredMCPService:
                    def __init__(self, original_service, allowed_servers):
                        self.original = original_service
                        self.allowed = allowed_servers
                        
                    @property
                    def tool_registry(self):
                        """Return only tools from allowed servers."""
                        filtered = {}
                        all_tools = self.original.tool_registry
                        
                        for server_id in self.allowed:
                            if server_id in all_tools:
                                filtered[server_id] = all_tools[server_id]
                        
                        agent_id = getattr(self, 'agent_id', 'unknown')
                        print(f"🔧 Agent {agent_id} can see tools from: {list(filtered.keys())}")
                        return filtered
                    
                    def __getattr__(self, name):
                        # Delegate all other attributes to original
                        return getattr(self.original, name)
                
                # Replace with filtered service
                self.overlord.mcp_service = FilteredMCPService(
                    original_mcp_service, 
                    self._mcp_server_ids
                )
        
        try:
            # Call original process
            result = await original_process(self, *args, **kwargs)
            return result
        finally:
            # Restore original service
            if original_mcp_service:
                self.overlord.mcp_service = original_mcp_service
    
    # Apply the patch
    Agent.process_message = patched_process
    print("✅ Agent tool filtering patch applied!")
    
    
def prepare_agents_for_a2a(overlord):
    """Prepare agents with their specific MCP server IDs for filtering."""
    
    # Map of agent ID to their MCP servers from the formation
    agent_mcp_mapping = {
        'it-support': ['filesystem', 'system-info'],
        'project-manager': ['linear'],
        'researcher': [],
        'writer': []
    }
    
    for agent_id, agent in overlord.agents.items():
        if agent_id in agent_mcp_mapping:
            agent._mcp_server_ids = agent_mcp_mapping[agent_id]
            print(f"📌 Agent {agent_id} configured with MCP servers: {agent._mcp_server_ids}")
        else:
            agent._mcp_server_ids = []
            
    print("✅ Agents prepared for segregated MCP access!")


# Export functions
__all__ = ['patch_agent_tools', 'prepare_agents_for_a2a']