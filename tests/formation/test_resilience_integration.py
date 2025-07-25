"""
Integration test demonstrating the FALLBACK_AGENT strategy in action.
"""

import pytest
from unittest.mock import MagicMock

from muxi.formation.overlord.active_agents_tracker import ActiveAgentsTracker
from muxi.formation.resilience.resilient_workflow_manager import ResilientWorkflowManager
from muxi.datatypes.resilience import (
    ResilienceConfig,
    ErrorContext,
    ErrorType,
    ErrorSeverity,
)
from muxi.datatypes.exceptions import NoAvailableAgentsError


class TestResilienceFallbackIntegration:
    """Test the complete integration of fallback agent strategy."""

    @pytest.mark.asyncio
    async def test_agent_failure_triggers_fallback_and_retry(self):
        """Test that agent failure triggers fallback strategy and retries with different agent."""
        # Create mock overlord with multiple agents
        overlord = MagicMock()
        overlord.formation_id = "test_formation"

        # Set up active agent tracker
        tracker = ActiveAgentsTracker()
        overlord.active_agent_tracker = tracker

        # Set up agents
        agent1 = MagicMock()
        agent1.agent_id = "agent1"
        agent2 = MagicMock()
        agent2.agent_id = "agent2"
        agent3 = MagicMock()
        agent3.agent_id = "agent3"

        overlord.agents = {
            "agent1": agent1,
            "agent2": agent2,
            "agent3": agent3,
        }
        overlord.get_agent.side_effect = lambda aid: overlord.agents[aid]

        # Set up agent router to select agents in order
        selection_count = 0

        async def mock_select_agent(message, request_id=None):
            nonlocal selection_count
            available = await tracker.get_available_agents(list(overlord.agents.keys()), request_id)
            if not available:
                raise NoAvailableAgentsError("No agents available")

            # First call selects agent1, second call selects agent2
            selection_count += 1
            if selection_count == 1:
                return "agent1" if "agent1" in available else available[0]
            else:
                return "agent2" if "agent2" in available else available[0]

        overlord.select_agent_for_message = mock_select_agent

        # Create resilience manager
        resilience_manager = ResilientWorkflowManager()
        resilience_config = ResilienceConfig(
            enable_fallbacks=True,
            enable_retries=True,
        )

        # Create a workflow that simulates agent processing
        class TestWorkflow:
            def __init__(self, overlord):
                self.overlord = overlord
                self.execution_count = 0

            async def execute(self, request_id):
                self.execution_count += 1

                # Select agent
                agent_id = await self.overlord.select_agent_for_message(
                    "Test message", request_id=request_id
                )

                # Simulate agent1 failing on first attempt
                if agent_id == "agent1" and self.execution_count == 1:
                    raise Exception("Agent1 crashed!")

                # Otherwise succeed
                return f"Success with {agent_id}"

        # Create workflow instance
        workflow = TestWorkflow(overlord)
        request_id = "test_request_123"

        # Create custom execute function that handles retry signal
        async def execute_with_retry():
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Reset execution count for retry
                    if attempt > 0:
                        workflow.execution_count = 0

                    result = await workflow.execute(request_id)
                    return result

                except Exception as e:
                    # Create error context
                    error_context = ErrorContext(
                        error=e,
                        error_type=ErrorType.AGENT_CRASHED,
                        severity=ErrorSeverity.HIGH,
                        context_data={
                            "agent_id": "agent1",  # The agent that failed
                            "request_id": request_id,
                        },
                    )

                    # Execute fallback strategy
                    recovery_result = await resilience_manager._execute_fallback_agent_strategy(
                        workflow, error_context
                    )

                    if recovery_result.success and recovery_result.metadata.get("retry_from_start"):
                        # Retry from the beginning
                        continue
                    else:
                        raise

            raise Exception("Max retry attempts exceeded")

        # Execute the workflow with resilience
        result = await execute_with_retry()

        # Verify the result
        assert result == "Success with agent2"
        assert workflow.execution_count == 1  # Reset after retry

        # Verify agent1 was excluded for the request
        exclusions = await tracker.get_request_exclusions(request_id)
        assert "agent1" in exclusions

        # Clean up request
        await tracker.cleanup_request(request_id)

        # Verify exclusions were cleaned up
        exclusions = await tracker.get_request_exclusions(request_id)
        assert len(exclusions) == 0

    @pytest.mark.asyncio
    async def test_multiple_agent_failures_cascade(self):
        """Test that multiple agents can fail and be excluded in sequence."""
        # Create mock overlord
        overlord = MagicMock()
        tracker = ActiveAgentsTracker()
        overlord.active_agent_tracker = tracker

        # Set up 4 agents
        overlord.agents = {f"agent{i}": MagicMock() for i in range(1, 5)}

        # Track which agents have been tried
        tried_agents = []

        async def mock_select_agent(message, request_id=None):
            available = await tracker.get_available_agents(list(overlord.agents.keys()), request_id)
            if not available:
                raise NoAvailableAgentsError("No agents available")

            # Select first available agent not yet tried
            for agent_id in ["agent1", "agent2", "agent3", "agent4"]:
                if agent_id in available and agent_id not in tried_agents:
                    tried_agents.append(agent_id)
                    return agent_id

            raise NoAvailableAgentsError("All agents have been tried")

        overlord.select_agent_for_message = mock_select_agent

        # Create resilience manager
        resilience_manager = ResilientWorkflowManager()

        # Simulate first 2 agents failing
        failing_agents = ["agent1", "agent2"]
        request_id = "cascade_test"

        # Execute with cascading failures
        for i, agent_id in enumerate(failing_agents):
            error_context = ErrorContext(
                error=Exception(f"{agent_id} failed"),
                error_type=ErrorType.AGENT_CRASHED,
                severity=ErrorSeverity.HIGH,
                context_data={
                    "agent_id": agent_id,
                    "request_id": request_id,
                },
            )

            # Execute fallback strategy
            result = await resilience_manager._execute_fallback_agent_strategy(
                MagicMock(overlord=overlord), error_context
            )

            assert result.success is True
            assert result.metadata["excluded_agent"] == agent_id

        # Verify both agents are excluded
        exclusions = await tracker.get_request_exclusions(request_id)
        assert exclusions == {"agent1", "agent2"}

        # Next selection should skip excluded agents
        selected = await overlord.select_agent_for_message("test", request_id)
        assert selected == "agent3"

    @pytest.mark.asyncio
    async def test_all_agents_excluded_error(self):
        """Test that appropriate error is raised when all agents are excluded."""
        overlord = MagicMock()
        tracker = ActiveAgentsTracker()
        overlord.active_agent_tracker = tracker

        # Only 2 agents available
        overlord.agents = {"agent1": MagicMock(), "agent2": MagicMock()}

        # Exclude both agents for a request
        request_id = "no_agents_test"
        await tracker.exclude_agent_for_request(request_id, "agent1")
        await tracker.exclude_agent_for_request(request_id, "agent2")

        # Try to get available agents
        available = await tracker.get_available_agents(list(overlord.agents.keys()), request_id)

        # Should return empty list
        assert available == []

        # Router should raise NoAvailableAgentsError
        async def mock_select_agent(message, request_id=None):
            available = await tracker.get_available_agents(list(overlord.agents.keys()), request_id)
            if not available:
                raise NoAvailableAgentsError("No agents available for new requests")

        overlord.select_agent_for_message = mock_select_agent

        with pytest.raises(NoAvailableAgentsError):
            await overlord.select_agent_for_message("test", request_id)
