"""
Integration tests for Phase 4B: Planning Workflow Detection & Continuity

Tests the complete workflow from detection through synthesis to continuation.
"""

from unittest.mock import AsyncMock, MagicMock

from src.muxi.runtime.clarification.planning_workflow_detector import (
    PlanningWorkflowDetector
)
from src.muxi.runtime.clarification.planning_continuation_manager import (
    PlanningContinuationManager
)
from src.muxi.runtime.clarification.types import (
    PlanningWorkflowType,
    WorkflowState,
    ToolExecutionResult,
    WorkflowSynthesis
)


class TestPhase4BIntegration:
    """Test the complete Phase 4B planning workflow system"""

    def setup_method(self):
        """Set up test components"""
        self.detector = PlanningWorkflowDetector()
        self.continuation_manager = PlanningContinuationManager()
        self.mock_model = AsyncMock()

    def test_travel_planning_detection(self):
        """Test detection of travel planning workflow"""
        message = ("I want to book a trip to New York in August. "
                   "Can you check the weather and find the best fares?")

        workflow_request = self.detector.detect(message)

        assert workflow_request is not None
        assert workflow_request.workflow_type == PlanningWorkflowType.TRAVEL_PLANNING
        assert "book a trip to New York in August" in workflow_request.planning_goal
        assert len(workflow_request.information_requests) >= 1
        assert workflow_request.confidence > 0.6
        assert "weather" in workflow_request.detected_tools
        assert "pricing" in workflow_request.detected_tools

    def test_investment_planning_detection(self):
        """Test detection of investment planning workflow"""
        message = ("Help me invest $10k in the stock market. "
                   "Research current trends and analyze the best options.")

        workflow_request = self.detector.detect(message)

        assert workflow_request is not None
        assert workflow_request.workflow_type == PlanningWorkflowType.INVESTMENT_PLANNING
        assert "invest $10k" in workflow_request.planning_goal
        assert len(workflow_request.information_requests) >= 1
        assert workflow_request.confidence > 0.6

    def test_session_creation_and_management(self):
        """Test planning session lifecycle"""
        # Create mock workflow request
        from src.muxi.runtime.clarification.types import PlanningWorkflowRequest
        workflow_request = PlanningWorkflowRequest(
            workflow_type=PlanningWorkflowType.TRAVEL_PLANNING,
            planning_goal="book a trip to NYC",
            information_requests=["weather", "fares"],
            original_message="I want to book a trip to NYC. Check weather and fares.",
            confidence=0.9
        )

        # Create session
        session = self.continuation_manager.create_session(
            user_id="test_user",
            agent_id="test_agent",
            workflow_request=workflow_request
        )

        assert session is not None
        assert session.current_state == WorkflowState.INFORMATION_GATHERING
        assert session.workflow_request.workflow_type == PlanningWorkflowType.TRAVEL_PLANNING
        assert self.continuation_manager.should_continue_planning(session.session_id)

    def test_tool_result_integration(self):
        """Test adding tool results and state transitions"""
        from src.muxi.runtime.clarification.types import PlanningWorkflowRequest

        # Create session
        workflow_request = PlanningWorkflowRequest(
            workflow_type=PlanningWorkflowType.TRAVEL_PLANNING,
            planning_goal="book a trip to NYC",
            information_requests=["weather", "fares"],
            original_message="I want to book a trip to NYC.",
            confidence=0.9
        )

        session = self.continuation_manager.create_session(
            user_id="test_user",
            agent_id="test_agent",
            workflow_request=workflow_request
        )

        # Add tool result
        tool_result = ToolExecutionResult(
            tool_name="get_weather",
            parameters={"location": "New York", "month": "August"},
            result={"temperature": "75-85°F", "conditions": "partly cloudy"},
            execution_time=1.2,
            success=True,
            planning_relevance="Weather data for NYC travel planning"
        )

        success = self.continuation_manager.add_tool_result(session.session_id, tool_result)

        assert success
        updated_session = self.continuation_manager.get_session(session.session_id)
        assert updated_session.current_state == WorkflowState.DATA_SYNTHESIS
        assert len(updated_session.executed_tools) == 1
        assert updated_session.executed_tools[0].tool_name == "get_weather"

    def test_synthesis_update_and_response_generation(self):
        """Test synthesis update and response generation"""
        from src.muxi.runtime.clarification.types import PlanningWorkflowRequest

        # Create session with tool results
        workflow_request = PlanningWorkflowRequest(
            workflow_type=PlanningWorkflowType.TRAVEL_PLANNING,
            planning_goal="book a trip to NYC",
            information_requests=["weather", "fares"],
            original_message="I want to book a trip to NYC.",
            confidence=0.9
        )

        session = self.continuation_manager.create_session(
            user_id="test_user",
            agent_id="test_agent",
            workflow_request=workflow_request
        )

        # Add mock tool results
        tool_results = [
            ToolExecutionResult(
                tool_name="get_weather",
                parameters={"location": "NYC"},
                result={"temp": "75-85°F"},
                execution_time=1.0,
                success=True
            ),
            ToolExecutionResult(
                tool_name="get_fares",
                parameters={"destination": "NYC"},
                result={"price": "$350-500"},
                execution_time=1.5,
                success=True
            )
        ]

        for result in tool_results:
            self.continuation_manager.add_tool_result(session.session_id, result)

        # Create mock synthesis
        synthesis = WorkflowSynthesis(
            planning_goal="book a trip to NYC",
            tool_results=tool_results,
            key_insights=["Weather is favorable", "Fares range $350-500"],
            options=[
                {"title": "Option 1", "description": "Budget option"},
                {"title": "Option 2", "description": "Premium option"}
            ],
            trade_offs=["Cost vs convenience"],
            recommendations=["Book mid-August for best weather"],
            follow_up_questions=["What's your budget preference?"],
            confidence_score=0.85
        )

        # Update synthesis
        success = self.continuation_manager.update_synthesis(session.session_id, synthesis)
        assert success

        # Generate response
        response = self.continuation_manager.get_planning_response(session.session_id)
        assert response is not None
        assert "Key Insights:" in response
        assert "Your Options:" in response
        assert "Trade-offs" in response
        assert "help you decide" in response

    def test_session_state_transitions(self):
        """Test complete session state transitions"""
        from src.muxi.runtime.clarification.types import PlanningWorkflowRequest

        workflow_request = PlanningWorkflowRequest(
            workflow_type=PlanningWorkflowType.GENERAL_PLANNING,
            planning_goal="make a decision",
            information_requests=["research"],
            original_message="Help me decide.",
            confidence=0.8
        )

        session = self.continuation_manager.create_session(
            user_id="test_user",
            agent_id="test_agent",
            workflow_request=workflow_request
        )

        # Start in information gathering
        assert session.current_state == WorkflowState.INFORMATION_GATHERING

        # Add tool result -> moves to synthesis
        tool_result = ToolExecutionResult(
            tool_name="research_tool",
            parameters={},
            result={"data": "research results"},
            execution_time=1.0,
            success=True
        )
        self.continuation_manager.add_tool_result(session.session_id, tool_result)
        session = self.continuation_manager.get_session(session.session_id)
        assert session.current_state == WorkflowState.DATA_SYNTHESIS

        # Update synthesis -> moves to option presentation
        synthesis = WorkflowSynthesis(
            planning_goal="make a decision",
            tool_results=[tool_result],
            key_insights=["Key insight"],
            options=[],
            trade_offs=[],
            recommendations=[],
            follow_up_questions=[],
            confidence_score=0.7
        )
        self.continuation_manager.update_synthesis(session.session_id, synthesis)
        session = self.continuation_manager.get_session(session.session_id)
        assert session.current_state == WorkflowState.OPTION_PRESENTATION

        # Advance to refinement
        self.continuation_manager.advance_to_refinement(session.session_id)
        session = self.continuation_manager.get_session(session.session_id)
        assert session.current_state == WorkflowState.DECISION_REFINEMENT

        # Complete session
        self.continuation_manager.complete_session(session.session_id)
        session = self.continuation_manager.get_session(session.session_id)
        assert session.current_state == WorkflowState.PLANNING_COMPLETE
        assert not self.continuation_manager.should_continue_planning(session.session_id)

    def test_session_summary(self):
        """Test session summary generation"""
        from src.muxi.runtime.clarification.types import PlanningWorkflowRequest

        workflow_request = PlanningWorkflowRequest(
            workflow_type=PlanningWorkflowType.PRODUCT_SELECTION,
            planning_goal="buy a laptop",
            information_requests=["specs", "prices"],
            original_message="Help me buy a laptop.",
            confidence=0.9
        )

        session = self.continuation_manager.create_session(
            user_id="test_user",
            agent_id="test_agent",
            workflow_request=workflow_request
        )

        summary = self.continuation_manager.get_session_summary(session.session_id)

        assert summary is not None
        assert summary["workflow_type"] == "product_selection"
        assert summary["planning_goal"] == "buy a laptop"
        assert summary["current_state"] == "information_gathering"
        assert summary["tools_executed"] == 0
        assert summary["successful_tools"] == 0
        assert not summary["has_synthesis"]
        assert "created_at" in summary
        assert "updated_at" in summary

    def test_session_cleanup(self):
        """Test session cleanup functionality"""
        from src.muxi.runtime.clarification.types import PlanningWorkflowRequest

        workflow_request = PlanningWorkflowRequest(
            workflow_type=PlanningWorkflowType.GENERAL_PLANNING,
            planning_goal="test",
            information_requests=[],
            original_message="test",
            confidence=0.5
        )

        session = self.continuation_manager.create_session(
            user_id="test_user",
            agent_id="test_agent",
            workflow_request=workflow_request
        )

        session_id = session.session_id

        # Verify session exists
        assert self.continuation_manager.get_session(session_id) is not None

        # Clean up session
        self.continuation_manager.cleanup_session(session_id)

        # Verify session removed
        assert self.continuation_manager.get_session(session_id) is None
        assert not self.continuation_manager.should_continue_planning(session_id)

    def test_edge_cases(self):
        """Test edge cases and error handling"""
        # Test detection with non-planning messages
        non_planning_messages = [
            "Hello, how are you?",
            "What's the weather today?",
            "Tell me a joke.",
            "What time is it?"
        ]

        for message in non_planning_messages:
            workflow_request = self.detector.detect(message)
            assert workflow_request is None, f"Incorrectly detected planning for: {message}"

        # Test session operations with invalid IDs
        assert self.continuation_manager.get_session("invalid_id") is None
        assert not self.continuation_manager.add_tool_result("invalid_id", MagicMock())
        assert not self.continuation_manager.update_synthesis("invalid_id", MagicMock())
        assert self.continuation_manager.get_planning_response("invalid_id") is None

    def test_multiple_concurrent_sessions(self):
        """Test handling multiple concurrent planning sessions"""
        from src.muxi.runtime.clarification.types import PlanningWorkflowRequest

        # Create multiple sessions
        sessions = []
        for i in range(3):
            workflow_request = PlanningWorkflowRequest(
                workflow_type=PlanningWorkflowType.GENERAL_PLANNING,
                planning_goal=f"goal_{i}",
                information_requests=[],
                original_message=f"message_{i}",
                confidence=0.8
            )

            session = self.continuation_manager.create_session(
                user_id=f"user_{i}",
                agent_id=f"agent_{i}",
                workflow_request=workflow_request
            )
            sessions.append(session)

        # Verify all sessions exist independently
        for session in sessions:
            retrieved = self.continuation_manager.get_session(session.session_id)
            assert retrieved is not None
            assert retrieved.user_id == session.user_id
            assert retrieved.agent_id == session.agent_id

        # Clean up all sessions
        for session in sessions:
            self.continuation_manager.cleanup_session(session.session_id)
            assert self.continuation_manager.get_session(session.session_id) is None


if __name__ == "__main__":
    # Run basic integration test
    test_instance = TestPhase4BIntegration()
    test_instance.setup_method()

    print("🧪 Testing Phase 4B Integration...")

    # Test detection
    print("✅ Testing planning workflow detection...")
    test_instance.test_travel_planning_detection()
    test_instance.test_investment_planning_detection()

    # Test session management
    print("✅ Testing session management...")
    test_instance.test_session_creation_and_management()
    test_instance.test_tool_result_integration()

    # Test synthesis and responses
    print("✅ Testing synthesis and response generation...")
    test_instance.test_synthesis_update_and_response_generation()

    # Test state transitions
    print("✅ Testing state transitions...")
    test_instance.test_session_state_transitions()

    # Test edge cases
    print("✅ Testing edge cases...")
    test_instance.test_edge_cases()

    print("🎉 Phase 4B Integration Tests Completed Successfully!")
    print("\n📋 Phase 4B Implementation Summary:")
    print("✅ PlanningWorkflowDetector - Detects implicit planning requests")
    print("✅ PlanningContinuationManager - Manages workflow sessions and state")
    print("✅ Type System - Extended with planning workflow types")
    print("✅ Integration - All components work together seamlessly")
    print("\n🚀 Phase 4B: Planning Workflow Detection & Continuity is COMPLETE!")
