"""
Test 15A2: Topic Tagging Fallback Behavior

Tests that the system handles fallback scenarios gracefully:
- No LLM configured (heuristic mode)
- LLM errors
- Malformed responses

All fallbacks should return empty topics list without breaking the system.
"""
import pytest
from pathlib import Path
from muxi.runtime.formation.workflow.analyzer import RequestAnalyzer, ComplexityMethod


@pytest.mark.asyncio
async def test_heuristic_analyzer_returns_empty_topics():
    """Test heuristic analyzer returns empty topics (no LLM)."""
    analyzer = RequestAnalyzer(llm=None, complexity_method=ComplexityMethod.HEURISTIC)

    test_messages = [
        "Write a blog post about AI trends",
        "Debug the login API endpoint",
        "Analyze Q4 sales data",
        "Create a meal plan for next week"
    ]

    for message in test_messages:
        result = await analyzer.analyze_request(message)

        # Heuristic mode should always return empty topics
        assert result.topics == [], f"Expected empty topics for heuristic analysis of: {message}"
        assert isinstance(result.topics, list)

        # Other analysis fields should still work
        assert result.complexity_score > 0
        assert len(result.required_capabilities) > 0

        print(f"✓ Heuristic analysis for '{message[:50]}...'")
        print(f"  Topics: {result.topics} (empty as expected)")
        print(f"  Complexity: {result.complexity_score}")


@pytest.mark.asyncio
async def test_llm_error_returns_empty_topics():
    """Test LLM error gracefully returns empty topics."""
    from unittest.mock import AsyncMock

    # Mock LLM that throws error
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(side_effect=Exception("LLM service unavailable"))

    analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)

    result = await analyzer.analyze_request("Test message")

    # Should fallback to heuristic with empty topics
    assert result.topics == []
    assert result.complexity_score > 0  # Heuristic still provides score

    print(f"\n✓ LLM error handled gracefully")
    print(f"  Topics: {result.topics} (empty from fallback)")
    print(f"  System remained stable")


@pytest.mark.asyncio
async def test_malformed_json_returns_empty_topics():
    """Test malformed LLM response returns empty topics."""
    from unittest.mock import AsyncMock

    # Mock LLM that returns invalid JSON
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(return_value="This is not JSON at all!")

    analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)

    result = await analyzer.analyze_request("Test message")

    # Should handle gracefully with empty topics
    assert result.topics == []
    assert result.complexity_score > 0

    print(f"\n✓ Malformed JSON handled gracefully")
    print(f"  Topics: {result.topics} (empty from error handler)")


@pytest.mark.asyncio
async def test_missing_topics_field_returns_empty():
    """Test LLM response without topics field returns empty list."""
    from unittest.mock import AsyncMock

    # Mock LLM that returns valid JSON but no topics field
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(return_value="""
    {
        "complexity_score": 5.0,
        "implicit_subtasks": ["Step 1"],
        "required_capabilities": ["general"],
        "acceptance_criteria": ["Done"],
        "confidence_score": 0.8,
        "reasoning": "Test response without topics"
    }
    """)

    analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)

    result = await analyzer.analyze_request("Test message")

    # Should default to empty list
    assert result.topics == []
    assert result.complexity_score == 5.0

    print(f"\n✓ Missing topics field handled")
    print(f"  Topics: {result.topics} (defaults to empty)")


@pytest.mark.asyncio
async def test_topics_not_array_returns_empty():
    """Test topics field that's not an array is handled gracefully."""
    from unittest.mock import AsyncMock

    # Mock LLM that returns topics as string instead of array
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(return_value="""
    {
        "complexity_score": 5.0,
        "implicit_subtasks": [],
        "required_capabilities": ["general"],
        "acceptance_criteria": ["Done"],
        "confidence_score": 0.8,
        "topics": "writing, blog, coding",
        "reasoning": "Test"
    }
    """)

    analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)

    result = await analyzer.analyze_request("Test message")

    # Should convert to empty list (not throw error)
    assert result.topics == []

    print(f"\n✓ Non-array topics handled")
    print(f"  Topics: {result.topics} (converted to empty)")


@pytest.mark.asyncio
async def test_empty_topics_array_returns_empty():
    """Test explicitly empty topics array is preserved."""
    from unittest.mock import AsyncMock

    # Mock LLM that returns empty topics array
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(return_value="""
    {
        "complexity_score": 3.0,
        "implicit_subtasks": [],
        "required_capabilities": ["general"],
        "acceptance_criteria": ["Done"],
        "confidence_score": 0.7,
        "topics": [],
        "reasoning": "Simple request with no clear topics"
    }
    """)

    analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)

    result = await analyzer.analyze_request("Test message")

    assert result.topics == []

    print(f"\n✓ Empty topics array preserved")
    print(f"  Topics: {result.topics}")


@pytest.mark.asyncio
async def test_topics_with_empty_strings_filtered():
    """Test empty strings in topics are filtered out."""
    from unittest.mock import AsyncMock

    # Mock LLM that returns topics with empty/whitespace items
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(return_value="""
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

    # Empty strings should be filtered out
    assert result.topics == ["writing", "blog", "coding"]
    assert "" not in result.topics
    assert "  " not in result.topics

    print(f"\n✓ Empty strings filtered from topics")
    print(f"  Topics: {result.topics}")


@pytest.mark.asyncio
async def test_topics_normalized_to_lowercase():
    """Test topics are normalized to lowercase."""
    from unittest.mock import AsyncMock

    # Mock LLM that returns mixed-case topics
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(return_value="""
    {
        "complexity_score": 5.0,
        "implicit_subtasks": [],
        "required_capabilities": ["general"],
        "acceptance_criteria": ["Done"],
        "confidence_score": 0.8,
        "topics": ["Writing", "BLOG", "Sales-Analysis", "  Quarterly-Reports  "],
        "reasoning": "Test"
    }
    """)

    analyzer = RequestAnalyzer(llm=mock_llm, complexity_method=ComplexityMethod.LLM)

    result = await analyzer.analyze_request("Test message")

    # All should be lowercase and stripped
    assert result.topics == ["writing", "blog", "sales-analysis", "quarterly-reports"]
    assert all(t == t.lower() for t in result.topics)
    assert all(t == t.strip() for t in result.topics)

    print(f"\n✓ Topics normalized to lowercase")
    print(f"  Topics: {result.topics}")


@pytest.mark.asyncio
async def test_topics_limited_to_five():
    """Test topics list is limited to maximum of 5 items."""
    from unittest.mock import AsyncMock

    # Mock LLM that returns too many topics
    mock_llm = AsyncMock()
    mock_llm.generate_text = AsyncMock(return_value="""
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

    print(f"\n✓ Topics limited to 5 items")
    print(f"  Topics: {result.topics}")
    print(f"  Count: {len(result.topics)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
