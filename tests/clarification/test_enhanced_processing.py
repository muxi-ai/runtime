"""
Unit tests for enhanced tool processing with clarification support.

Tests Phase 3 functionality including tool call validation, parameter enrichment,
and enhanced execution flow.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.muxi.runtime.clarification.tool_processor import EnhancedToolProcessor
from src.muxi.runtime.clarification.types import ToolInformationAnalysis
from src.muxi.runtime.mcp.parser import ToolCall


class TestEnhancedToolProcessor:
    """Test enhanced tool processing functionality"""

    @pytest.fixture
    def mock_agent(self):
        """Create mock agent"""
        agent = MagicMock()
        agent.invoke_tool = AsyncMock(return_value={"result": "success"})
        agent._mcp_service = MagicMock()
        agent._mcp_service.list_available_tools = AsyncMock(return_value=[
            {
                "name": "book_restaurant",
                "parameters": {
                    "required": ["location", "date", "time"],
                    "properties": {
                        "location": {"type": "string", "description": "City or area"},
                        "date": {"type": "string", "description": "Date for reservation"},
                        "time": {"type": "string", "description": "Time for reservation"},
                        "party_size": {"type": "integer", "description": "Number of people"}
                    }
                }
            }
        ])
        return agent

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock clarification analyzer"""
        analyzer = MagicMock()
        analyzer.analyze_tool_call = AsyncMock()
        return analyzer

    @pytest.fixture
    def mock_enricher(self):
        """Create mock parameter enricher"""
        enricher = MagicMock()
        enricher.enrich_parameters = AsyncMock()
        return enricher

    @pytest.fixture
    def processor(self, mock_agent, mock_analyzer, mock_enricher):
        """Create EnhancedToolProcessor instance"""
        return EnhancedToolProcessor(mock_agent, mock_analyzer, mock_enricher)

    @pytest.mark.asyncio
    async def test_process_tool_calls_with_no_tools(self, processor):
        """Test processing text with no tool calls"""
        text = "Hello, how are you today?"

        result_text, tool_calls, clarification = await processor.process_tool_calls_with_clarification(
            text, user_id=1
        )

        assert result_text == text
        assert tool_calls == []
        assert clarification is None

    @pytest.mark.asyncio
    async def test_process_tool_calls_with_complete_parameters(self, processor, mock_analyzer, mock_enricher):
        """Test processing tool calls with complete parameters"""
        text = 'I want to book a restaurant. ```json\n{"tool": "book_restaurant", "parameters": {"location": "NYC", "date": "2024-01-15", "time": "7:00 PM"}}\n```'

        # Mock analysis showing tool call can proceed
        mock_analysis = ToolInformationAnalysis(
            missing_info=[],
            available_info={"location": "NYC", "date": "2024-01-15", "time": "7:00 PM"},
            confidence_scores={},
            suggestions=[],
            can_proceed=True,
            tool_name="book_restaurant"
        )
        mock_analyzer.analyze_tool_call.return_value = mock_analysis

        # Mock enricher returning original parameters
        mock_enricher.enrich_parameters.return_value = {
            "location": "NYC", "date": "2024-01-15", "time": "7:00 PM"
        }

        result_text, tool_calls, clarification = await processor.process_tool_calls_with_clarification(
            text, user_id=1
        )

        # Should process successfully without clarification
        assert "**Result from book_restaurant:**" in result_text
        assert len(tool_calls) == 1
        assert clarification is None
        assert tool_calls[0].result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_process_tool_calls_with_missing_parameters(self, processor, mock_analyzer, mock_enricher):
        """Test processing tool calls with missing required parameters"""
        text = 'Book a restaurant. ```json\n{"tool": "book_restaurant", "parameters": {"location": "NYC"}}\n```'

        # Mock analysis showing missing parameters
        mock_analysis = ToolInformationAnalysis(
            missing_info=["date", "time"],
            available_info={"location": "NYC"},
            confidence_scores={"date": 0.0, "time": 0.0},
            suggestions=["Please specify date", "Please specify time"],
            can_proceed=False,
            tool_name="book_restaurant"
        )
        mock_analyzer.analyze_tool_call.return_value = mock_analysis

        result_text, tool_calls, clarification = await processor.process_tool_calls_with_clarification(
            text, user_id=1
        )

        # Should return clarification question
        assert result_text == text  # Original text unchanged
        assert len(tool_calls) > 0  # Raw tool calls returned
        assert clarification is not None
        assert "book_restaurant" in clarification
        assert "date" in clarification and "time" in clarification

    @pytest.mark.asyncio
    async def test_validate_and_enrich_tool_call_success(self, processor, mock_analyzer, mock_enricher):
        """Test successful tool call validation and enrichment"""
        tool_call = ToolCall(
            tool_name="book_restaurant",
            parameters={"location": "NYC", "date": "2024-01-15"},
            full_text="mock",
            start_pos=0,
            end_pos=10
        )

        # Mock successful analysis
        mock_analysis = ToolInformationAnalysis(
            can_proceed=True,
            missing_info=[],
            available_info={"location": "NYC", "date": "2024-01-15"}
        )
        mock_analyzer.analyze_tool_call.return_value = mock_analysis

        # Mock parameter enrichment
        mock_enricher.enrich_parameters.return_value = {
            "location": "NYC",
            "date": "2024-01-15",
            "time": "7:00 PM"  # Enriched from context
        }

        result = await processor._validate_and_enrich_tool_call(tool_call, {})

        assert not result["needs_clarification"]
        assert result["clarification_question"] is None
        assert result["enhanced_call"] is not None
        assert result["enhanced_call"].parameters["time"] == "7:00 PM"

    @pytest.mark.asyncio
    async def test_validate_and_enrich_tool_call_needs_clarification(self, processor, mock_analyzer):
        """Test tool call that needs clarification"""
        tool_call = ToolCall(
            tool_name="book_restaurant",
            parameters={"location": "NYC"},
            full_text="mock",
            start_pos=0,
            end_pos=10
        )

        # Mock analysis showing missing information
        mock_analysis = ToolInformationAnalysis(
            can_proceed=False,
            missing_info=["date", "time"],
            available_info={"location": "NYC"}
        )
        mock_analyzer.analyze_tool_call.return_value = mock_analysis

        result = await processor._validate_and_enrich_tool_call(tool_call, {})

        assert result["needs_clarification"]
        assert result["clarification_question"] is not None
        assert "date" in result["clarification_question"]
        assert "time" in result["clarification_question"]
        assert result["enhanced_call"] is None

    def test_generate_tool_clarification_question_single_param(self, processor):
        """Test clarification question generation for single missing parameter"""
        analysis = ToolInformationAnalysis(
            missing_info=["location"],
            available_info={},
            confidence_scores={},
            suggestions=[],
            can_proceed=False,
            tool_name="book_restaurant"
        )

        question = processor._generate_tool_clarification_question(analysis, "book_restaurant")

        assert "book_restaurant" in question
        assert "location" in question
        assert question.endswith("Can you provide this?")

    def test_generate_tool_clarification_question_multiple_params(self, processor):
        """Test clarification question generation for multiple missing parameters"""
        analysis = ToolInformationAnalysis(
            missing_info=["date", "time", "party_size"],
            available_info={},
            confidence_scores={},
            suggestions=[],
            can_proceed=False,
            tool_name="book_restaurant"
        )

        question = processor._generate_tool_clarification_question(analysis, "book_restaurant")

        assert "book_restaurant" in question
        assert "date" in question
        assert "time" in question
        assert "party_size" in question
        assert question.endswith("Can you provide these?")

    @pytest.mark.asyncio
    async def test_validate_tool_response_success(self, processor):
        """Test validation of successful tool response"""
        tool_call = ToolCall("book_restaurant", {}, "mock", 0, 10)
        response = {"status": "success", "confirmation": "12345"}

        clarification = await processor.validate_tool_response(tool_call, response)

        assert clarification is None  # No clarification needed

    @pytest.mark.asyncio
    async def test_validate_tool_response_error_needs_clarification(self, processor):
        """Test validation of tool response with error requiring clarification"""
        tool_call = ToolCall("book_restaurant", {}, "mock", 0, 10)
        response = {"error": "Invalid date format provided"}

        clarification = await processor.validate_tool_response(tool_call, response)

        assert clarification is not None
        assert "book_restaurant" in clarification
        assert "Invalid date format" in clarification

    @pytest.mark.asyncio
    async def test_validate_tool_response_partial_result(self, processor):
        """Test validation of partial tool response"""
        tool_call = ToolCall("search_flights", {}, "mock", 0, 10)
        response = {"results": "partial", "message": "Some flights found"}

        clarification = await processor.validate_tool_response(tool_call, response)

        assert clarification is not None
        assert "partial" in clarification
        assert "search_flights" in clarification

    @pytest.mark.asyncio
    async def test_handle_clarified_tool_execution(self, processor, mock_agent):
        """Test execution of tool with clarified parameters"""
        original_tool_call = ToolCall(
            tool_name="book_restaurant",
            parameters={"location": "NYC"},
            full_text="mock",
            start_pos=0,
            end_pos=10
        )

        clarified_params = {"date": "2024-01-15", "time": "7:00 PM"}

        result = await processor.handle_clarified_tool_execution(original_tool_call, clarified_params)

        # Verify tool was called with merged parameters
        mock_agent.invoke_tool.assert_called_once_with(
            tool_name="book_restaurant",
            parameters={"location": "NYC", "date": "2024-01-15", "time": "7:00 PM"}
        )

        # Verify result
        assert result == {"result": "success"}
        assert original_tool_call.result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_handle_clarified_tool_execution_error(self, processor, mock_agent):
        """Test handling of errors during clarified tool execution"""
        original_tool_call = ToolCall("book_restaurant", {}, "mock", 0, 10)
        clarified_params = {"date": "invalid-date"}

        # Mock tool execution failure
        mock_agent.invoke_tool.side_effect = Exception("Invalid date format")

        result = await processor.handle_clarified_tool_execution(original_tool_call, clarified_params)

        # Verify error handling
        assert "error" in result
        assert "Invalid date format" in result["error"]
        assert original_tool_call.result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_processor_error_handling(self, processor, mock_analyzer):
        """Test processor graceful error handling"""
        text = 'Book a restaurant. ```json\n{"tool": "book_restaurant", "parameters": {}}\n```'

        # Mock analyzer failure
        mock_analyzer.analyze_tool_call.side_effect = Exception("Analysis failed")

        result_text, tool_calls, clarification = await processor.process_tool_calls_with_clarification(
            text, user_id=1
        )

        # Should fall back gracefully
        assert result_text == text
        assert tool_calls == []
        assert clarification is None
