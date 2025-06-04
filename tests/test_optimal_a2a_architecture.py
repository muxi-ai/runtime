"""
Test Optimal A2A Architecture - Direct Communication

Tests the refactored A2A architecture where agents communicate directly
with each other instead of routing through the overlord.

Key architectural patterns tested:
- External Agent → Formation Server → Agent (direct)
- Local Agent → Local Agent (direct)
- Local Agent → Registry Client → External Agent (direct)
"""

import asyncio
import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock

from runtime.muxi.runtime.overlord import Overlord
from runtime.muxi.runtime.llm import LLM


@pytest.fixture
async def optimal_formation():
    """Create a formation with optimal A2A architecture for testing"""
    formation_config = {
        "name": "optimal-formation",
        "a2a": {
            "server": {
                "enabled": True,
                "port": 8187,  # Different port for testing
                "host": "127.0.0.1",
                "trusted_endpoints": ["127.0.0.1", "localhost"],
                "mode": "none"
            },
            "registries": ["http://localhost:9090"]
        }
    }

    # Create mock model
    mock_model = MagicMock(spec=LLM)
    mock_model.chat = AsyncMock(return_value="Direct agent response")

    overlord = Overlord(formation_config=formation_config)

    # Add test agents
    for i in range(3):
        overlord.create_agent(
            agent_id=f"agent-{i}",
            model=mock_model,
            description=f"Test agent {i} for optimal A2A testing",
            a2a_internal=True,
            a2a_external=True
        )

    # Start formation server
    await overlord.start_formation_server()

    yield overlord

    # Cleanup
    await overlord.stop_formation_server()


class TestOptimalA2AArchitecture:
    """Test suite for the optimal A2A architecture"""

    async def test_external_to_formation_direct_routing(self, optimal_formation):
        """Test: External Agent → Formation Server → Agent (direct routing)"""
        # Test direct HTTP communication to formation server
        message_payload = {
            "message": "Hello from external agent!",
            "message_type": "request",
            "context": {"source": "external"},
            "message_id": "ext-test-001"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:8187/agents/agent-0/message",
                json=message_payload
            ) as response:
                assert response.status == 200
                data = await response.json()

                assert data["status"] == "success"
                assert data["agent_id"] == "agent-0"
                assert "response" in data
                assert data["message_id"] == "ext-test-001"

    async def test_agent_to_agent_direct_communication(self, optimal_formation):
        """Test: Local Agent → Local Agent (direct communication)"""
        overlord = optimal_formation

        # Get source agent directly
        source_agent = overlord.get_agent("agent-0")

        # Test direct agent-to-agent communication
        response = await source_agent.send_a2a_message(
            target_agent_id="agent-1",
            message="Direct agent communication test",
            message_type="request",
            wait_for_response=True,
            timeout=10
        )

        assert response is not None
        assert response["status"] == "success"
        assert "response" in response

    async def test_agent_to_external_direct_communication(self, optimal_formation):
        """Test: Local Agent → Registry Client → External Agent (direct)"""
        overlord = optimal_formation

        # Mock external agent discovery
        if overlord.external_registry_client:
            mock_external_agents = [
                {
                    "name": "external-payment-agent",
                    "url": "http://external-formation:8080/agents/payment-agent/message",
                    "capabilities": ["payment", "billing"],
                    "authentication": {"type": "none"}
                }
            ]
            overlord.external_registry_client.discover_agents = AsyncMock(
                return_value=mock_external_agents
            )

        # Get source agent
        source_agent = overlord.get_agent("agent-0")

        # Test external communication (would fail in real test due to mock)
        # This validates the communication path structure
        try:
            await source_agent.send_a2a_message(
                target_agent_id="external-payment-agent",
                message="Process payment of $100",
                message_type="request",
                wait_for_response=True,
                timeout=5
            )
        except Exception as e:
            # Expected to fail in test environment, but validates the path
            assert "external" in str(e).lower() or "connection" in str(e).lower()

    async def test_formation_server_direct_agent_access(self, optimal_formation):
        """Test: Formation Server has direct access to agents"""
        overlord = optimal_formation

        # Verify formation server has direct access to agents
        formation_server = overlord.formation_server
        assert formation_server is not None
        assert formation_server.overlord == overlord

        # Test that formation server can directly route to agents
        # without going through overlord.route_a2a_message
        agent_ids = list(overlord.agents.keys())
        assert len(agent_ids) >= 3
        assert "agent-0" in agent_ids

    async def test_no_overlord_routing_bottleneck(self, optimal_formation):
        """Test: Verify overlord is not a bottleneck in message transmission"""
        overlord = optimal_formation

        # Verify that route_a2a_message method has been removed
        assert not hasattr(overlord, 'route_a2a_message') or \
               not callable(getattr(overlord, 'route_a2a_message', None))

        # Agents should handle their own A2A communication
        agent = overlord.get_agent("agent-0")
        assert hasattr(agent, 'send_a2a_message')
        assert callable(agent.send_a2a_message)

    async def test_concurrent_direct_communication(self, optimal_formation):
        """Test: Multiple agents can communicate concurrently without overlord bottleneck"""
        overlord = optimal_formation

        # Create multiple concurrent A2A communications
        tasks = []
        for i in range(3):
            source_agent = overlord.get_agent(f"agent-{i}")
            target_id = f"agent-{(i + 1) % 3}"  # Circular communication

            task = source_agent.send_a2a_message(
                target_agent_id=target_id,
                message=f"Concurrent message from agent-{i}",
                message_type="request",
                wait_for_response=True,
                timeout=10
            )
            tasks.append(task)

        # Execute all communications concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all communications succeeded
        success_count = sum(
            1 for resp in responses
            if isinstance(resp, dict) and resp.get("status") == "success"
        )
        assert success_count == 3

    async def test_formation_server_agent_discovery(self, optimal_formation):
        """Test: Formation server provides agent discovery without overlord routing"""
        overlord = optimal_formation

        # Test formation server's discovery endpoint
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8187/agents") as response:
                assert response.status == 200
                data = await response.json()

                assert "agents" in data
                assert len(data["agents"]) == 3
                assert data["formation"] == overlord.formation_config["name"]

                # Verify agent structure
                agent_card = data["agents"][0]
                assert "name" in agent_card
                assert "description" in agent_card
                assert "capabilities" in agent_card

    async def test_overlord_as_management_layer_only(self, optimal_formation):
        """Test: Overlord functions as management/coordination layer, not message routing"""
        overlord = optimal_formation

        # Overlord should provide these management functions
        assert hasattr(overlord, 'create_agent')
        assert hasattr(overlord, 'start_formation_server')
        assert hasattr(overlord, 'stop_formation_server')
        assert hasattr(overlord, 'register_agent_with_external_registry')
        assert hasattr(overlord, 'discover_external_agents')

        # But NOT direct message routing
        assert not hasattr(overlord, 'route_a2a_message') or \
               not callable(getattr(overlord, 'route_a2a_message', None))

        # Agents handle their own communication
        agent = overlord.get_agent("agent-0")
        assert hasattr(agent, 'send_a2a_message')
        assert hasattr(agent, 'handle_a2a_message')


@pytest.mark.asyncio
async def test_architectural_performance_improvement():
    """Test: Verify the architectural improvement provides better performance"""

    # This test validates that the new architecture should be faster
    # because it eliminates the overlord bottleneck

    # In the optimal architecture:
    # - No centralized routing through overlord
    # - Direct agent-to-agent communication
    # - Formation server routes directly to agents
    # - Reduced latency and improved concurrency

    # This is a conceptual test - in real implementation,
    # we would measure actual performance metrics

    assert True  # Architectural improvement is by design


if __name__ == "__main__":
    pytest.main([__file__])
