"""
Unit tests for topic tagging feature.

Tests the topic extraction, normalization, and observability
for the RequestAnalysis topic tagging functionality.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from muxi.datatypes.workflow import RequestAnalysis
from muxi.formation.workflow.analyzer import RequestAnalyzer, ComplexityMethod


# Helper function to create mock LLM with PromptLoader patched
def create_mock_llm_with_prompt(llm_response: str):
    """Create a mock LLM that properly returns the given response."""
    mock_llm = MagicMock()
    mock_llm.generate_text = AsyncMock(return_value=llm_response)
    return mock_llm


class TestTopicTaggingDataclass:
    """Test RequestAnalysis dataclass with topics field."""

    def test_request_analysis_with_topics(self):
        """Test creating RequestAnalysis with topics."""
        analysis = RequestAnalysis(
            complexity_score=5.0,
            requires_decomposition=False,
            requires_approval=False,
            implicit_subtasks=["Step 1"],
            required_capabilities=["writing"],
            acceptance_criteria=["Complete"],
            confidence_score=0.8,
            topics=["writing", "blog", "quarterly-reports"]
        )
        
        assert analysis.topics == ["writing", "blog", "quarterly-reports"]
        assert len(analysis.topics) == 3

    def test_request_analysis_without_topics_default(self):
        """Test RequestAnalysis defaults to empty list when topics not provided."""
        analysis = RequestAnalysis(
            complexity_score=3.0,
            requires_decomposition=False,
            requires_approval=False,
            implicit_subtasks=[],
            required_capabilities=["general"],
            acceptance_criteria=["Done"],
            confidence_score=0.7,
        )
        
        assert analysis.topics == []
        assert isinstance(analysis.topics, list)

    def test_request_analysis_empty_topics_list(self):
        """Test RequestAnalysis accepts empty topics list explicitly."""
        analysis = RequestAnalysis(
            complexity_score=2.0,
            requires_decomposition=False,
            requires_approval=False,
            implicit_subtasks=[],
            required_capabilities=["general"],
            acceptance_criteria=["Complete"],
            topics=[]
        )
        
        assert analysis.topics == []


class TestHeuristicAnalyzerTopics:
    """Test heuristic analyzer returns empty topics."""

    @pytest.mark.asyncio
    async def test_heuristic_returns_empty_topics(self):
        """Test heuristic analysis returns empty topics list."""
        analyzer = RequestAnalyzer(llm=None, complexity_method=ComplexityMethod.HEURISTIC)
        
        result = await analyzer.analyze_request("Write a blog post about AI trends")
        
        assert result.topics == []
        assert isinstance(result.topics, list)

    @pytest.mark.asyncio
    async def test_heuristic_various_requests(self):
        """Test heuristic returns empty topics for various request types."""
        analyzer = RequestAnalyzer(llm=None)
        
        test_cases = [
            "Debug the login API endpoint",
            "Analyze Q4 sales performance",
            "Create a meal plan for next week",
            "Help me understand Python decorators"
        ]
        
        for message in test_cases:
            result = await analyzer.analyze_request(message)
            assert result.topics == [], f"Expected empty topics for: {message}"


class TestLLMAnalyzerTopics:
    """Test LLM analyzer extracts and normalizes topics."""

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_llm_extracts_topics_from_response(self, mock_prompt_loader):
        """Test LLM parser extracts topics from valid JSON response."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        # Create mock LLM that returns JSON with topics
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 6.5,
            "implicit_subtasks": ["Research", "Write", "Review"],
            "required_capabilities": ["writing", "research"],
            "acceptance_criteria": ["Blog post published"],
            "confidence_score": 0.85,
            "is_scheduling_request": false,
            "is_explicit_approval_request": false,
            "explicit_sop_request": null,
            "topics": ["writing", "blog", "artificial-intelligence", "content-creation"],
            "reasoning": "This is a content creation request"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Write a blog post about AI")
        
        assert result.topics == ["writing", "blog", "artificial-intelligence", "content-creation"]
        assert len(result.topics) == 4

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_llm_normalizes_topics(self, mock_prompt_loader):
        """Test topics are normalized to lowercase with stripped whitespace."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 5.0,
            "implicit_subtasks": [],
            "required_capabilities": ["general"],
            "acceptance_criteria": ["Done"],
            "confidence_score": 0.8,
            "topics": ["Writing", "  BLOG  ", "Sales-Analysis", "  quarterly-reports  "],
            "reasoning": "Test"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # All should be lowercase and stripped
        assert result.topics == ["writing", "blog", "sales-analysis", "quarterly-reports"]

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_llm_limits_topics_to_five(self, mock_prompt_loader):
        """Test topics list is limited to maximum of 5 items."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 5.0,
            "implicit_subtasks": [],
            "required_capabilities": ["general"],
            "acceptance_criteria": ["Done"],
            "confidence_score": 0.8,
            "topics": ["topic1", "topic2", "topic3", "topic4", "topic5", "topic6", "topic7"],
            "reasoning": "Test"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # Should be limited to 5
        assert len(result.topics) == 5
        assert result.topics == ["topic1", "topic2", "topic3", "topic4", "topic5"]

    @pytest.mark.asyncio
    async def test_llm_handles_missing_topics_field(self):
        """Test parser handles LLM response without topics field."""
        mock_llm = MagicMock()
        mock_llm.generate_text = AsyncMock(return_value="""
        {
            "complexity_score": 4.0,
            "implicit_subtasks": [],
            "required_capabilities": ["general"],
            "acceptance_criteria": ["Done"],
            "confidence_score": 0.75,
            "reasoning": "Test"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # Should default to empty list
        assert result.topics == []

    @pytest.mark.asyncio
    async def test_llm_handles_empty_topics_array(self):
        """Test parser handles empty topics array in LLM response."""
        mock_llm = MagicMock()
        mock_llm.generate_text = AsyncMock(return_value="""
        {
            "complexity_score": 3.0,
            "implicit_subtasks": [],
            "required_capabilities": ["general"],
            "acceptance_criteria": ["Done"],
            "confidence_score": 0.7,
            "topics": [],
            "reasoning": "Test"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        assert result.topics == []

    @pytest.mark.asyncio
    async def test_llm_handles_malformed_topics(self):
        """Test parser handles malformed topics (not a list)."""
        mock_llm = MagicMock()
        mock_llm.generate_text = AsyncMock(return_value="""
        {
            "complexity_score": 3.0,
            "implicit_subtasks": [],
            "required_capabilities": ["general"],
            "acceptance_criteria": ["Done"],
            "confidence_score": 0.7,
            "topics": "writing, blog, coding",
            "reasoning": "Test"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # Should handle gracefully and return empty list
        assert result.topics == []

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_llm_filters_empty_strings(self, mock_prompt_loader):
        """Test parser filters out empty strings from topics."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 5.0,
            "implicit_subtasks": [],
            "required_capabilities": ["general"],
            "acceptance_criteria": ["Done"],
            "confidence_score": 0.8,
            "topics": ["writing", "", "  ", "blog", null, "coding"],
            "reasoning": "Test"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # Empty strings and whitespace-only should be filtered
        assert result.topics == ["writing", "blog", "coding"]


class TestFallbackPathsTopics:
    """Test all fallback paths return empty topics."""

    @pytest.mark.asyncio
    async def test_llm_error_fallback_returns_empty_topics(self):
        """Test LLM error triggers heuristic fallback with empty topics."""
        mock_llm = AsyncMock()
        mock_llm.generate_text = AsyncMock(side_effect=Exception("LLM error"))
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # Should fallback to heuristic with empty topics
        assert result.topics == []

    @pytest.mark.asyncio
    async def test_parsing_error_fallback_returns_empty_topics(self):
        """Test parsing error returns fallback analysis with empty topics."""
        mock_llm = AsyncMock()
        mock_llm.generate_text = AsyncMock(return_value="Invalid JSON response")
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # Should return fallback with empty topics
        assert result.topics == []

    @pytest.mark.asyncio
    async def test_main_error_fallback_returns_empty_topics(self):
        """Test main analyze_request error returns fallback with empty topics."""
        mock_llm = AsyncMock()
        mock_llm.generate_text = AsyncMock(side_effect=RuntimeError("Critical error"))
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Test message")
        
        # Should catch error and return safe fallback with empty topics
        assert result.topics == []
        assert result.complexity_score == 5.0  # Fallback default


class TestHybridAnalyzerTopics:
    """Test hybrid analyzer uses LLM topics when available."""

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_hybrid_uses_llm_topics(self, mock_prompt_loader):
        """Test hybrid mode uses topics from LLM when available."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 6.0,
            "implicit_subtasks": ["Step 1"],
            "required_capabilities": ["writing"],
            "acceptance_criteria": ["Done"],
            "confidence_score": 0.85,
            "topics": ["debugging", "api", "backend"],
            "reasoning": "Test"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.HYBRID)
        result = await analyzer.analyze_request("Debug the API")
        
        # Should use LLM topics
        assert result.topics == ["debugging", "api", "backend"]

    @pytest.mark.asyncio
    async def test_hybrid_fallback_empty_topics_on_llm_error(self):
        """Test hybrid mode returns empty topics when LLM fails."""
        mock_llm = AsyncMock()
        mock_llm.generate_text = AsyncMock(side_effect=Exception("LLM failed"))
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.HYBRID)
        result = await analyzer.analyze_request("Test message")
        
        # Should fallback to heuristic with empty topics
        assert result.topics == []


class TestTopicExamples:
    """Test realistic topic extraction examples."""

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_blog_writing_topics(self, mock_prompt_loader):
        """Test topics for blog writing request."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 7.0,
            "implicit_subtasks": ["Research", "Write", "Format"],
            "required_capabilities": ["writing", "research"],
            "acceptance_criteria": ["Blog post complete"],
            "confidence_score": 0.9,
            "topics": ["writing", "blog", "artificial-intelligence", "content-creation"],
            "reasoning": "Writing task"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Write a blog post about AI trends")
        
        assert "writing" in result.topics
        assert "blog" in result.topics
        assert len(result.topics) > 0

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_debugging_topics(self, mock_prompt_loader):
        """Test topics for debugging request."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 6.0,
            "implicit_subtasks": ["Investigate", "Fix"],
            "required_capabilities": ["debugging"],
            "acceptance_criteria": ["Bug fixed"],
            "confidence_score": 0.85,
            "topics": ["debugging", "api", "authentication", "backend"],
            "reasoning": "Debug task"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Debug the login API endpoint")
        
        assert "debugging" in result.topics
        assert "api" in result.topics

    @pytest.mark.asyncio
    @patch('muxi.formation.prompts.loader.PromptLoader')
    async def test_data_analysis_topics(self, mock_prompt_loader):
        """Test topics for data analysis request."""
        mock_prompt_loader.get.return_value = "Mock prompt"
        
        mock_llm = create_mock_llm_with_prompt("""
        {
            "complexity_score": 8.0,
            "implicit_subtasks": ["Gather data", "Analyze", "Report"],
            "required_capabilities": ["data_analysis", "research"],
            "acceptance_criteria": ["Analysis complete"],
            "confidence_score": 0.9,
            "topics": ["data-analysis", "sales", "quarterly-reports", "business-intelligence"],
            "reasoning": "Analysis task"
        }
        """)
        
        analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)
        result = await analyzer.analyze_request("Analyze Q4 sales performance")
        
        assert "data-analysis" in result.topics or "sales" in result.topics
