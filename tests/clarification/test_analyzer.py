"""
Unit tests for InformationAnalyzer class.

Tests the analysis of requests and detection of missing information for both
tools and reasoning scenarios.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from runtime.muxi.runtime.clarification.analyzer import InformationAnalyzer
from runtime.muxi.runtime.clarification.types import (
    InformationAnalysis,
    ToolInformationAnalysis,
    ReasoningInformationAnalysis,
    InformationAnalysisError
)


class TestInformationAnalyzer:
    """Test InformationAnalyzer functionality"""

    @pytest.fixture
    def analyzer(self):
        """Create InformationAnalyzer instance for testing"""
        mock_model = MagicMock()
        mock_model.generate = AsyncMock(return_value="Mock response")
        return InformationAnalyzer(model=mock_model)

    @pytest.fixture
    def analyzer_no_model(self):
        """Create InformationAnalyzer without model for testing fallback behavior"""
        return InformationAnalyzer(model=None)

    @pytest.mark.asyncio
    async def test_analyze_request_tool_scenario(self, analyzer):
        """Test analyzing a tool-based request"""
        user_message = "Book me a restaurant for tonight"
        intent = "restaurant_booking"
        available_tools = ["book_restaurant", "search_restaurants"]
        user_context = {"location": "New York"}

        result = await analyzer.analyze_request(
            user_message=user_message,
            intent=intent,
            available_tools=available_tools,
            user_context=user_context
        )

        assert isinstance(result, InformationAnalysis)
        assert isinstance(result.missing_info, list)
        assert isinstance(result.available_info, dict)
        assert isinstance(result.confidence_scores, dict)
        assert isinstance(result.suggestions, list)
        assert isinstance(result.can_proceed, bool)

    @pytest.mark.asyncio
    async def test_analyze_request_reasoning_scenario(self, analyzer):
        """Test analyzing a reasoning-based request"""
        user_message = "Give me investment advice"
        intent = "investment_advice"
        available_tools = []  # No tools available, should trigger reasoning analysis
        user_context = {}

        result = await analyzer.analyze_request(
            user_message=user_message,
            intent=intent,
            available_tools=available_tools,
            user_context=user_context
        )

        assert isinstance(result, InformationAnalysis)
        assert len(result.missing_info) > 0  # Should detect missing investment context
        assert result.reasoning_context_needed is not None

    @pytest.mark.asyncio
    async def test_analyze_tool_requirements_book_restaurant(self, analyzer):
        """Test analyzing tool requirements for restaurant booking"""
        tool_name = "book_restaurant"
        provided_params = {"party_size": 4}
        user_context = {"location": "San Francisco"}

        result = await analyzer.analyze_tool_requirements(
            tool_name=tool_name,
            provided_params=provided_params,
            user_context=user_context
        )

        assert isinstance(result, ToolInformationAnalysis)
        assert result.tool_name == tool_name
        assert "location" not in result.missing_required_params  # Should be filled from context
        assert "date" in result.missing_required_params  # Should be missing
        assert "time" in result.missing_required_params  # Should be missing
        assert "party_size" not in result.missing_required_params  # Provided

    @pytest.mark.asyncio
    async def test_analyze_tool_requirements_missing_all(self, analyzer):
        """Test analyzing tool requirements when all parameters are missing"""
        tool_name = "book_restaurant"
        provided_params = {}
        user_context = {}

        result = await analyzer.analyze_tool_requirements(
            tool_name=tool_name,
            provided_params=provided_params,
            user_context=user_context
        )

        assert isinstance(result, ToolInformationAnalysis)
        assert len(result.missing_required_params) == 4  # location, date, time, party_size
        assert not result.can_proceed  # Cannot proceed without required params

    @pytest.mark.asyncio
    async def test_analyze_reasoning_requirements_investment(self, analyzer):
        """Test analyzing reasoning requirements for investment advice"""
        intent = "investment_advice"
        user_message = "I want to invest my money"
        user_context = {"age": 30}

        result = await analyzer.analyze_reasoning_requirements(
            intent=intent,
            user_message=user_message,
            user_context=user_context
        )

        assert isinstance(result, ReasoningInformationAnalysis)
        assert result.intent == intent
        assert result.complexity_level == "complex"
        assert "risk_tolerance" in result.context_gaps
        assert "investment_timeline" in result.context_gaps
        assert "financial_goals" in result.context_gaps

    @pytest.mark.asyncio
    async def test_analyze_reasoning_requirements_technical(self, analyzer):
        """Test analyzing reasoning requirements for technical explanation"""
        intent = "technical_explanation"
        user_message = "Explain machine learning to me"
        user_context = {}

        result = await analyzer.analyze_reasoning_requirements(
            intent=intent,
            user_message=user_message,
            user_context=user_context
        )

        assert isinstance(result, ReasoningInformationAnalysis)
        assert result.intent == intent
        assert result.complexity_level == "moderate"
        assert "technical_background" in result.user_background_needed
        assert "experience_level" in result.user_background_needed

    @pytest.mark.asyncio
    async def test_enrich_with_context(self, analyzer):
        """Test enriching missing information with user context"""
        missing_info = ["location", "cuisine", "unknown_param"]
        user_context = {
            "city": "Boston",
            "favorite_cuisine": "Italian",
            "other_info": "Some other data"
        }

        enriched = await analyzer.enrich_with_context(missing_info, user_context)

        assert "location" in enriched
        assert enriched["location"] == "Boston"  # Should map city -> location
        assert "cuisine" in enriched
        assert enriched["cuisine"] == "Italian"  # Should map favorite_cuisine -> cuisine
        assert "unknown_param" not in enriched  # Should not find mapping

    @pytest.mark.asyncio
    async def test_identify_potential_tool(self, analyzer):
        """Test tool identification from user messages"""
        # Test direct tool name match
        tool = await analyzer._identify_potential_tool(
            "Book a restaurant for me",
            ["book_restaurant", "search_hotels"]
        )
        assert tool == "book_restaurant"

        # Test keyword matching
        tool = await analyzer._identify_potential_tool(
            "I want to reserve a table",
            ["book_restaurant", "search_hotels"]
        )
        assert tool == "book_restaurant"

        # Test no match
        tool = await analyzer._identify_potential_tool(
            "Tell me about quantum physics",
            ["book_restaurant", "search_hotels"]
        )
        assert tool is None

    @pytest.mark.asyncio
    async def test_find_in_context_direct_match(self, analyzer):
        """Test finding parameters directly in user context"""
        user_context = {"location": "Seattle", "party_size": 6}

        # Direct match
        value = analyzer._find_in_context("location", user_context)
        assert value == "Seattle"

        # No match
        value = analyzer._find_in_context("unknown", user_context)
        assert value is None

    @pytest.mark.asyncio
    async def test_find_in_context_mapping(self, analyzer):
        """Test finding parameters using context mappings"""
        user_context = {"city": "Denver", "people": 8}

        # Should map city -> location
        value = analyzer._find_in_context("location", user_context)
        assert value == "Denver"

        # Should map people -> party_size
        value = analyzer._find_in_context("party_size", user_context)
        assert value == 8

    @pytest.mark.asyncio
    async def test_extract_context_value_dict(self, analyzer):
        """Test extracting values from structured context items"""
        # Test dict with 'value' key
        context_item = {"value": "New York", "importance": 0.8}
        value = analyzer._extract_context_value(context_item)
        assert value == "New York"

        # Test plain dict
        context_item = {"city": "Chicago", "state": "IL"}
        value = analyzer._extract_context_value(context_item)
        assert value == {"city": "Chicago", "state": "IL"}

        # Test plain value
        value = analyzer._extract_context_value("Simple string")
        assert value == "Simple string"

    @pytest.mark.asyncio
    async def test_error_handling(self, analyzer):
        """Test error handling in analyzer methods"""
        # Test with invalid input that should raise InformationAnalysisError
        with pytest.raises(InformationAnalysisError):
            # Mock a method to raise an exception
            analyzer._get_tool_schema = AsyncMock(side_effect=Exception("Test error"))
            await analyzer.analyze_tool_requirements("invalid_tool", {}, {})

    @pytest.mark.asyncio
    async def test_analyzer_without_model(self, analyzer_no_model):
        """Test analyzer functionality without LLM model"""
        user_message = "Book me a restaurant"
        intent = "restaurant_booking"
        available_tools = ["book_restaurant"]
        user_context = {}

        # Should work without model, using fallback logic
        result = await analyzer_no_model.analyze_request(
            user_message=user_message,
            intent=intent,
            available_tools=available_tools,
            user_context=user_context
        )

        assert isinstance(result, InformationAnalysis)
        assert isinstance(result.missing_info, list)


class TestAnalyzerHelperMethods:
    """Test helper methods in InformationAnalyzer"""

    @pytest.fixture
    def analyzer(self):
        return InformationAnalyzer(model=None)

    def test_analyze_financial_intent(self, analyzer):
        """Test financial intent analysis"""
        user_context = {"risk_tolerance": "moderate"}

        context_gaps, background_needed = analyzer._analyze_financial_intent(user_context)

        # Should not include risk_tolerance in gaps (already provided)
        assert "risk_tolerance" not in context_gaps
        # Should include missing financial context
        assert "investment_timeline" in context_gaps
        assert "financial_goals" in context_gaps

    def test_analyze_explanation_intent(self, analyzer):
        """Test explanation intent analysis"""
        user_message = "Explain AI to me"
        user_context = {}

        context_gaps, background_needed = analyzer._analyze_explanation_intent(
            user_message, user_context
        )

        assert "technical_background" in background_needed
        assert "experience_level" in background_needed

    def test_analyze_generic_context_needs(self, analyzer):
        """Test generic context analysis"""
        # Short message should trigger need for more details
        short_message = "Help me"
        context_gaps = analyzer._analyze_generic_context_needs(short_message, {})
        assert "more_details" in context_gaps

        # Longer message should not
        long_message = "I need help with setting up a development environment for Python"
        context_gaps = analyzer._analyze_generic_context_needs(long_message, {})
        assert len(context_gaps) == 0

    def test_generate_tool_suggestions(self, analyzer):
        """Test tool suggestion generation"""
        suggestions = analyzer._generate_tool_suggestions(
            "book_restaurant",
            ["location", "date"]
        )

        assert len(suggestions) == 2
        assert any("location" in s for s in suggestions)
        assert any("date" in s for s in suggestions)

    def test_generate_reasoning_suggestions(self, analyzer):
        """Test reasoning suggestion generation"""
        suggestions = analyzer._generate_reasoning_suggestions(
            "investment advice",
            ["risk_tolerance", "timeline"]
        )

        assert len(suggestions) == 2
        assert any("risk_tolerance" in s for s in suggestions)
        assert any("timeline" in s for s in suggestions)
