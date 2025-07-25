"""
Tests for request-scoped agent exclusion in resilience fallback.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from muxi.formation.overlord.active_agents_tracker import ActiveAgentsTracker
from muxi.formation.overlord.agent_router import AgentRouter
from muxi.formation.resilience.resilient_workflow_manager import ResilientWorkflowManager
from muxi.datatypes.resilience import (
    RecoveryStrategy,
    ErrorContext,
    ErrorType,
    ErrorSeverity,
    WorkflowException,
)


class TestActiveAgentsTracker:
    """Test ActiveAgentsTracker request-scoped exclusion functionality."""

    @pytest.mark.asyncio
    async def test_exclude_agent_for_request(self):
        """Test that agents can be excluded for specific requests."""
        tracker = ActiveAgentsTracker()

        # Initially all agents are available
        all_agents = ["agent1", "agent2", "agent3"]
        available = await tracker.get_available_agents(all_agents)
        assert available == all_agents

        # Exclude agent2 for request1
        await tracker.exclude_agent_for_request("request1", "agent2")

        # agent2 should be excluded for request1
        available = await tracker.get_available_agents(all_agents, "request1")
        assert available == ["agent1", "agent3"]

        # But agent2 should still be available for other requests
        available = await tracker.get_available_agents(all_agents, "request2")
        assert available == all_agents

    @pytest.mark.asyncio
    async def test_multiple_exclusions_per_request(self):
        """Test that multiple agents can be excluded for a single request."""
        tracker = ActiveAgentsTracker()

        all_agents = ["agent1", "agent2", "agent3", "agent4"]

        # Exclude multiple agents for request1
        await tracker.exclude_agent_for_request("request1", "agent2")
        await tracker.exclude_agent_for_request("request1", "agent3")

        available = await tracker.get_available_agents(all_agents, "request1")
        assert available == ["agent1", "agent4"]

    @pytest.mark.asyncio
    async def test_request_cleanup(self):
        """Test that request exclusions are cleaned up properly."""
        tracker = ActiveAgentsTracker()

        all_agents = ["agent1", "agent2", "agent3"]

        # Exclude agent2 for request1
        await tracker.exclude_agent_for_request("request1", "agent2")

        # Verify exclusion
        available = await tracker.get_available_agents(all_agents, "request1")
        assert available == ["agent1", "agent3"]

        # Clean up request
        await tracker.cleanup_request("request1")

        # All agents should be available again for request1
        available = await tracker.get_available_agents(all_agents, "request1")
        assert available == all_agents

    @pytest.mark.asyncio
    async def test_pending_deletions_take_precedence(self):
        """Test that pending deletions override request exclusions."""
        tracker = ActiveAgentsTracker()
        tracker.pending_deletions.add("agent2")  # Mark agent2 for deletion

        all_agents = ["agent1", "agent2", "agent3"]

        # Even without request exclusion, agent2 shouldn't be available
        available = await tracker.get_available_agents(all_agents)
        assert "agent2" not in available

        # Request-specific exclusions shouldn't change this
        available = await tracker.get_available_agents(all_agents, "request1")
        assert "agent2" not in available

    @pytest.mark.asyncio
    async def test_get_request_exclusions(self):
        """Test retrieving exclusions for a specific request."""
        tracker = ActiveAgentsTracker()

        # Exclude agents for different requests
        await tracker.exclude_agent_for_request("request1", "agent1")
        await tracker.exclude_agent_for_request("request1", "agent2")
        await tracker.exclude_agent_for_request("request2", "agent3")

        # Get exclusions for request1
        exclusions = await tracker.get_request_exclusions("request1")
        assert exclusions == {"agent1", "agent2"}

        # Get exclusions for request2
        exclusions = await tracker.get_request_exclusions("request2")
        assert exclusions == {"agent3"}

        # Get exclusions for non-existent request
        exclusions = await tracker.get_request_exclusions("request3")
        assert exclusions == set()


class TestAgentRouterIntegration:
    """Test AgentRouter integration with request-scoped exclusion."""

    @pytest.mark.asyncio
    async def test_agent_router_respects_request_exclusions(self):
        """Test that agent router respects request-scoped exclusions."""
        # Mock overlord with tracker
        overlord = MagicMock()
        tracker = ActiveAgentsTracker()
        overlord.active_agent_tracker = tracker
        overlord.agents = {
            "agent1": MagicMock(),
            "agent2": MagicMock(),
            "agent3": MagicMock(),
        }
        overlord.agent_descriptions = {
            "agent1": "General assistant",
            "agent2": "Code specialist",
            "agent3": "Data analyst",
        }
        overlord.formation_config = {"overlord": {"config": {"caching": {"enabled": False}}}}

        router = AgentRouter(overlord)

        # Exclude agent2 for request1
        await tracker.exclude_agent_for_request("request1", "agent2")

        # Mock routing model to return agent2 (which is excluded)
        with patch.object(router, "_select_best_available_agent") as mock_select:
            # First call will try to select from available agents
            mock_select.return_value = "agent1"

            selected = await router.select_agent_for_message("Write some code", "request1")

            # Should not select agent2 even though it's a code specialist
            assert selected != "agent2"
            assert selected in ["agent1", "agent3"]


class TestResilientWorkflowManager:
    """Test resilient workflow manager fallback agent strategy."""

    @pytest.mark.asyncio
    async def test_fallback_agent_strategy_excludes_failed_agent(self):
        """Test that fallback agent strategy excludes the failed agent."""
        manager = ResilientWorkflowManager()

        # Create mock workflow with overlord
        workflow = MagicMock()
        tracker = ActiveAgentsTracker()
        workflow.overlord.active_agent_tracker = tracker

        # Create error context with agent and request info
        error_context = ErrorContext(
            error=Exception("Agent failed"),
            error_type=ErrorType.AGENT_CRASHED,
            severity=ErrorSeverity.HIGH,
            context_data={
                "agent_id": "failing_agent",
                "request_id": "test_request",
            },
        )

        # Execute fallback strategy
        result = await manager._execute_fallback_agent_strategy(workflow, error_context)

        # Should succeed with retry signal
        assert result.success is True
        assert result.strategy_used == RecoveryStrategy.FALLBACK_AGENT
        assert result.metadata["retry_from_start"] is True
        assert result.metadata["excluded_agent"] == "failing_agent"

        # Verify agent was excluded for the request
        exclusions = await tracker.get_request_exclusions("test_request")
        assert "failing_agent" in exclusions

    @pytest.mark.asyncio
    async def test_fallback_agent_strategy_without_context(self):
        """Test fallback agent strategy fails gracefully without required context."""
        manager = ResilientWorkflowManager()

        # Create error context without agent/request info
        error_context = ErrorContext(
            error=Exception("Generic error"),
            error_type=ErrorType.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            context_data={},
        )

        # Workflow without overlord
        workflow = MagicMock()
        workflow.overlord = None

        # Execute fallback strategy
        result = await manager._execute_fallback_agent_strategy(workflow, error_context)

        # Should fail without required context
        assert result.success is False
        assert result.strategy_used == RecoveryStrategy.FALLBACK_AGENT
        assert isinstance(result.error, WorkflowException)


class TestEndToEndFlow:
    """Test the complete flow of request-scoped exclusion."""

    @pytest.mark.asyncio
    async def test_complete_request_flow_with_cleanup(self):
        """Test that request exclusions are properly cleaned up after request completion."""
        tracker = ActiveAgentsTracker()

        # Simulate a request lifecycle
        request_id = "test_request_123"
        all_agents = ["agent1", "agent2", "agent3"]

        # 1. Request starts - all agents available
        available = await tracker.get_available_agents(all_agents, request_id)
        assert len(available) == 3

        # 2. Agent1 fails, gets excluded
        await tracker.exclude_agent_for_request(request_id, "agent1")
        available = await tracker.get_available_agents(all_agents, request_id)
        assert "agent1" not in available
        assert len(available) == 2

        # 3. Agent2 also fails, gets excluded
        await tracker.exclude_agent_for_request(request_id, "agent2")
        available = await tracker.get_available_agents(all_agents, request_id)
        assert "agent2" not in available
        assert len(available) == 1

        # 4. Request completes, cleanup happens
        await tracker.cleanup_request(request_id)

        # 5. New request with same ID should see all agents
        available = await tracker.get_available_agents(all_agents, request_id)
        assert len(available) == 3

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolated(self):
        """Test that concurrent requests have isolated exclusions."""
        tracker = ActiveAgentsTracker()

        all_agents = ["agent1", "agent2", "agent3"]

        # Simulate concurrent requests
        async def request1():
            await tracker.exclude_agent_for_request("req1", "agent1")
            available = await tracker.get_available_agents(all_agents, "req1")
            assert "agent1" not in available
            assert "agent2" in available

        async def request2():
            await tracker.exclude_agent_for_request("req2", "agent2")
            available = await tracker.get_available_agents(all_agents, "req2")
            assert "agent2" not in available
            assert "agent1" in available

        # Run concurrently
        await asyncio.gather(request1(), request2())

        # Verify isolation
        req1_exclusions = await tracker.get_request_exclusions("req1")
        req2_exclusions = await tracker.get_request_exclusions("req2")

        assert req1_exclusions == {"agent1"}
        assert req2_exclusions == {"agent2"}
