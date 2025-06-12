"""
Comprehensive A2A Communication Pattern Tests

Tests sync/async communication patterns, external agent communication,
and various A2A protocol scenarios.
"""

import asyncio
import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
import time

from src.muxi.runtime.overlord import Overlord
from src.muxi.runtime.llm import LLM


class MockExternalAgent:
    """Mock external agent for testing cross-formation communication"""

    def __init__(self, agent_id: str, port: int = 8190):
        self.agent_id = agent_id
        self.port = port
        self.received_messages = []
        self.app = None
        self.server_task = None

    async def start_mock_server(self):
        """Start a mock external agent server"""
        from fastapi import FastAPI
        import uvicorn

        self.app = FastAPI()

        @self.app.post(f"/agents/{self.agent_id}/message")
        async def handle_message(request: dict):
            self.received_messages.append(request)
            return {
                "status": "success",
                "response": (
                    f"External agent {self.agent_id} received: "
                    f"{request.get('message', '')}"
                ),
                "agent_id": self.agent_id,
                "message_id": request.get("message_id", "unknown")
            }

        config = uvicorn.Config(
            app=self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="error"
        )
        server = uvicorn.Server(config)
        self.server_task = asyncio.create_task(server.serve())

        # Wait for server to start
        await asyncio.sleep(0.5)

    async def stop_mock_server(self):
        """Stop the mock external agent server"""
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass


@pytest.fixture
async def formation_overlord():
    """Create an overlord with formation server for testing"""
    formation_config = {
        "name": "test-formation",
        "a2a": {
            "server": {
                "enabled": True,
                "port": 8186,  # Different port to avoid conflicts
                "host": "127.0.0.1",
                "trusted_endpoints": ["127.0.0.1", "localhost"],
                "mode": "none"
            }
        }
    }

    # Create mock model with proper chat method
    mock_model = MagicMock(spec=LLM)
    mock_model.chat = AsyncMock(return_value="Response from agent")

    overlord = Overlord(formation_config=formation_config)

    # Add test agents
    for i in range(3):
        overlord.create_agent(
            agent_id=f"agent-{i}",
            model=mock_model,
            description=f"Test agent {i} for A2A communication",
            a2a_external=True,
            a2a_internal=True
        )

    # Start formation server
    await overlord.start_formation_server()

    yield overlord

    # Cleanup
    await overlord.stop_formation_server()


@pytest.mark.asyncio
class TestSyncAsyncPatterns:
    """Test synchronous and asynchronous communication patterns"""

    async def test_synchronous_request_response(self, formation_overlord):
        """Test synchronous request-response pattern"""
        overlord = formation_overlord

        # Test internal sync communication
        response = await overlord.route_a2a_message(
            source_agent_id="agent-0",
            target_agent_id="agent-1",
            message="Sync test message",
            message_type="request",
            wait_for_response=True,
            timeout=5
        )

        assert response is not None
        assert "Response from agent" in str(response)

    async def test_asynchronous_fire_and_forget(self, formation_overlord):
        """Test asynchronous fire-and-forget pattern"""
        overlord = formation_overlord

        # Test async notification (no response expected)
        start_time = time.time()
        response = await overlord.route_a2a_message(
            source_agent_id="agent-0",
            target_agent_id="agent-1",
            message="Async notification",
            message_type="notification",
            wait_for_response=False
        )
        end_time = time.time()

        # Should return quickly without waiting for response
        assert (end_time - start_time) < 1.0
        assert response is None  # No response for notifications

    async def test_concurrent_message_handling(self, formation_overlord):
        """Test handling multiple concurrent A2A messages"""
        overlord = formation_overlord

        # Send multiple concurrent messages
        tasks = []
        for i in range(10):
            task = overlord.route_a2a_message(
                source_agent_id="agent-0",
                target_agent_id="agent-1",
                message=f"Concurrent message {i}",
                message_type="request",
                wait_for_response=True,
                timeout=10
            )
            tasks.append(task)

        # Wait for all to complete
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed
        assert len(responses) == 10
        successful_responses = [r for r in responses if not isinstance(r, Exception)]
        assert len(successful_responses) == 10

    async def test_timeout_handling(self, formation_overlord):
        """Test timeout handling for slow responses"""
        overlord = formation_overlord

        # Create slow mock agent
        async def slow_chat_response(msg):
            await asyncio.sleep(5)  # 5 second delay
            return "Slow response"

        slow_model = MagicMock(spec=LLM)
        slow_model.chat = AsyncMock(side_effect=slow_chat_response)

        overlord.create_agent(
            agent_id="slow-agent",
            model=slow_model,
            description="Slow responding agent",
            a2a_internal=True
        )

        # Test that timeout is respected
        start_time = time.time()
        response = await overlord.route_a2a_message(
            source_agent_id="agent-0",
            target_agent_id="slow-agent",
            message="This should timeout",
            message_type="request",
            wait_for_response=True,
            timeout=1  # 1 second timeout
        )
        end_time = time.time()

        # Should timeout in approximately 1 second
        assert (end_time - start_time) < 2.0

        # Should return error response due to timeout
        assert response is not None
        assert response["status"] == "error"
        assert "timed out" in response["error"].lower()


@pytest.mark.asyncio
class TestExternalCommunication:
    """Test communication with external agents and formations"""

    async def test_external_agent_discovery(self, formation_overlord):
        """Test discovery of external agents via HTTP"""
        # Test the /agents discovery endpoint
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8186/agents") as response:
                assert response.status == 200
                data = await response.json()

                assert "agents" in data
                assert len(data["agents"]) == 3  # 3 test agents
                assert data["formation"] == "test-formation"

                # Verify agent card structure
                agent_card = data["agents"][0]
                assert "name" in agent_card
                assert "description" in agent_card
                assert "url" in agent_card
                assert "capabilities" in agent_card
                assert "formation" in agent_card

    async def test_external_agent_communication(self, formation_overlord):
        """Test sending messages to external agents"""
        # Start mock external agent
        external_agent = MockExternalAgent("external-test-agent", port=8190)
        await external_agent.start_mock_server()

        try:
            # Test communication via HTTP (simulating external formation)
            async with aiohttp.ClientSession() as session:
                message_payload = {
                    "message": "Hello from test formation",
                    "message_type": "request",
                    "context": {"source_formation": "test-formation"},
                    "message_id": "external-test-123"
                }

                async with session.post(
                    "http://127.0.0.1:8190/agents/external-test-agent/message",
                    json=message_payload
                ) as response:
                    assert response.status == 200
                    data = await response.json()

                    assert data["status"] == "success"
                    assert data["agent_id"] == "external-test-agent"
                    assert "Hello from test formation" in data["response"]

                # Verify the external agent received the message
                assert len(external_agent.received_messages) == 1
                received = external_agent.received_messages[0]
                assert received["message"] == "Hello from test formation"

        finally:
            await external_agent.stop_mock_server()

    async def test_bidirectional_external_communication(self, formation_overlord):
        """Test bidirectional communication between formations"""
        # Start mock external agent
        external_agent = MockExternalAgent("partner-agent", port=8191)
        await external_agent.start_mock_server()

        try:
            # Step 1: External agent sends message to our formation
            async with aiohttp.ClientSession() as session:
                # External -> Local
                message_payload = {
                    "message": "Request from partner formation",
                    "message_type": "request",
                    "context": {"source_formation": "partner-formation"},
                    "message_id": "partner-request-456"
                }

                async with session.post(
                    "http://127.0.0.1:8186/agents/agent-0/message",
                    json=message_payload
                ) as response:
                    assert response.status == 200
                    local_response = await response.json()
                    assert local_response["status"] == "success"

                # Step 2: Our formation responds to external agent
                response_payload = {
                    "message": "Response from test formation",
                    "message_type": "response",
                    "context": {"response_to": "partner-request-456"},
                    "message_id": "test-response-789"
                }

                async with session.post(
                    "http://127.0.0.1:8191/agents/partner-agent/message",
                    json=response_payload
                ) as response:
                    assert response.status == 200
                    external_response = await response.json()
                    assert external_response["status"] == "success"

                # Verify bidirectional communication worked
                assert len(external_agent.received_messages) == 1
                received = external_agent.received_messages[0]
                assert received["message"] == "Response from test formation"

        finally:
            await external_agent.stop_mock_server()


@pytest.mark.asyncio
class TestSecurityAndValidation:
    """Test security features and message validation"""

    async def test_trusted_endpoint_validation(self):
        """Test that untrusted endpoints are rejected"""
        formation_config = {
            "name": "secure-formation",
            "a2a": {
                "server": {
                    "enabled": True,
                    "port": 8187,
                    "host": "127.0.0.1",
                    "trusted_endpoints": ["trusted-host.com"],  # Specific trusted host
                    "mode": "none"
                }
            }
        }

        mock_model = MagicMock(spec=LLM)
        mock_model.chat = AsyncMock(return_value="Response")

        overlord = Overlord(formation_config=formation_config)
        overlord.create_agent(
            agent_id="secure-agent",
            model=mock_model,
            a2a_external=True
        )

        await overlord.start_formation_server()

        try:
            # Test that localhost (untrusted) is rejected
            async with aiohttp.ClientSession() as session:
                message_payload = {
                    "message": "Untrusted request",
                    "message_type": "request"
                }

                async with session.post(
                    "http://127.0.0.1:8187/agents/secure-agent/message",
                    json=message_payload
                ) as response:
                    # Should be rejected due to untrusted endpoint
                    assert response.status == 403

        finally:
            await overlord.stop_formation_server()

    async def test_agent_a2a_disabled(self, formation_overlord):
        """Test that agents with A2A disabled reject external messages"""
        overlord = formation_overlord

        # Create agent with external A2A disabled
        mock_model = MagicMock(spec=LLM)
        mock_model.chat = AsyncMock(return_value="Should not be called")

        overlord.create_agent(
            agent_id="private-agent",
            model=mock_model,
            a2a_external=False  # Disable external A2A
        )

        # Try to send external message to disabled agent
        async with aiohttp.ClientSession() as session:
            message_payload = {
                "message": "This should be rejected",
                "message_type": "request"
            }

            async with session.post(
                "http://127.0.0.1:8186/agents/private-agent/message",
                json=message_payload
            ) as response:
                # Should be rejected
                assert response.status == 403
                error_data = await response.json()
                assert "not configured for external A2A" in error_data["detail"]


@pytest.mark.asyncio
async def test_formation_server_performance():
    """Test performance characteristics of formation server"""
    formation_config = {
        "name": "performance-test",
        "a2a": {
            "server": {
                "enabled": True,
                "port": 8188,
                "host": "127.0.0.1",
                "trusted_endpoints": ["127.0.0.1"],
                "mode": "none"
            }
        }
    }

    # Create fast-responding mock
    mock_model = MagicMock(spec=LLM)
    mock_model.chat = AsyncMock(return_value="Fast response")

    overlord = Overlord(formation_config=formation_config)

    # Create multiple agents
    for i in range(5):
        overlord.create_agent(
            agent_id=f"perf-agent-{i}",
            model=mock_model,
            a2a_external=True
        )

    await overlord.start_formation_server()

    try:
        # Test rapid sequential requests
        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(50):  # 50 rapid requests
                task = session.post(
                    f"http://127.0.0.1:8188/agents/perf-agent-{i % 5}/message",
                    json={
                        "message": f"Performance test {i}",
                        "message_type": "request"
                    }
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks)

            # Verify all succeeded
            for response in responses:
                assert response.status == 200
                response.close()

        end_time = time.time()
        duration = end_time - start_time

        # Should handle 50 requests reasonably quickly (less than 10 seconds)
        assert duration < 10.0
        print(f"✅ Handled 50 requests in {duration:.2f} seconds ({50/duration:.1f} req/sec)")

    finally:
        await overlord.stop_formation_server()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
