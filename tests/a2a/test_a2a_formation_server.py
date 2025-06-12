"""
Test A2A Formation Server Integration

This test verifies that the A2A Formation Server is properly integrated
with the Overlord and provides correct agent routing functionality.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
import aiohttp

from src.muxi.runtime.overlord import Overlord
from src.muxi.runtime.llm import LLM
from src.muxi.runtime.a2a.formation_server import A2AFormationServer


@pytest.fixture
def formation_config():
    """Formation configuration with A2A server enabled"""
    return {
        "name": "test-formation",
        "a2a": {
            "server": {
                "enabled": True,
                "port": 8182,  # Use different port for testing
                "host": "127.0.0.1",
                "trusted_endpoints": ["127.0.0.1", "localhost"],
                "mode": "none"
            },
            "registries": ["http://localhost:9090"]
        }
    }


@pytest.fixture
def disabled_formation_config():
    """Formation configuration with A2A server disabled"""
    return {
        "name": "test-formation-disabled",
        "a2a": {
            "server": {
                "enabled": False,
                "port": 8183,
                "host": "127.0.0.1"
            }
        }
    }


@pytest.fixture
def mock_model():
    """Mock LLM model for testing"""
    model = MagicMock(spec=LLM)
    model.chat = AsyncMock(return_value="Test response from agent")
    model.run = AsyncMock(return_value="Test response from agent")
    return model


class TestA2AFormationServerIntegration:
    """Test A2A Formation Server integration with Overlord"""

    def test_formation_server_initialization_enabled(self, formation_config, mock_model):
        """Test that formation server is initialized when enabled"""
        overlord = Overlord(formation_config=formation_config)

        # Verify formation server was created
        assert overlord.formation_server is not None
        assert isinstance(overlord.formation_server, A2AFormationServer)
        assert overlord.formation_server.port == 8182
        assert overlord.formation_server.host == "127.0.0.1"
        assert overlord.formation_server.formation_name == "test-formation"
        assert overlord.formation_server.auth_mode == "none"
        assert overlord.formation_server.trusted_endpoints == ["127.0.0.1", "localhost"]

    def test_formation_server_initialization_disabled(self, disabled_formation_config, mock_model):
        """Test that formation server is not initialized when disabled"""
        overlord = Overlord(formation_config=disabled_formation_config)

        # Verify formation server was not created
        assert overlord.formation_server is None

    def test_formation_server_initialization_no_config(self, mock_model):
        """Test that formation server is not initialized without config"""
        overlord = Overlord()

        # Verify formation server was not created
        assert overlord.formation_server is None

    @pytest.mark.asyncio
    async def test_formation_server_lifecycle(self, formation_config, mock_model):
        """Test starting and stopping the formation server"""
        overlord = Overlord(formation_config=formation_config)

        # Add a test agent
        _ = overlord.create_agent(
            agent_id="test-agent",
            model=mock_model,
            description="Test agent for A2A communication"
        )

        # Start the formation server
        start_result = await overlord.start_formation_server()
        assert start_result["status"] == "started"
        assert start_result["port"] == 8182
        assert "test-agent" in start_result["agents"]

        # Check server status
        status = await overlord.get_formation_server_status()
        assert status["running"] is True
        assert status["port"] == 8182

        # Stop the formation server
        stop_result = await overlord.stop_formation_server()
        assert stop_result["status"] == "stopped"

        # Check server status after stopping
        status = await overlord.get_formation_server_status()
        assert status["running"] is False

    @pytest.mark.asyncio
    async def test_formation_server_health_endpoints(self, formation_config, mock_model):
        """Test that formation server health endpoints work"""
        overlord = Overlord(formation_config=formation_config)

        # Add a test agent
        _ = overlord.create_agent(
            agent_id="health-test-agent",
            model=mock_model,
            description="Agent for health endpoint testing",
            a2a_external=True
        )

        # Start the formation server
        await overlord.start_formation_server()

        try:
            # Test health endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get("http://127.0.0.1:8182/health") as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data["status"] == "healthy"
                    assert data["formation"] == "test-formation"
                    assert "health-test-agent" in data["agents"]

                # Test formation info endpoint
                async with session.get("http://127.0.0.1:8182/info") as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data["formation"] == "test-formation"
                    assert data["server_mode"] == "none"
                    assert "health-test-agent" in data["agents"]
                    assert data["total_agents"] == 1

                # Test agent discovery endpoint
                async with session.get("http://127.0.0.1:8182/agents") as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data["formation"] == "test-formation"
                    assert len(data["agents"]) == 1

                    agent_card = data["agents"][0]
                    assert agent_card["name"] == "health-test-agent"
                    assert agent_card["formation"] == "test-formation"
                    assert "capabilities" in agent_card

        finally:
            # Clean up
            await overlord.stop_formation_server()

    @pytest.mark.asyncio
    async def test_agent_message_routing(self, formation_config, mock_model):
        """Test that agent messages are properly routed"""
        overlord = Overlord(formation_config=formation_config)

        # Add a test agent
        _ = overlord.create_agent(
            agent_id="routing-test-agent",
            model=mock_model,
            description="Agent for message routing testing",
            a2a_external=True
        )

        # Start the formation server
        await overlord.start_formation_server()

        try:
            # Test agent message endpoint
            message_payload = {
                "message": "Hello from external agent",
                "message_type": "request",
                "context": {"test": True},
                "message_id": "test-message-123"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://127.0.0.1:8182/agents/routing-test-agent/message",
                    json=message_payload
                ) as response:
                    assert response.status == 200
                    data = await response.json()

                    assert data["status"] == "success"
                    assert data["agent_id"] == "routing-test-agent"
                    assert data["message_id"] == "test-message-123"
                    assert data["response"] == "Test response from agent"

                    # Verify the mock was called
                    mock_model.run.assert_called_once_with("Hello from external agent")

        finally:
            # Clean up
            await overlord.stop_formation_server()

    @pytest.mark.asyncio
    async def test_agent_not_found_error(self, formation_config, mock_model):
        """Test that non-existent agents return 404"""
        overlord = Overlord(formation_config=formation_config)

        # Start the formation server without adding any agents
        await overlord.start_formation_server()

        try:
            message_payload = {
                "message": "Hello to non-existent agent",
                "message_type": "request"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://127.0.0.1:8182/agents/non-existent-agent/message",
                    json=message_payload
                ) as response:
                    assert response.status == 404
                    data = await response.json()
                    assert "not found" in data["detail"].lower()

        finally:
            # Clean up
            await overlord.stop_formation_server()

    @pytest.mark.asyncio
    async def test_trusted_endpoints_security(self, mock_model):
        """Test that trusted endpoints security works"""
        # Configuration with restricted trusted endpoints
        config = {
            "name": "secure-formation",
            "a2a": {
                "server": {
                    "enabled": True,
                    "port": 8184,
                    "host": "127.0.0.1",
                    "trusted_endpoints": ["192.168.1.100"],  # Only allow specific IP
                    "mode": "none"
                }
            }
        }

        overlord = Overlord(formation_config=config)

        # Add a test agent
        _ = overlord.create_agent(
            agent_id="security-test-agent",
            model=mock_model,
            description="Agent for security testing",
            a2a_external=True
        )

        # Start the formation server
        await overlord.start_formation_server()

        try:
            message_payload = {
                "message": "Hello from untrusted source",
                "message_type": "request"
            }

            # Try to access from localhost (should be blocked)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://127.0.0.1:8184/agents/security-test-agent/message",
                    json=message_payload
                ) as response:
                    assert response.status == 403
                    data = await response.json()
                    assert "not in trusted endpoints" in data["detail"]

        finally:
            # Clean up
            await overlord.stop_formation_server()

    def test_server_management_methods_without_server(self, mock_model):
        """Test server management methods when no server is configured"""
        overlord = Overlord()  # No formation config

        # Test methods return appropriate error messages
        asyncio.run(self._test_no_server_configured(overlord))

    async def _test_no_server_configured(self, overlord):
        """Helper method for testing server methods without configuration"""
        start_result = await overlord.start_formation_server()
        assert start_result["status"] == "error"
        assert "not configured" in start_result["message"]

        stop_result = await overlord.stop_formation_server()
        assert stop_result["status"] == "error"
        assert "not configured" in stop_result["message"]

        status_result = await overlord.get_formation_server_status()
        assert status_result["status"] == "not_configured"
        assert "not configured" in status_result["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
