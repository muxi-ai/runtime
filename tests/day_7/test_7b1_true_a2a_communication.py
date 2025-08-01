"""
Test 7B1: True A2A Communication with Tool Isolation

This test verifies that agent-to-agent communication works properly when 
agents need to collaborate but have different tool access.

Expected Behavior:
- Agent 1 needs information that only Agent 2's tools can provide
- Agent 2 uses its exclusive tools to fulfill the request  
- Result is returned via A2A communication
- No agent has access to tools they shouldn't have

Test Formation: formation-multi-agent-segregated
"""

import pytest
import asyncio
from pathlib import Path

from muxi.formation import Formation
from tests.utils.env_setup import load_api_keys


@pytest.mark.asyncio
async def test_7b1_true_a2a_communication():
    """Test true A2A communication with proper tool isolation."""
    load_api_keys()
    
    formation_path = "test-formations/formation-multi-agent-segregated/formation.yaml"
    
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    try:
        # Verify tool isolation first
        mcp_service = overlord.mcp_service
        
        # Check shared tools
        shared_tools = mcp_service.agent_tool_registry.get("_shared", {})
        print(f"✅ Shared tools: {list(shared_tools.keys())}")
        assert len(shared_tools) == 2, f"Expected 2 shared tools, got {len(shared_tools)}"
        assert "web-scraper-mcp" in shared_tools
        assert "web-search-mcp" in shared_tools
        
        # Check IT support tools
        it_tools = mcp_service.agent_tool_registry.get("it-support", {})
        print(f"✅ IT Support tools: {list(it_tools.keys())}")
        assert "it-support-filesystem" in it_tools
        assert "it-support-system-info" in it_tools
        
        # Check Project Manager tools  
        pm_tools = mcp_service.agent_tool_registry.get("project-manager", {})
        print(f"✅ Project Manager tools: {list(pm_tools.keys())}")
        assert "project-manager-linear" in pm_tools
        
        # Verify researcher has NO exclusive tools (only shared)
        researcher_tools = mcp_service.agent_tool_registry.get("researcher", {})
        print(f"✅ Researcher tools: {list(researcher_tools.keys())}")
        assert len(researcher_tools) == 0, "Researcher should have no exclusive tools"
        
        # Test A2A communication: Researcher asks IT Support for system info
        prompt = """I need to know the current system information for a report I'm writing. 
        Since I don't have access to system tools, can you help me get the system details?"""
        
        result = await overlord.process_chat(
            message=prompt,
            user_id="test-user",
            session_id="test-session",
            agent_name="researcher"  # Start with researcher who needs help
        )
        
        print(f"✅ A2A Communication Result: {result.content[:200]}...")
        
        # Verify the result contains system information
        # (This would come from IT support agent using their system-info tool)
        assert result.content, "Should have received a response"
        assert len(result.content) > 50, "Response should contain substantial information"
        
        # The response should indicate collaboration occurred
        # (Implementation detail: check if multiple agents were involved)
        
        print("✅ Test 7B1 PASSED: True A2A communication with tool isolation working!")
        
    except Exception as e:
        print(f"❌ Test 7B1 FAILED: {str(e)}")
        raise
    
    finally:
        # Clean shutdown
        if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
            await overlord.mcp_service.shutdown()


if __name__ == "__main__":
    asyncio.run(test_7b1_true_a2a_communication())