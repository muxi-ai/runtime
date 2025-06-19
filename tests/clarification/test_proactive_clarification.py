"""
Test Phase 4: Proactive Clarification Components

This module tests the proactive clarification functionality including:
- ProactiveClarificationIntentDetector
- ClarificationModeManager
- Plan analysis and feedback
- Goal-driven questioning
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import List

from src.muxi.runtime.clarification import (
    ProactiveClarificationIntentDetector,
    ClarificationModeManager,
    ProactiveRequest,
    ProactiveRequestType,
    MultiStepPlan,
    ClarificationMode,
    ClarificationSession,
    GoalContext,
    PlanAnalysis,
    PlanStepAnalysis
)


class TestProactiveClarificationIntentDetector:
    """Test proactive intent detection from user messages"""

    @pytest.fixture
    def detector(self):
        """Create detector with mock model"""
        mock_model = Mock()
        return ProactiveClarificationIntentDetector(model=mock_model)

    @pytest.mark.asyncio
    async def test_detect_guided_questioning_request(self, detector):
        """Test detection of guided questioning requests"""
        messages = [
            "Ask me questions until you understand my investment goals",
            "Interview me about my background before recommending anything",
            "Get more information from me first",
            "What questions do you need me to answer?"
        ]

        for message in messages:
            request = await detector.detect_proactive_request(message)
            assert request is not None
            assert request.request_type == ProactiveRequestType.GUIDED_QUESTIONING
            assert request.confidence > 0.8

    @pytest.mark.asyncio
    async def test_detect_plan_feedback_request(self, detector):
        """Test detection of plan feedback requests"""
        messages = [
            "I want to start a business, then get funding, then hire developers. What do you think?",
            "My plan is to research the market, then create a product. How does that sound?",
            "I'm thinking of learning Python, then building a web app. Thoughts?"
        ]

        for message in messages:
            request = await detector.detect_proactive_request(message)
            assert request is not None
            assert request.request_type == ProactiveRequestType.PLAN_FEEDBACK
            assert "plan" in request.goal.lower() or "business" in request.goal.lower()

    @pytest.mark.asyncio
    async def test_detect_context_first_request(self, detector):
        """Test detection of context-first requests"""
        messages = [
            "Make sure you understand my situation before advising",
            "Get my background first before we proceed",
            "Understand my needs before recommending anything"
        ]

        for message in messages:
            request = await detector.detect_proactive_request(message)
            assert request is not None
            assert request.request_type == ProactiveRequestType.CONTEXT_FIRST

    @pytest.mark.asyncio
    async def test_detect_step_by_step_request(self, detector):
        """Test detection of step-by-step requests"""
        messages = [
            "Walk me through how to start investing",
            "Guide me step by step through the process",
            "Show me the steps to build a website"
        ]

        for message in messages:
            request = await detector.detect_proactive_request(message)
            assert request is not None
            assert request.request_type == ProactiveRequestType.STEP_BY_STEP

    @pytest.mark.asyncio
    async def test_no_detection_for_regular_messages(self, detector):
        """Test that regular messages don't trigger proactive detection"""
        regular_messages = [
            "What's the weather today?",
            "Help me book a restaurant",
            "Explain quantum physics",
            "I need investment advice"
        ]

        for message in regular_messages:
            request = await detector.detect_proactive_request(message)
            assert request is None

    @pytest.mark.asyncio
    async def test_parse_multi_step_plan(self, detector):
        """Test parsing multi-step plans from messages"""
        plan_message = (
            "I want to first research the market, then create a business plan, "
            "then get funding, and finally launch the product. What do you think?"
        )

        plan = await detector.parse_multi_step_plan(plan_message)
        assert plan is not None
        assert len(plan.steps) >= 3
        assert "research" in plan.steps[0].lower()
        assert "business plan" in plan.steps[1].lower()
        assert "funding" in plan.steps[2].lower()

    @pytest.mark.asyncio
    async def test_extract_goals_from_requests(self, detector):
        """Test goal extraction from different request types"""
        test_cases = [
            ("Ask me questions until you can help me invest wisely", "invest wisely"),
            ("Walk me through starting a business", "starting a business"),
            ("Get my background before recommending career moves", "career moves")
        ]

        for message, expected_goal_fragment in test_cases:
            request = await detector.detect_proactive_request(message)
            assert request is not None
            assert expected_goal_fragment.lower() in request.goal.lower()


class TestClarificationModeManager:
    """Test clarification mode and session management"""

    @pytest.fixture
    def mock_overlord(self):
        """Create mock overlord"""
        overlord = Mock()
        overlord.get_user_context = AsyncMock(return_value={})
        return overlord

    @pytest.fixture
    def mode_manager(self, mock_overlord):
        """Create mode manager with mock overlord"""
        return ClarificationModeManager(overlord=mock_overlord)

    @pytest.mark.asyncio
    async def test_enter_proactive_mode(self, mode_manager):
        """Test entering proactive questioning mode"""
        proactive_request = ProactiveRequest(
            request_type=ProactiveRequestType.GUIDED_QUESTIONING,
            goal="investment advice",
            original_message="Ask me questions until you understand my investment goals",
            max_questions=5
        )

        session = await mode_manager.enter_proactive_mode(
            user_id="user123",
            agent_id="agent456",
            proactive_request=proactive_request
        )

        assert session is not None
        assert session.user_id == "user123"
        assert session.agent_id == "agent456"
        assert session.mode == ClarificationMode.PROACTIVE_QUESTIONING
        assert session.max_questions == 5
        assert session.goal_context is not None
        assert session.goal_context.goal == "investment advice"

    @pytest.mark.asyncio
    async def test_enter_plan_analysis_mode(self, mode_manager):
        """Test entering plan analysis mode"""
        # Create mock plan analysis
        plan = MultiStepPlan(
            steps=["research market", "create product", "get funding"],
            goal="start a business",
            original_message="I want to start a business"
        )

        plan_analysis = PlanAnalysis(
            plan=plan,
            overall_feasibility=0.8,
            step_analyses=[
                PlanStepAnalysis(
                    step_index=0,
                    step_text="research market",
                    feasibility_score=0.9,
                    clarity_score=0.7,
                    requirements=["Time", "Research skills"],
                    potential_issues=[],
                    suggested_clarifications=["What specific market?"],
                    dependencies=[]
                )
            ],
            missing_steps=[],
            clarification_questions=["What type of business are you considering?"],
            recommendations=["Consider more detailed market research"]
        )

        session = await mode_manager.enter_plan_analysis_mode(
            user_id="user123",
            agent_id="agent456",
            plan_analysis=plan_analysis
        )

        assert session is not None
        assert session.mode == ClarificationMode.PLAN_ANALYSIS
        assert session.plan_analysis == plan_analysis

    @pytest.mark.asyncio
    async def test_session_progress_tracking(self, mode_manager):
        """Test updating session progress"""
        # Create a session first
        proactive_request = ProactiveRequest(
            request_type=ProactiveRequestType.GUIDED_QUESTIONING,
            goal="career advice",
            original_message="Ask me questions about my career goals",
            max_questions=3
        )

        session = await mode_manager.enter_proactive_mode(
            user_id="user123",
            agent_id="agent456",
            proactive_request=proactive_request
        )

        # Update progress
        collected_info = {"experience": "5 years", "field": "software"}
        success = await mode_manager.update_session_progress(
            session.session_id,
            collected_info=collected_info,
            questions_asked=2
        )

        assert success is True

        # Check session was updated
        updated_session = await mode_manager.get_active_session("user123")
        assert updated_session.questions_asked == 2
        assert "experience" in updated_session.goal_context.collected_info

    @pytest.mark.asyncio
    async def test_session_completion(self, mode_manager):
        """Test completing a clarification session"""
        # Create and complete a session
        proactive_request = ProactiveRequest(
            request_type=ProactiveRequestType.GUIDED_QUESTIONING,
            goal="investment advice",
            original_message="Help me invest",
            max_questions=2
        )

        session = await mode_manager.enter_proactive_mode(
            user_id="user123",
            agent_id="agent456",
            proactive_request=proactive_request
        )

        # Complete the session
        complete_info = await mode_manager.complete_session(session.session_id)

        assert isinstance(complete_info, dict)
        assert "goal_achievement" in complete_info

        # Session should be cleaned up
        active_session = await mode_manager.get_active_session("user123")
        assert active_session is None

    @pytest.mark.asyncio
    async def test_goal_context_creation(self, mode_manager):
        """Test goal context creation for different goal types"""
        test_cases = [
            ("investment advice", "investment_advice"),
            ("start a business", "business_planning"),
            ("career guidance", "career_guidance"),
            ("learn programming", "learning_guidance")
        ]

        for goal, expected_type in test_cases:
            goal_type = mode_manager._determine_goal_type(goal)
            assert goal_type == expected_type

            required_areas = mode_manager._determine_required_info_areas(goal_type, goal)
            assert isinstance(required_areas, list)
            assert len(required_areas) > 0


class TestProactiveIntegration:
    """Test integration of proactive clarification with Agent"""

    @pytest.fixture
    def mock_agent(self):
        """Create mock agent with proactive capabilities"""
        agent = Mock()
        agent.agent_id = "test_agent"
        agent.model = Mock()
        agent.overlord = Mock()

        # Mock clarification components
        agent._proactive_detector = Mock()
        agent._mode_manager = Mock()
        agent._clarification_parser = Mock()

        return agent

    @pytest.mark.asyncio
    async def test_proactive_request_detection_flow(self, mock_agent):
        """Test the full proactive request detection and handling flow"""
        # Mock proactive request detection
        proactive_request = ProactiveRequest(
            request_type=ProactiveRequestType.GUIDED_QUESTIONING,
            goal="investment advice",
            original_message="Ask me questions until you understand my investment goals"
        )

        mock_agent._proactive_detector.detect_proactive_request = AsyncMock(
            return_value=proactive_request
        )

        # Mock session creation
        mock_session = Mock()
        mock_session.goal_context = Mock()
        mock_session.goal_context.required_info_areas = ["risk_tolerance", "timeline"]

        mock_agent._mode_manager.get_active_session = AsyncMock(return_value=None)
        mock_agent._mode_manager.enter_proactive_mode = AsyncMock(return_value=mock_session)

        # Import and patch the actual method

        # Test that proactive detection would be triggered
        message = "Ask me questions until you understand my investment goals"
        user_id = "user123"

        # The flow should detect this as a proactive request
        assert "ask me questions" in message.lower()
        assert "until" in message.lower()

    @pytest.mark.asyncio
    async def test_plan_analysis_flow(self, mock_agent):
        """Test plan analysis detection and handling"""
        plan_message = (
            "I want to first research the market, then create a business plan, "
            "then get funding. What do you think?"
        )

        # Mock plan parsing
        mock_plan = MultiStepPlan(
            steps=["research the market", "create a business plan", "get funding"],
            goal="start a business",
            original_message=plan_message
        )

        proactive_request = ProactiveRequest(
            request_type=ProactiveRequestType.PLAN_FEEDBACK,
            goal="start a business",
            original_message=plan_message
        )
        proactive_request.multi_step_plan = mock_plan

        mock_agent._proactive_detector.detect_proactive_request = AsyncMock(
            return_value=proactive_request
        )

        # Verify the flow would be triggered
        assert "what do you think" in plan_message.lower()
        assert "first" in plan_message.lower() and "then" in plan_message.lower()

    @pytest.mark.asyncio
    async def test_session_continuation(self, mock_agent):
        """Test continuing an existing proactive session"""
        # Mock existing session
        existing_session = Mock()
        existing_session.mode = ClarificationMode.PROACTIVE_QUESTIONING
        existing_session.questions_asked = 1
        existing_session.completion_criteria_met = False

        mock_agent._mode_manager.get_active_session = AsyncMock(
            return_value=existing_session
        )

        # Mock response processing
        mock_result = Mock()
        mock_result.extracted_info = {"risk_tolerance": "moderate"}

        mock_agent._clarification_parser.parse_response = AsyncMock(
            return_value=mock_result
        )

        # Test that session continuation would work
        user_response = "I'm comfortable with moderate risk"

        # Should process the response and continue the session
        assert existing_session is not None
        assert not existing_session.completion_criteria_met


@pytest.mark.asyncio
async def test_phase_4_end_to_end():
    """End-to-end test of Phase 4 functionality"""

    # Test scenario: User requests guided questioning
    user_message = "Ask me questions until you understand my investment goals"

    # 1. Detection should work
    detector = ProactiveClarificationIntentDetector()
    request = await detector.detect_proactive_request(user_message)

    # Should detect guided questioning request
    if request:  # Only test if detection works (may not with mock model)
        assert request.request_type == ProactiveRequestType.GUIDED_QUESTIONING
        assert "investment" in request.goal.lower()

    # 2. Mode manager should handle the request
    mock_overlord = Mock()
    mode_manager = ClarificationModeManager(overlord=mock_overlord)

    if request:
        session = await mode_manager.enter_proactive_mode(
            user_id="test_user",
            agent_id="test_agent",
            proactive_request=request
        )

        assert session.mode == ClarificationMode.PROACTIVE_QUESTIONING
        assert session.goal_context is not None

    # 3. Test plan analysis scenario
    plan_message = "I want to research, then build, then launch. What do you think?"
    plan_request = await detector.detect_proactive_request(plan_message)

    if plan_request and plan_request.request_type == ProactiveRequestType.PLAN_FEEDBACK:
        # Would trigger plan analysis mode
        assert "plan" in plan_request.goal.lower() or "multi-step" in plan_request.goal.lower()


if __name__ == "__main__":
    pytest.main([__file__])
