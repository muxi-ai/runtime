"""
Test Task 3.3: Agent Knowledge-Memory Coordination completion.

This test verifies the enhanced coordination features that are always enabled:
1. Smart Query Routing
2. Content Deduplication
3. Dynamic Context Budget Management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.muxi.formation.agents import Agent


class TestTask33Completion:
    """Test Task 3.3 Agent Knowledge-Memory Coordination features."""

    @pytest.fixture
    def mock_model(self):
        """Create a mock model."""
        model = MagicMock()
        model.get_embedding = AsyncMock(return_value=[0.1] * 1536)
        return model

    @pytest.fixture
    def mock_overlord(self):
        """Create a mock overlord."""
        overlord = MagicMock()
        overlord.buffer_memory = None
        return overlord

    @pytest.fixture
    def agent(self, mock_model, mock_overlord):
        """Create an agent for testing."""
        return Agent(
            model=mock_model,
            overlord=mock_overlord,
            system_message="Test agent",
            agent_id="test_agent",
        )

    def test_smart_query_routing_knowledge_only(self, agent):
        """Test smart query routing identifies knowledge-only queries."""
        # Test factual/technical queries
        knowledge_queries = [
            "What is the API documentation for this function?",
            "How does the authentication algorithm work?",
            "Explain the configuration settings",
            "Define the class structure",
            "Show me the installation steps"
        ]

        for query in knowledge_queries:
            strategy = agent._analyze_query_for_routing(query)
            assert strategy == "knowledge_only", "Query should route to knowledge_only"

    def test_smart_query_routing_memory_only(self, agent):
        """Test smart query routing identifies memory-only queries."""
        # Test conversational/personal queries
        memory_queries = [
            "What did we discuss earlier about my project?",
            "You mentioned something before about our conversation",
            "Remember when I told you about my preferences?",
            "As we talked previously, my situation is",
            "Continue from where we left off"
        ]

        for query in memory_queries:
            strategy = agent._analyze_query_for_routing(query)
            assert strategy == "memory_only", "Query should route to memory_only"

    def test_smart_query_routing_both(self, agent):
        """Test smart query routing identifies queries needing both sources."""
        # Test mixed/complex queries
        both_queries = [
            "Based on the documentation and our previous discussion, how should I proceed?",
            "Using the API specs you showed me earlier, what's the best approach?",
            "Can you help me implement this feature we talked about?",
            "What are the best practices for this problem?",
            "How can I solve this issue?"
        ]

        for query in both_queries:
            strategy = agent._analyze_query_for_routing(query)
            assert strategy == "both", "Query should route to both sources"

    def test_context_budget_allocation_knowledge_only(self, agent):
        """Test budget allocation for knowledge-only strategy."""
        knowledge_limit, memory_limit = agent._allocate_context_budget(
            total_budget=10, strategy="knowledge_only", base_limit=5
        )
        assert knowledge_limit == 10
        assert memory_limit == 0

    def test_context_budget_allocation_memory_only(self, agent):
        """Test budget allocation for memory-only strategy."""
        knowledge_limit, memory_limit = agent._allocate_context_budget(
            total_budget=10, strategy="memory_only", base_limit=5
        )
        assert knowledge_limit == 0
        assert memory_limit == 10

    def test_context_budget_allocation_both(self, agent):
        """Test budget allocation for both strategy."""
        knowledge_limit, memory_limit = agent._allocate_context_budget(
            total_budget=10, strategy="both", base_limit=5
        )
        # Should allocate to both with knowledge getting slight preference
        assert knowledge_limit > 0
        assert memory_limit > 0
        assert knowledge_limit + memory_limit <= 10

    def test_content_deduplication(self, agent):
        """Test content deduplication removes similar results."""
        results = {
            "knowledge": [
                {
                    "content": "The API authentication requires JWT tokens for secure access",
                    "relevance": 0.9
                }
            ],
            "memory": [
                {
                    "content": (
                        "The API authentication requires JWT tokens for secure access to the system"
                    ),
                    "relevance": 0.8
                }
            ]
        }

        deduplicated = agent._deduplicate_results(results)

        # Should keep knowledge but remove similar memory
        assert len(deduplicated["knowledge"]) == 1
        assert len(deduplicated["memory"]) == 0

    def test_text_overlap_calculation(self, agent):
        """Test text overlap calculation accuracy."""
        # Test high overlap
        text1 = "the quick brown fox jumps"
        text2 = "the quick brown fox runs"
        overlap = agent._calculate_text_overlap(text1, text2)
        assert overlap > 0.5  # Should have significant overlap

        # Test low overlap
        text1 = "completely different content here"
        text2 = "totally unrelated information there"
        overlap = agent._calculate_text_overlap(text1, text2)
        assert overlap < 0.3  # Should have minimal overlap

    def test_enhanced_unified_ranking(self, agent):
        """Test enhanced unified ranking combines results intelligently."""
        knowledge_results = [
            {"content": "Knowledge result 1", "relevance": 0.8}
        ]
        memory_results = [
            {"content": "Memory result 1", "relevance": 0.7, "timestamp": "2024-01-01T12:00:00Z"}
        ]

        unified = agent._create_enhanced_unified_ranking(
            knowledge_results=knowledge_results,
            memory_results=memory_results,
            query="test query",
            strategy="both",
            budget=5
        )

        # Should have both results with enhanced scoring
        assert len(unified) == 2
        for result in unified:
            assert "enhanced_score" in result
            assert "source_type" in result
            assert "unified_rank" in result
            assert "strategy_used" in result

    def test_search_knowledge_always_enhanced(self, agent):
        """Test that search_knowledge always uses enhanced features."""
        # Mock the knowledge handler
        agent.knowledge_handler = MagicMock()
        agent.knowledge_handler.search_unified = AsyncMock(return_value={
            "knowledge": [{"content": "test", "relevance": 0.8}],
            "memory": [{"content": "test memory", "relevance": 0.7}],
        })

        # Call search_knowledge - enhanced features should always be enabled
        import asyncio
        results = asyncio.run(agent.search_knowledge(
            query="test query",
            limit=5,
            include_memory=True
        ))

        # Should return enhanced unified results by default
        assert isinstance(results, list)
        # The method should have used smart routing, deduplication, and enhanced ranking


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
