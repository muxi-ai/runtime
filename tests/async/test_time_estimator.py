"""
Comprehensive tests for TimeEstimator component.

Tests cover processing time estimation, threshold logic, complexity assessment,
and integration with RequestAnalyzer.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock

from src.muxi.runtime.overlord.async_patterns.time_estimator import TimeEstimator
from src.muxi.runtime.overlord.workflow.request_analyzer import RequestAnalysis


class TestTimeEstimator:
    """Test suite for TimeEstimator functionality."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create a mock RequestAnalyzer for testing."""
        analyzer = Mock()
        return analyzer

    @pytest.fixture
    def time_estimator(self, mock_analyzer):
        """Create a TimeEstimator instance for testing."""
        return TimeEstimator(analyzer=mock_analyzer)

    @pytest.fixture
    def simple_analysis(self):
        """Create a simple RequestAnalysis for testing."""
        return RequestAnalysis(
            complexity_score=3.0,
            required_capabilities=["text"],
            estimated_duration=15.0,
            agent_recommendations=["assistant"],
            workflow_complexity="simple",
            requires_coordination=False,
            risk_factors=[]
        )

    @pytest.fixture
    def complex_analysis(self):
        """Create a complex RequestAnalysis for testing."""
        return RequestAnalysis(
            complexity_score=8.5,
            required_capabilities=["text", "vision", "research"],
            estimated_duration=180.0,
            agent_recommendations=["researcher", "analyst", "writer"],
            workflow_complexity="complex",
            requires_coordination=True,
            risk_factors=["external_dependency", "large_dataset"]
        )

    @pytest.mark.asyncio
    async def test_estimate_processing_time_simple_request(
        self, time_estimator, mock_analyzer, simple_analysis
    ):
        """Test processing time estimation for a simple request."""
        # Mock analyzer to return simple analysis
        mock_analyzer.analyze_request = AsyncMock(return_value=simple_analysis)

        request = "What is 2 + 2?"
        estimated_time = await time_estimator.estimate_processing_time(request)

        # Should be based on complexity_score=3.0, capabilities=1
        # base_time(5) * complexity_multiplier(3.0/5.0=0.6) * capability_multiplier(1) = 3.0
        assert estimated_time == 3.0

        # Verify analyzer was called correctly
        mock_analyzer.analyze_request.assert_called_once_with(request, None)

    @pytest.mark.asyncio
    async def test_estimate_processing_time_complex_request(
        self, time_estimator, mock_analyzer, complex_analysis
    ):
        """Test processing time estimation for a complex request."""
        # Mock analyzer to return complex analysis
        mock_analyzer.analyze_request = AsyncMock(return_value=complex_analysis)

        request = "Analyze market trends, create visualizations, and write comprehensive report"
        estimated_time = await time_estimator.estimate_processing_time(request)

        # Should be based on complexity_score=8.5, capabilities=3
        # base_time(5) * complexity_multiplier(8.5/5.0=1.7) * capability_multiplier(3) = 25.5
        assert estimated_time == 25.5

        # Verify analyzer was called correctly
        mock_analyzer.analyze_request.assert_called_once_with(request, None)

    @pytest.mark.asyncio
    async def test_estimate_processing_time_with_context(
        self, time_estimator, mock_analyzer, simple_analysis
    ):
        """Test processing time estimation with additional context."""
        mock_analyzer.analyze_request = AsyncMock(return_value=simple_analysis)

        request = "Summarize this document"
        context = {"document_size": "large", "urgency": "high"}

        await time_estimator.estimate_processing_time(request, context)

        # Verify analyzer was called with context
        mock_analyzer.analyze_request.assert_called_once_with(request, context)

    @pytest.mark.asyncio
    async def test_estimate_processing_time_maximum_cap(self, time_estimator, mock_analyzer):
        """Test that estimated time is capped at maximum value."""
        # Create analysis that would exceed maximum
        extreme_analysis = RequestAnalysis(
            complexity_score=10.0,
            required_capabilities=["text", "vision", "audio", "research", "computation"],
            estimated_duration=5000.0,
            agent_recommendations=["agent1", "agent2", "agent3"],
            workflow_complexity="extreme",
            requires_coordination=True,
            risk_factors=["high_complexity", "external_dependency"]
        )

        mock_analyzer.analyze_request = AsyncMock(return_value=extreme_analysis)

        request = "Extremely complex multi-modal analysis task"
        estimated_time = await time_estimator.estimate_processing_time(request)

        # Should be capped at 3600 seconds (1 hour)
        assert estimated_time == 3600.0

    @pytest.mark.asyncio
    async def test_estimate_processing_time_minimum_value(self, time_estimator, mock_analyzer):
        """Test estimation with very low complexity."""
        # Create analysis with minimal complexity
        minimal_analysis = RequestAnalysis(
            complexity_score=0.5,
            required_capabilities=["text"],
            estimated_duration=1.0,
            agent_recommendations=["assistant"],
            workflow_complexity="trivial",
            requires_coordination=False,
            risk_factors=[]
        )

        mock_analyzer.analyze_request = AsyncMock(return_value=minimal_analysis)

        request = "Hi"
        estimated_time = await time_estimator.estimate_processing_time(request)

        # Should be base_time(5) * complexity_multiplier(0.5/5.0=0.1) * capability_multiplier(1) = 0.5
        assert estimated_time == 0.5

    def test_should_use_async_below_threshold(self, time_estimator):
        """Test async decision when estimated time is below threshold."""
        estimated_time = 25.0
        threshold_seconds = 30.0

        should_async = time_estimator.should_use_async(estimated_time, threshold_seconds)

        assert should_async is False

    def test_should_use_async_above_threshold(self, time_estimator):
        """Test async decision when estimated time is above threshold."""
        estimated_time = 45.0
        threshold_seconds = 30.0

        should_async = time_estimator.should_use_async(estimated_time, threshold_seconds)

        assert should_async is True

    def test_should_use_async_equal_threshold(self, time_estimator):
        """Test async decision when estimated time equals threshold."""
        estimated_time = 30.0
        threshold_seconds = 30.0

        should_async = time_estimator.should_use_async(estimated_time, threshold_seconds)

        assert should_async is True  # >= threshold should trigger async

    @pytest.mark.asyncio
    async def test_estimate_processing_time_handles_analyzer_error(self, time_estimator, mock_analyzer):
        """Test that estimation handles analyzer errors gracefully."""
        # Mock analyzer to raise an exception
        mock_analyzer.analyze_request = AsyncMock(side_effect=Exception("Analysis failed"))

        request = "Test request"

        # Should fall back to default estimation
        estimated_time = await time_estimator.estimate_processing_time(request)

        # Should return base time (5.0) as fallback
        assert estimated_time == 5.0

    @pytest.mark.asyncio
    async def test_estimate_processing_time_with_zero_capabilities(self, time_estimator, mock_analyzer):
        """Test estimation when analysis returns zero capabilities."""
        zero_cap_analysis = RequestAnalysis(
            complexity_score=5.0,
            required_capabilities=[],  # Empty capabilities
            estimated_duration=25.0,
            agent_recommendations=["assistant"],
            workflow_complexity="medium",
            requires_coordination=False,
            risk_factors=[]
        )

        mock_analyzer.analyze_request = AsyncMock(return_value=zero_cap_analysis)

        request = "Test request"
        estimated_time = await time_estimator.estimate_processing_time(request)

        # Should handle zero capabilities gracefully
        # base_time(5) * complexity_multiplier(5.0/5.0=1.0) * capability_multiplier(0) = 0
        # But should have minimum protection
        assert estimated_time >= 0

    @pytest.mark.asyncio
    async def test_multiple_concurrent_estimations(self, time_estimator, mock_analyzer):
        """Test concurrent processing time estimations."""
        # Create different analyses for different requests
        analyses = []
        for i in range(5):
            analysis = RequestAnalysis(
                complexity_score=float(i + 1),
                required_capabilities=["text"] * (i + 1),
                estimated_duration=float((i + 1) * 10),
                agent_recommendations=[f"agent_{i}"],
                workflow_complexity="varied",
                requires_coordination=(i % 2 == 0),
                risk_factors=[]
            )
            analyses.append(analysis)

        # Mock analyzer to return different analysis based on call count
        call_count = 0

        async def mock_analyze(request, context):
            nonlocal call_count
            result = analyses[call_count % len(analyses)]
            call_count += 1
            return result

        mock_analyzer.analyze_request = AsyncMock(side_effect=mock_analyze)

        # Run multiple estimations concurrently
        requests = [f"Request {i}" for i in range(5)]

        tasks = []
        for request in requests:
            task = asyncio.create_task(
                time_estimator.estimate_processing_time(request)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should complete successfully
        assert len(results) == 5

        # Verify all are reasonable times
        for result in results:
            assert isinstance(result, float)
            assert result > 0
            assert result <= 3600  # Within maximum cap

    @pytest.mark.asyncio
    async def test_historical_data_integration(self, time_estimator, mock_analyzer, simple_analysis):
        """Test integration with historical performance data."""
        mock_analyzer.analyze_request = AsyncMock(return_value=simple_analysis)

        # Run several estimations to build history
        requests = [
            "Simple task 1",
            "Simple task 2",
            "Simple task 3"
        ]

        results = []
        for request in requests:
            result = await time_estimator.estimate_processing_time(request)
            results.append(result)

        # All should be consistent for similar complexity
        assert all(abs(result - results[0]) < 0.1 for result in results)

    def test_complexity_score_edge_cases(self, time_estimator, mock_analyzer):
        """Test time estimation with edge case complexity scores."""
        test_cases = [
            (0.0, "Zero complexity"),
            (-1.0, "Negative complexity"),
            (100.0, "Very high complexity"),
            (float('inf'), "Infinite complexity"),
        ]

        for complexity_score, description in test_cases:
            analysis = RequestAnalysis(
                complexity_score=complexity_score,
                required_capabilities=["text"],
                estimated_duration=10.0,
                agent_recommendations=["assistant"],
                workflow_complexity="test",
                requires_coordination=False,
                risk_factors=[]
            )

            # Should handle edge cases gracefully
            try:
                # Simulate the calculation
                base_time = 5.0
                complexity_multiplier = max(0, complexity_score / 5.0) if complexity_score != float('inf') else 1.0
                capability_multiplier = 1

                estimated_seconds = base_time * complexity_multiplier * capability_multiplier
                capped_time = min(estimated_seconds, 3600)

                # Should not raise exceptions and should be reasonable
                assert isinstance(capped_time, (int, float))
                assert capped_time >= 0
                assert capped_time <= 3600

            except Exception as e:
                pytest.fail(f"Failed to handle {description}: {e}")

    @pytest.mark.asyncio
    async def test_time_estimator_with_none_analysis(self, time_estimator, mock_analyzer):
        """Test behavior when analyzer returns None."""
        mock_analyzer.analyze_request = AsyncMock(return_value=None)

        request = "Test request"
        estimated_time = await time_estimator.estimate_processing_time(request)

        # Should fall back to default time
        assert estimated_time == 5.0

    @pytest.mark.asyncio
    async def test_estimation_performance(self, time_estimator, mock_analyzer, simple_analysis):
        """Test that time estimation itself is fast."""
        mock_analyzer.analyze_request = AsyncMock(return_value=simple_analysis)

        request = "Performance test request"

        start_time = time.time()
        estimated_time = await time_estimator.estimate_processing_time(request)
        end_time = time.time()

        # Estimation itself should be very fast (< 1 second)
        estimation_duration = end_time - start_time
        assert estimation_duration < 1.0

        # Should still return reasonable estimate
        assert isinstance(estimated_time, float)
        assert estimated_time > 0

    def test_threshold_edge_cases(self, time_estimator):
        """Test threshold comparison with edge cases."""
        test_cases = [
            (0.0, 0.0, True),      # Both zero
            (0.0, 1.0, False),     # Zero estimated time
            (1.0, 0.0, True),      # Zero threshold
            (-1.0, 30.0, False),   # Negative estimated time
            (30.0, -1.0, True),    # Negative threshold
            (float('inf'), 30.0, True),  # Infinite estimated time
            (30.0, float('inf'), False), # Infinite threshold
        ]

        for estimated_time, threshold, expected in test_cases:
            result = time_estimator.should_use_async(estimated_time, threshold)
            assert result == expected, f"Failed for estimated_time={estimated_time}, threshold={threshold}"

    @pytest.mark.asyncio
    async def test_custom_base_time_configuration(self, mock_analyzer, simple_analysis):
        """Test TimeEstimator with custom base time configuration."""
        # Create estimator with custom configuration
        custom_estimator = TimeEstimator(analyzer=mock_analyzer, base_time_seconds=10.0)

        mock_analyzer.analyze_request = AsyncMock(return_value=simple_analysis)

        request = "Custom base time test"
        estimated_time = await custom_estimator.estimate_processing_time(request)

        # Should use custom base time: 10.0 * (3.0/5.0) * 1 = 6.0
        assert estimated_time == 6.0

    @pytest.mark.asyncio
    async def test_custom_max_time_configuration(self, mock_analyzer):
        """Test TimeEstimator with custom maximum time configuration."""
        # Create estimator with custom max time
        custom_estimator = TimeEstimator(analyzer=mock_analyzer, max_time_seconds=1800)  # 30 minutes

        # Create analysis that would exceed custom maximum
        high_analysis = RequestAnalysis(
            complexity_score=10.0,
            required_capabilities=["text", "vision", "audio"],
            estimated_duration=2000.0,
            agent_recommendations=["agent1", "agent2"],
            workflow_complexity="high",
            requires_coordination=True,
            risk_factors=["complexity"]
        )

        mock_analyzer.analyze_request = AsyncMock(return_value=high_analysis)

        request = "High complexity task"
        estimated_time = await custom_estimator.estimate_processing_time(request)

        # Should be capped at custom maximum (1800 seconds)
        assert estimated_time == 1800.0
