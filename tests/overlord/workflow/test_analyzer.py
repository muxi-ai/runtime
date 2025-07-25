"""
Tests for the Request Analysis Engine.

Tests the RequestAnalyzer class that analyzes user requests for complexity
and determines if workflow orchestration is needed.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from src.muxi.overlord.workflow.analyzer import RequestAnalyzer
from src.muxi.overlord.workflow.types import RequestAnalysis


class TestRequestAnalyzer:
    """Test RequestAnalyzer functionality."""

    def test_analyzer_initialization(self):
        """Test RequestAnalyzer initialization."""
        # Without LLM
        analyzer = RequestAnalyzer()
        assert analyzer.llm is None
        assert analyzer.complexity_threshold == 7.0

        # With LLM
        mock_llm = Mock()
        analyzer = RequestAnalyzer(llm=mock_llm)
        assert analyzer.llm == mock_llm

    def test_threshold_configuration(self):
        """Test complexity threshold configuration."""
        analyzer = RequestAnalyzer()

        # Change threshold
        analyzer.complexity_threshold = 8.5
        assert analyzer.complexity_threshold == 8.5

    @pytest.mark.asyncio
    async def test_analyze_request_simple(self):
        """Test analyzing a simple request without LLM."""
        analyzer = RequestAnalyzer()

        # Simple request
        analysis = await analyzer.analyze_request(
            "What's the weather today?",
            context={}
        )

        assert isinstance(analysis, RequestAnalysis)
        assert analysis.complexity_score < 7.0
        assert analysis.requires_decomposition is False
        assert analysis.requires_approval is False

    @pytest.mark.asyncio
    async def test_analyze_request_complex_heuristic(self):
        """Test analyzing complex request with heuristic analysis."""
        analyzer = RequestAnalyzer()

        # Complex request with multiple indicators
        complex_request = (
            "I need you to research the impact of climate change on renewable energy, "
            "analyze the data from multiple sources, create visualizations, "
            "write a comprehensive report, and present findings to stakeholders. "
            "Please show me the plan first before executing."
        )

        analysis = await analyzer.analyze_request(
            complex_request,
            context={}
        )

        assert analysis.complexity_score >= 7.0
        assert analysis.requires_decomposition is True
        assert analysis.requires_approval is True  # Due to "show me the plan first"

    @pytest.mark.asyncio
    async def test_analyze_request_with_llm(self):
        """Test analyzing request with LLM."""
        # Mock LLM
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = """
        {
            "complexity_score": 8.5,
            "requires_decomposition": true,
            "requires_approval": false,
            "identified_capabilities": ["research", "analysis", "writing"],
            "confidence_score": 0.9,
            "reasoning": "Complex multi-step analytical task"
        }
        """

        analyzer = RequestAnalyzer(llm=mock_llm)

        analysis = await analyzer.analyze_request(
            "Complex analytical request",
            context={}
        )

        assert analysis.complexity_score == 8.5
        assert analysis.requires_decomposition is True
        assert analysis.requires_approval is False
        assert analysis.identified_capabilities == ["research", "analysis", "writing"]
        assert analysis.confidence_score == 0.9
        assert analysis.reasoning == "Complex multi-step analytical task"

    @pytest.mark.asyncio
    async def test_analyze_request_llm_fallback(self):
        """Test fallback to heuristic when LLM fails."""
        # Mock LLM that fails
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = Exception("LLM error")

        analyzer = RequestAnalyzer(llm=mock_llm)

        analysis = await analyzer.analyze_request(
            "Test request",
            context={}
        )

        # Should still return valid analysis
        assert isinstance(analysis, RequestAnalysis)
        assert analysis.confidence_score < 0.8  # Lower confidence for heuristic

    def test_detect_approval_keywords(self):
        """Test approval keyword detection."""
        analyzer = RequestAnalyzer()

        # Test various approval phrases
        approval_phrases = [
            "show me the plan first",
            "let me review before you start",
            "I want to approve the approach",
            "preview the workflow",
            "show me what you'll do",
            "break this down for my approval"
        ]

        for phrase in approval_phrases:
            request = f"Please {phrase} and then proceed"
            requires_approval = analyzer._detect_approval_request(request)
            assert requires_approval is True, f"Failed to detect approval in: {phrase}"

    def test_detect_non_approval(self):
        """Test non-approval request detection."""
        analyzer = RequestAnalyzer()

        non_approval_phrases = [
            "just do it",
            "go ahead and complete this",
            "start immediately",
            "no need for approval"
        ]

        for phrase in non_approval_phrases:
            requires_approval = analyzer._detect_approval_request(phrase)
            assert requires_approval is False, f"False positive for: {phrase}"

    def test_complexity_indicators(self):
        """Test complexity indicator detection."""
        analyzer = RequestAnalyzer()

        # High complexity indicators
        high_complexity_phrases = [
            "research and analyze multiple sources",
            "create comprehensive report with visualizations",
            "coordinate between different teams",
            "complex multi-step process",
            "detailed analysis required"
        ]

        for phrase in high_complexity_phrases:
            score = analyzer._calculate_heuristic_complexity(phrase)
            assert score >= 6.0, f"Low complexity score for: {phrase}"

    def test_low_complexity_detection(self):
        """Test low complexity detection."""
        analyzer = RequestAnalyzer()

        # Low complexity phrases
        low_complexity_phrases = [
            "what time is it?",
            "simple question",
            "quick answer needed",
            "just tell me",
            "one word response"
        ]

        for phrase in low_complexity_phrases:
            score = analyzer._calculate_heuristic_complexity(phrase)
            assert score <= 5.0, f"High complexity score for: {phrase}"

    def test_capability_identification(self):
        """Test capability identification."""
        analyzer = RequestAnalyzer()

        # Test various capabilities
        capability_tests = [
            ("research the topic", ["research"]),
            ("write a report", ["writing"]),
            ("analyze the data", ["analysis"]),
            ("code a solution", ["coding"]),
            ("research and write report", ["research", "writing"]),
            ("analyze data and create visualization", ["analysis", "visualization"])
        ]

        for request, expected_capabilities in capability_tests:
            capabilities = analyzer._identify_capabilities(request)
            for expected in expected_capabilities:
                assert expected in capabilities, (
                    f"Missing {expected} in {capabilities} for '{request}'"
                )

    @pytest.mark.asyncio
    async def test_context_integration(self):
        """Test context integration in analysis."""
        analyzer = RequestAnalyzer()

        # Test with conversation context
        context = {
            "conversation_history": [
                "User: I need help with data analysis",
                "Assistant: I can help with that. What data do you have?",
                "User: I have sales data from last year"
            ],
            "user_preferences": {
                "prefers_detailed_explanations": True,
                "requires_approval": False
            }
        }

        analysis = await analyzer.analyze_request(
            "Now create a comprehensive report",
            context=context
        )

        assert isinstance(analysis, RequestAnalysis)
        # Context should influence the analysis
        assert analysis.complexity_score > 0

    @pytest.mark.asyncio
    async def test_malformed_llm_response(self):
        """Test handling of malformed LLM responses."""
        # Mock LLM with invalid JSON
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "This is not valid JSON"

        analyzer = RequestAnalyzer(llm=mock_llm)

        analysis = await analyzer.analyze_request(
            "Test request",
            context={}
        )

        # Should fallback to heuristic analysis
        assert isinstance(analysis, RequestAnalysis)
        assert analysis.confidence_score < 0.8

    @pytest.mark.asyncio
    async def test_partial_llm_response(self):
        """Test handling of partial LLM responses."""
        # Mock LLM with partial JSON
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = """
        {
            "complexity_score": 6.5,
            "requires_decomposition": true
        }
        """

        analyzer = RequestAnalyzer(llm=mock_llm)

        analysis = await analyzer.analyze_request(
            "Test request",
            context={}
        )

        # Should use LLM values where available, defaults elsewhere
        assert analysis.complexity_score == 6.5
        assert analysis.requires_decomposition is True
        assert analysis.requires_approval is False  # Default value

    def test_threshold_comparison(self):
        """Test complexity threshold comparison."""
        analyzer = RequestAnalyzer()
        analyzer.complexity_threshold = 7.0

        # Test threshold logic
        analysis_low = RequestAnalysis(
            complexity_score=6.0,
            requires_decomposition=False,
            requires_approval=False,
            identified_capabilities=[],
            confidence_score=0.8
        )

        analysis_high = RequestAnalysis(
            complexity_score=8.0,
            requires_decomposition=True,
            requires_approval=False,
            identified_capabilities=[],
            confidence_score=0.8
        )

        # Verify threshold logic would work correctly
        assert analysis_low.complexity_score < analyzer.complexity_threshold
        assert analysis_high.complexity_score > analyzer.complexity_threshold

    @pytest.mark.asyncio
    async def test_edge_cases(self):
        """Test edge cases and error conditions."""
        analyzer = RequestAnalyzer()

        # Empty request
        analysis = await analyzer.analyze_request("", context={})
        assert isinstance(analysis, RequestAnalysis)
        assert analysis.complexity_score <= 3.0

        # Very long request
        long_request = "complex task " * 100
        analysis = await analyzer.analyze_request(long_request, context={})
        assert isinstance(analysis, RequestAnalysis)

        # None context
        analysis = await analyzer.analyze_request("test", context=None)
        assert isinstance(analysis, RequestAnalysis)

    @pytest.mark.asyncio
    async def test_confidence_scoring(self):
        """Test confidence scoring logic."""
        # With LLM - should have high confidence
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = """
        {
            "complexity_score": 7.5,
            "requires_decomposition": true,
            "requires_approval": false,
            "identified_capabilities": ["research"],
            "confidence_score": 0.95
        }
        """

        analyzer_with_llm = RequestAnalyzer(llm=mock_llm)
        analysis = await analyzer_with_llm.analyze_request("test", context={})
        assert analysis.confidence_score == 0.95

        # Without LLM - should have lower confidence
        analyzer_heuristic = RequestAnalyzer()
        analysis = await analyzer_heuristic.analyze_request("test", context={})
        assert analysis.confidence_score < 0.8

    def test_llm_prompt_creation(self):
        """Test LLM prompt creation."""
        analyzer = RequestAnalyzer()

        prompt = analyzer._create_analysis_prompt(
            "Test request",
            context={"key": "value"}
        )

        assert "Test request" in prompt
        assert "complexity" in prompt.lower()
        assert "decomposition" in prompt.lower()
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should be reasonably detailed

    @pytest.mark.asyncio
    async def test_batch_analysis(self):
        """Test analyzing multiple requests."""
        analyzer = RequestAnalyzer()

        requests = [
            "What time is it?",
            "Create a comprehensive business plan with market analysis",
            "Simple math: 2 + 2",
            "Research climate change, analyze data, and write report"
        ]

        analyses = []
        for request in requests:
            analysis = await analyzer.analyze_request(request, context={})
            analyses.append(analysis)

        # Verify complexity scores make sense relative to each other
        simple_scores = [analyses[0].complexity_score, analyses[2].complexity_score]
        complex_scores = [analyses[1].complexity_score, analyses[3].complexity_score]

        assert max(simple_scores) < min(complex_scores)


@pytest.fixture
def mock_llm():
    """Create mock LLM for testing."""
    llm = AsyncMock()
    llm.generate.return_value = """
    {
        "complexity_score": 7.5,
        "requires_decomposition": true,
        "requires_approval": false,
        "identified_capabilities": ["research", "analysis"],
        "confidence_score": 0.9,
        "reasoning": "Multi-step analytical task"
    }
    """
    return llm


class TestRequestAnalyzerIntegration:
    """Integration tests for RequestAnalyzer."""

    @pytest.mark.asyncio
    async def test_analyzer_with_real_scenarios(self, mock_llm):
        """Test analyzer with realistic scenarios."""
        analyzer = RequestAnalyzer(llm=mock_llm)

        scenarios = [
            {
                "request": "Research the renewable energy market, analyze trends, and create a presentation",
                "expected_complex": True,
                "expected_decomposition": True
            },
            {
                "request": "What's 2+2?",
                "expected_complex": False,
                "expected_decomposition": False
            },
            {
                "request": "Help me plan a project. Show me the approach first.",
                "expected_approval": True
            }
        ]

        for scenario in scenarios:
            analysis = await analyzer.analyze_request(
                scenario["request"],
                context={}
            )

            if "expected_complex" in scenario:
                if scenario["expected_complex"]:
                    assert analysis.complexity_score >= analyzer.complexity_threshold
                else:
                    assert analysis.complexity_score < analyzer.complexity_threshold

            if "expected_decomposition" in scenario:
                assert analysis.requires_decomposition == scenario["expected_decomposition"]

            if "expected_approval" in scenario:
                assert analysis.requires_approval == scenario["expected_approval"]
