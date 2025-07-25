"""
Unit tests for clarification types module.

Tests the core data classes and enums used throughout the clarification system.
"""

import pytest
from dataclasses import fields

from src.muxi.datatypes import (
    ClarificationRequest,
    ClarificationResult,
    ClarificationResultStatus,
    ClarificationQuestion,
    ClarificationConfig,
    ToolCall,
    ToolCallResult,
    InformationAnalysis,
    ToolInformationAnalysis,
    ReasoningInformationAnalysis,
    ContextAnalysis,
    ParameterMapping,
    ClarificationStatus,
    RequestType,
    QuestionStyle,
    ClarificationError
)


class TestEnums:
    """Test enum definitions"""

    def test_clarification_status_enum(self):
        """Test ClarificationStatus enum values"""
        assert ClarificationStatus.CLARIFYING.value == "clarifying"
        assert ClarificationStatus.READY.value == "ready"
        assert ClarificationStatus.FAILED.value == "failed"
        assert ClarificationStatus.CANCELLED.value == "cancelled"

    def test_request_type_enum(self):
        """Test RequestType enum values"""
        assert RequestType.TOOL_CALL.value == "tool_call"
        assert RequestType.REASONING.value == "reasoning"
        assert RequestType.MIXED.value == "mixed"

    def test_question_style_enum(self):
        """Test QuestionStyle enum values"""
        assert QuestionStyle.CONVERSATIONAL.value == "conversational"
        assert QuestionStyle.FORMAL.value == "formal"
        assert QuestionStyle.BRIEF.value == "brief"


class TestDataClasses:
    """Test core data classes"""

    def test_clarification_question_creation(self):
        """Test ClarificationQuestion creation and defaults"""
        question = ClarificationQuestion(
            question_id="test-123",
            question_text="What city would you like?",
            parameter_name="location",
            parameter_type="string"
        )

        assert question.question_id == "test-123"
        assert question.question_text == "What city would you like?"
        assert question.parameter_name == "location"
        assert question.parameter_type == "string"
        assert question.required is True  # Default value
        assert question.style == QuestionStyle.CONVERSATIONAL  # Default value

    def test_tool_call_creation(self):
        """Test ToolCall creation and auto-generated call_id"""
        tool_call = ToolCall(
            name="book_restaurant",
            parameters={"location": "New York", "party_size": 4}
        )

        assert tool_call.name == "book_restaurant"
        assert tool_call.parameters["location"] == "New York"
        assert tool_call.parameters["party_size"] == 4
        assert tool_call.call_id is not None  # Should be auto-generated
        assert len(tool_call.call_id) > 0

        # Test with explicit call_id
        tool_call_with_id = ToolCall(
            name="test_tool",
            parameters={},
            call_id="explicit-id"
        )
        assert tool_call_with_id.call_id == "explicit-id"

    def test_tool_call_result_creation(self):
        """Test ToolCallResult creation"""
        result = ToolCallResult(
            call_id="test-call-123",
            success=True,
            result={"status": "booked", "confirmation": "ABC123"},
            execution_time=1.5
        )

        assert result.call_id == "test-call-123"
        assert result.success is True
        assert result.result["status"] == "booked"
        assert result.error is None
        assert result.execution_time == 1.5

    def test_clarification_request_creation(self):
        """Test ClarificationRequest creation and defaults"""
        request = ClarificationRequest(
            request_id="",  # Will be auto-generated
            user_id="user-123",
            agent_id="agent-456",
            request_type=RequestType.TOOL_CALL,
            tool_name="book_restaurant",
            intent="restaurant_booking"
        )

        assert request.user_id == "user-123"
        assert request.agent_id == "agent-456"
        assert request.request_type == RequestType.TOOL_CALL
        assert request.tool_name == "book_restaurant"
        assert request.intent == "restaurant_booking"
        assert request.request_id != ""  # Should be auto-generated
        assert request.status == ClarificationStatus.CLARIFYING  # Default
        assert isinstance(request.provided_info, dict)
        assert isinstance(request.missing_info, list)
        assert isinstance(request.clarification_plan, list)
        assert request.current_step == 0
        assert request.created_at > 0
        assert request.updated_at > 0

    def test_clarification_result_creation(self):
        """Test ClarificationResult creation"""
        result = ClarificationResult(
            status=ClarificationResultStatus.COMPLETE,
            complete_params={"location": "New York", "party_size": 4},
            confidence=0.9
        )

        assert result.status == ClarificationResultStatus.COMPLETE
        assert result.complete_params["location"] == "New York"
        assert result.complete_params["party_size"] == 4
        assert result.confidence == 0.9
        assert result.next_question is None
        assert result.error_message is None

    def test_information_analysis_creation(self):
        """Test InformationAnalysis creation"""
        analysis = InformationAnalysis(
            missing_info=["location", "date"],
            available_info={"party_size": 4},
            confidence_scores={"party_size": 0.9},
            suggestions=["Please provide location"],
            can_proceed=False
        )

        assert analysis.missing_info == ["location", "date"]
        assert analysis.available_info["party_size"] == 4
        assert analysis.confidence_scores["party_size"] == 0.9
        assert analysis.suggestions == ["Please provide location"]
        assert analysis.can_proceed is False
        assert analysis.reasoning_context_needed is None

    def test_tool_information_analysis_inheritance(self):
        """Test ToolInformationAnalysis inherits from InformationAnalysis"""
        analysis = ToolInformationAnalysis(
            missing_info=["location"],
            available_info={},
            confidence_scores={"location": 0.0},
            suggestions=["Provide location"],
            can_proceed=False,
            tool_name="book_restaurant",
            tool_schema={"required": ["location"]},
            missing_required_params=["location"],
            missing_optional_params=["cuisine"],
            parameter_confidence={"location": 0.0}
        )

        assert analysis.tool_name == "book_restaurant"
        assert analysis.missing_required_params == ["location"]
        assert analysis.missing_optional_params == ["cuisine"]
        assert analysis.can_proceed is False  # Inherited property

    def test_reasoning_information_analysis_inheritance(self):
        """Test ReasoningInformationAnalysis inherits from InformationAnalysis"""
        analysis = ReasoningInformationAnalysis(
            missing_info=["risk_tolerance"],
            available_info={},
            confidence_scores={"risk_tolerance": 0.0},
            suggestions=["Provide risk tolerance"],
            can_proceed=False,
            intent="investment_advice",
            context_gaps=["risk_tolerance"],
            user_background_needed=["experience"],
            complexity_level="complex"
        )

        assert analysis.intent == "investment_advice"
        assert analysis.context_gaps == ["risk_tolerance"]
        assert analysis.complexity_level == "complex"
        assert analysis.can_proceed is False  # Inherited property

    def test_context_analysis_creation(self):
        """Test ContextAnalysis creation"""
        analysis = ContextAnalysis(
            needs_more_info=True,
            missing_context=["background", "goals"],
            intent="technical_explanation",
            confidence=0.8,
            suggested_questions=["What's your technical background?"]
        )

        assert analysis.needs_more_info is True
        assert analysis.missing_context == ["background", "goals"]
        assert analysis.intent == "technical_explanation"
        assert analysis.confidence == 0.8
        assert analysis.suggested_questions == ["What's your technical background?"]

    def test_parameter_mapping_creation(self):
        """Test ParameterMapping creation"""
        mapping = ParameterMapping(
            parameter_name="location",
            context_keys=["city", "current_location", "address"],
            transformation_function="normalize_location",
            confidence_threshold=0.8
        )

        assert mapping.parameter_name == "location"
        assert mapping.context_keys == ["city", "current_location", "address"]
        assert mapping.transformation_function == "normalize_location"
        assert mapping.confidence_threshold == 0.8

    def test_clarification_config_defaults(self):
        """Test ClarificationConfig default values"""
        config = ClarificationConfig()

        assert config.max_questions == 5
        assert config.style == QuestionStyle.CONVERSATIONAL
        assert config.persist_learned_info is False
        assert config.timeout_seconds == 300
        assert config.auto_fill_from_context is True
        assert config.reasoning_requirements is True

    def test_clarification_config_custom(self):
        """Test ClarificationConfig with custom values"""
        config = ClarificationConfig(
            max_questions=3,
            style=QuestionStyle.BRIEF,
            persist_learned_info=True,
            timeout_seconds=600
        )

        assert config.max_questions == 3
        assert config.style == QuestionStyle.BRIEF
        assert config.persist_learned_info is True
        assert config.timeout_seconds == 600


class TestExceptions:
    """Test custom exception classes"""

    def test_clarification_error(self):
        """Test base ClarificationError"""
        with pytest.raises(ClarificationError) as exc_info:
            raise ClarificationError("Test error message")

        assert str(exc_info.value) == "Test error message"

    def test_exception_inheritance(self):
        """Test that all clarification exceptions inherit from ClarificationError"""
        from src.muxi.datatypes import (
            InformationAnalysisError,
            QuestionGenerationError,
            ParameterExtractionError,
            ContextEnrichmentError
        )

        # All should be subclasses of ClarificationError
        assert issubclass(InformationAnalysisError, ClarificationError)
        assert issubclass(QuestionGenerationError, ClarificationError)
        assert issubclass(ParameterExtractionError, ClarificationError)
        assert issubclass(ContextEnrichmentError, ClarificationError)


class TestDataClassFields:
    """Test that all data classes have the expected fields"""

    def test_clarification_request_fields(self):
        """Test ClarificationRequest has all expected fields"""
        field_names = {f.name for f in fields(ClarificationRequest)}
        expected_fields = {
            'request_id', 'user_id', 'agent_id', 'request_type', 'tool_name',
            'intent', 'provided_info', 'missing_info', 'clarification_plan',
            'current_step', 'context', 'created_at', 'updated_at', 'status'
        }
        assert field_names == expected_fields

    def test_clarification_question_fields(self):
        """Test ClarificationQuestion has all expected fields"""
        field_names = {f.name for f in fields(ClarificationQuestion)}
        expected_fields = {
            'question_id', 'question_text', 'parameter_name', 'parameter_type',
            'parameter_description', 'required', 'validation_rules',
            'context_hints', 'style', 'goal_area', 'priority', 'follow_up_questions'
        }
        assert field_names == expected_fields

    def test_tool_call_fields(self):
        """Test ToolCall has all expected fields"""
        field_names = {f.name for f in fields(ToolCall)}
        expected_fields = {'name', 'parameters', 'call_id'}
        assert field_names == expected_fields
