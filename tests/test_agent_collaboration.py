"""
Tests for Agent Collaboration Infrastructure

This module tests the peer-to-peer collaboration capabilities between agents,
including consultation, information sharing, expertise discovery, and coordination.
"""

import pytest
import sys
import os
from unittest.mock import patch

try:
    from runtime.muxi.runtime.overlord import Overlord
except ImportError:
    # Add the runtime directory to the Python path for testing
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))
    from runtime.muxi.runtime.overlord import Overlord


class MockLLM:
    """Mock LLM for testing purposes."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_count = 0

    async def chat(self, messages):
        """Mock chat method that returns predefined responses."""
        self.call_count += 1
        # Return a response based on the last message content
        if messages:
            last_message = messages[-1].get('content', '')
            if 'CONSULTATION REQUEST' in last_message:
                return "Here's my expert advice on this topic. Based on best practices..."
            elif 'security' in last_message.lower():
                return "Security recommendation: Use multi-factor authentication..."
            elif 'coordination' in last_message.lower():
                return "Coordination acknowledged. Ready to proceed with next steps."

        return "Mock response from LLM"


class TestAgentCollaboration:
    """Test suite for agent collaboration functionality."""

    @pytest.fixture
    async def overlord(self):
        """Create a test overlord with mock configuration."""
        overlord = Overlord()
        return overlord

    @pytest.fixture
    async def agents(self, overlord):
        """Create test agents for collaboration testing."""
        # Create mock models
        security_model = MockLLM()
        research_model = MockLLM()
        deployment_model = MockLLM()

        # Create agents
        security_agent = overlord.create_agent(
            agent_id="security-expert",
            model=security_model,
            system_message="You are a cybersecurity expert."
        )

        research_agent = overlord.create_agent(
            agent_id="research-agent",
            model=research_model,
            system_message="You are a research specialist."
        )

        deployment_agent = overlord.create_agent(
            agent_id="deployment-agent",
            model=deployment_model,
            system_message="You are a deployment specialist."
        )

        return {
            "security": security_agent,
            "research": research_agent,
            "deployment": deployment_agent
        }

    @pytest.mark.asyncio
    async def test_expertise_registration(self, overlord, agents):
        """Test agent expertise registration functionality."""
        security_agent = agents["security"]

        # Register expertise
        success = await security_agent.register_expertise(
            expertise_areas=["cybersecurity", "penetration_testing", "security_auditing"],
            proficiency_levels={
                "cybersecurity": "expert",
                "penetration_testing": "master",
                "security_auditing": "expert"
            }
        )

        assert success is True

        # Verify expertise was registered in overlord
        expertise_record = overlord._agent_expertise.get("security-expert")
        assert expertise_record is not None
        assert "cybersecurity" in expertise_record["expertise_areas"]
        assert expertise_record["proficiency_levels"]["cybersecurity"] == "expert"

    @pytest.mark.asyncio
    async def test_expert_discovery(self, overlord, agents):
        """Test finding experts by topic."""
        security_agent = agents["security"]
        research_agent = agents["research"]

        # Register expertise for security agent
        await security_agent.register_expertise(
            expertise_areas=["cybersecurity", "network_security"],
            proficiency_levels={"cybersecurity": "expert", "network_security": "master"}
        )

        # Register expertise for research agent
        await research_agent.register_expertise(
            expertise_areas=["data_analysis", "machine_learning"],
            proficiency_levels={"data_analysis": "expert", "machine_learning": "intermediate"}
        )

        # Find security experts
        security_experts = await research_agent.find_expert(
            topic="security",
            min_proficiency="expert"
        )

        assert len(security_experts) == 1
        assert "security-expert" in security_experts
        assert security_experts["security-expert"]["proficiency"] in ["expert", "master"]

        # Find machine learning experts (should include research agent)
        ml_experts = await security_agent.find_expert(
            topic="machine_learning",
            min_proficiency="intermediate"
        )

        assert len(ml_experts) == 1
        assert "research-agent" in ml_experts

    @pytest.mark.asyncio
    async def test_consultation_request(self, overlord, agents):
        """Test consultation request between agents."""
        security_agent = agents["security"]
        research_agent = agents["research"]

        # Register security expertise
        await security_agent.register_expertise(
            expertise_areas=["cybersecurity"],
            proficiency_levels={"cybersecurity": "expert"}
        )

        # Mock the A2A messaging infrastructure
        with patch.object(research_agent, 'send_a2a_message') as mock_send:
            mock_send.return_value = {
                "status": "success",
                "response": "Use HTTPS, implement proper authentication, and validate all inputs.",
                "consultation_topic": "API security",
                "expert_agent": "security-expert"
            }

            # Request consultation
            response = await research_agent.request_consultation(
                target_agent_id="security-expert",
                topic="API security best practices",
                context={"project": "user-management-api"}
            )

            # Verify consultation was requested
            assert mock_send.called
            assert response["status"] == "success"
            assert "security" in response["response"]

    @pytest.mark.asyncio
    async def test_information_sharing(self, overlord, agents):
        """Test information sharing between agents."""
        security_agent = agents["security"]

        # Mock the A2A messaging infrastructure
        with patch.object(security_agent, 'send_a2a_message') as mock_send:
            mock_send.return_value = None  # Notifications don't return responses

            # Share information
            success = await security_agent.share_information(
                target_agent_id="research-agent",
                information="New vulnerability discovered in library X version 1.2.3",
                topic="security_alerts",
                relevance_reason="You're working on dependency analysis"
            )

            # Verify information was shared
            assert mock_send.called
            assert success is True

            # Check the call arguments
            call_args = mock_send.call_args
            assert call_args[1]["message_type"] == "notification"
            assert call_args[1]["wait_for_response"] is False

    @pytest.mark.asyncio
    async def test_peer_coordination(self, overlord, agents):
        """Test peer coordination between agents."""
        research_agent = agents["research"]

        # Mock the A2A messaging infrastructure
        with patch.object(research_agent, 'send_a2a_message') as mock_send:
            mock_send.return_value = {
                "status": "success",
                "response": "Task handoff acknowledged. Ready to proceed with deployment.",
                "coordination_type": "handoff",
                "coordinated_with": "deployment-agent"
            }

            # Coordinate task handoff
            response = await research_agent.coordinate_with_peer(
                peer_agent_id="deployment-agent",
                coordination_type="handoff",
                details={
                    "task": "API testing complete",
                    "next_step": "deployment",
                    "artifacts": ["test_results.json", "coverage_report.html"]
                }
            )

            # Verify coordination was successful
            assert mock_send.called
            assert response["status"] == "success"
            assert response["coordination_type"] == "handoff"

    @pytest.mark.asyncio
    async def test_handle_consultation_request(self, overlord, agents):
        """Test handling of incoming consultation requests."""
        security_agent = agents["security"]

        # Test consultation handling
        response = await security_agent._handle_consultation_request(
            source_agent_id="research-agent",
            message="What are the best practices for API authentication?",
            context={
                "collaboration_type": "consultation",
                "topic": "API authentication",
                "context": {"project": "user-management"}
            },
            message_id="test-msg-123"
        )

        assert response["status"] == "success"
        assert "expert advice" in response["response"]
        assert response["consultation_topic"] == "API authentication"
        assert response["expert_agent"] == "security-expert"

    @pytest.mark.asyncio
    async def test_handle_information_sharing(self, overlord, agents):
        """Test handling of incoming information sharing."""
        research_agent = agents["research"]

        # Mock overlord memory operations
        with patch.object(overlord, 'add_to_buffer_memory') as mock_memory:
            # Test information sharing handling
            result = await research_agent._handle_information_sharing(
                source_agent_id="security-expert",
                message="New security vulnerability in library X",
                context={
                    "collaboration_type": "information_sharing",
                    "topic": "security_alerts",
                    "relevance_reason": "Working on dependency analysis"
                },
                message_id="test-msg-124"
            )

            # Information sharing returns None (it's a notification)
            assert result is None

            # Verify memory storage was attempted
            assert mock_memory.called

    @pytest.mark.asyncio
    async def test_handle_peer_coordination(self, overlord, agents):
        """Test handling of peer coordination requests."""
        deployment_agent = agents["deployment"]

        # Test handoff coordination
        response = await deployment_agent._handle_peer_coordination(
            source_agent_id="research-agent",
            message="Coordination request: handoff",
            context={
                "collaboration_type": "peer_coordination",
                "coordination_type": "handoff",
                "details": {
                    "task": "API testing complete",
                    "next_step": "deployment",
                    "artifacts": ["test_results.json"]
                }
            },
            message_id="test-msg-125"
        )

        assert response["status"] == "success"
        assert "handoff acknowledged" in response["response"]
        assert response["coordination_type"] == "handoff"

    @pytest.mark.asyncio
    async def test_collaboration_message_routing(self, overlord, agents):
        """Test that collaboration messages are routed correctly."""
        security_agent = agents["security"]

        # Test consultation message routing
        consultation_response = await security_agent.handle_a2a_message(
            source_agent_id="research-agent",
            message="Need help with security implementation",
            message_type="request",
            context={
                "collaboration_type": "consultation",
                "topic": "security_implementation",
                "context": {}
            },
            message_id="test-consultation"
        )

        assert consultation_response["status"] == "success"
        assert "expert advice" in consultation_response["response"]

        # Test information sharing message routing
        sharing_response = await security_agent.handle_a2a_message(
            source_agent_id="research-agent",
            message="Important security update",
            message_type="notification",
            context={
                "collaboration_type": "information_sharing",
                "topic": "security_updates",
                "relevance_reason": "For your current project"
            },
            message_id="test-sharing"
        )

        # Information sharing returns None (notification)
        assert sharing_response is None

    @pytest.mark.asyncio
    async def test_collaboration_stats(self, overlord, agents):
        """Test collaboration statistics functionality."""
        security_agent = agents["security"]
        research_agent = agents["research"]

        # Register expertise for multiple agents
        await security_agent.register_expertise(
            expertise_areas=["cybersecurity", "network_security"],
            proficiency_levels={"cybersecurity": "expert", "network_security": "master"}
        )

        await research_agent.register_expertise(
            expertise_areas=["data_analysis", "cybersecurity"],
            proficiency_levels={"data_analysis": "expert", "cybersecurity": "intermediate"}
        )

        # Get collaboration stats
        stats = overlord.get_collaboration_stats()

        assert stats["total_agents"] == 3
        assert stats["agents_with_expertise"] == 2
        assert stats["total_expertise_areas"] == 4  # 2 + 2 areas

        # Check most common expertise
        most_common = stats["most_common_expertise"]
        cybersecurity_count = next(
            (item["agent_count"] for item in most_common if item["area"] == "cybersecurity"),
            0
        )
        assert cybersecurity_count == 2  # Both agents have cybersecurity

    @pytest.mark.asyncio
    async def test_error_handling(self, overlord, agents):
        """Test error handling in collaboration methods."""
        security_agent = agents["security"]

        # Test consultation with non-existent agent
        with patch.object(security_agent, 'send_a2a_message') as mock_send:
            mock_send.side_effect = Exception("Connection failed")

            response = await security_agent.request_consultation(
                target_agent_id="non-existent-agent",
                topic="test topic"
            )

            assert response is None

        # Test information sharing with error
        with patch.object(security_agent, 'send_a2a_message') as mock_send:
            mock_send.side_effect = Exception("Network error")

            success = await security_agent.share_information(
                target_agent_id="non-existent-agent",
                information="test info",
                topic="test"
            )

            assert success is False

    @pytest.mark.asyncio
    async def test_expertise_proficiency_filtering(self, overlord, agents):
        """Test that expertise discovery respects proficiency level requirements."""
        security_agent = agents["security"]
        research_agent = agents["research"]

        # Register expertise with different proficiency levels
        await security_agent.register_expertise(
            expertise_areas=["cybersecurity"],
            proficiency_levels={"cybersecurity": "master"}
        )

        await research_agent.register_expertise(
            expertise_areas=["cybersecurity"],
            proficiency_levels={"cybersecurity": "novice"}
        )

        # Find experts with minimum expert level
        experts = await security_agent.find_expert(
            topic="cybersecurity",
            min_proficiency="expert"
        )

        # Should not include research agent (only novice level)
        assert len(experts) == 0  # security agent excluded (self)

        # Find experts with minimum novice level
        experts = await security_agent.find_expert(
            topic="cybersecurity",
            min_proficiency="novice"
        )

        # Should include research agent
        assert len(experts) == 1
        assert "research-agent" in experts


if __name__ == "__main__":
    pytest.main([__file__])
