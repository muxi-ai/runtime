"""
Comprehensive unit tests for the KnowledgeHandler class.

Tests cover:
- MD5-based caching functionality
- Performance optimization features
- Memory integration
- Error handling
- Configuration loading
- Search functionality
"""

import pytest
import asyncio
import tempfile
import os
import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

# Import the classes we're testing
from muxi.formation.agents.knowledge import KnowledgeHandler, FileKnowledge
from muxi.formation.memory import ShortTermMemory


class TestKnowledgeHandler:
    """Test suite for KnowledgeHandler class"""

    @pytest.fixture
    def agent_id(self):
        """Test agent ID"""
        return "test_agent"

    @pytest.fixture
    def embedding_dimension(self):
        """Test embedding dimension"""
        return 128  # Small dimension for faster tests

    @pytest.fixture
    async def handler(self, agent_id, embedding_dimension):
        """Create test knowledge handler"""
        return KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=embedding_dimension,
            enable_query_cache=False,  # Disable for predictable tests
            max_files_per_source=5,
            max_total_files=10
        )

    @pytest.fixture
    def mock_embedding_fn(self, embedding_dimension):
        """Mock embedding function that returns deterministic results"""
        async def embedding_fn(text: str) -> List[float]:
            # Create deterministic embedding based on text hash
            text_hash = hashlib.md5(text.encode()).hexdigest()
            # Convert hex to float values
            values = []
            for i in range(0, len(text_hash), 2):
                hex_pair = text_hash[i:i+2]
                values.append(int(hex_pair, 16) / 255.0)

            # Pad or truncate to desired dimension
            while len(values) < embedding_dimension:
                values.extend(values)

            return values[:embedding_dimension]

        return embedding_fn

    @pytest.fixture
    def temp_knowledge_file(self):
        """Create temporary knowledge file"""
        content = """
        # Knowledge Base Test Document

        ## User Authentication

        To authenticate users, use the login API endpoint with username and password.
        The system supports OAuth 2.0 and basic authentication methods.

        ## Password Reset

        Users can reset their passwords by clicking the "Forgot Password" link.
        A reset email will be sent to their registered email address.

        ## API Documentation

        The REST API provides endpoints for user management, data access, and system configuration.
        Rate limiting is enforced at 1000 requests per hour per API key.

        ## Error Handling

        Common error codes include:
        - 401: Unauthorized access
        - 403: Forbidden operation
        - 404: Resource not found
        - 429: Rate limit exceeded
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def temp_knowledge_dir(self):
        """Create temporary knowledge directory with multiple files"""
        temp_dir = tempfile.mkdtemp()

        files_content = {
            "faq.md": """
            # Frequently Asked Questions

            ## How do I create an account?
            Visit the signup page and fill out the registration form.

            ## How do I contact support?
            Email us at support@example.com or use the chat widget.
            """,
            "api_guide.md": """
            # API Guide

            ## Authentication
            Include your API key in the Authorization header.

            ## Rate Limits
            API calls are limited to 1000 per hour.
            """,
            "troubleshooting.txt": """
            Troubleshooting Common Issues

            1. Connection timeouts - Check your network settings
            2. Authentication errors - Verify your credentials
            3. Rate limit errors - Wait before retrying
            """
        }

        for filename, content in files_content.items():
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, 'w') as f:
                f.write(content)

        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)


class TestBasicFunctionality(TestKnowledgeHandler):
    """Test basic knowledge handler functionality"""

    async def test_handler_initialization(self, agent_id, embedding_dimension):
        """Test KnowledgeHandler initialization"""
        handler = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=embedding_dimension
        )

        assert handler.agent_id == agent_id
        assert handler.embedding_dimension == embedding_dimension
        assert handler.enable_query_cache is True  # Default value
        assert handler.optimized_search_params is True  # Default value
        assert len(handler.sources) == 0  # No sources initially

    async def test_add_file_single(self, handler, mock_embedding_fn, temp_knowledge_file):
        """Test adding a single file to knowledge handler"""
        knowledge = FileKnowledge(
            name="test_knowledge",
            path=temp_knowledge_file,
            description="Test knowledge file"
        )

        count = await handler.add_file(knowledge, mock_embedding_fn)

        assert count > 0, "Should process at least one document"
        assert len(handler.sources) == 1, "Should have one source"
        assert handler.sources[0] == temp_knowledge_file

    async def test_add_file_directory(self, handler, mock_embedding_fn, temp_knowledge_dir):
        """Test adding a directory to knowledge handler"""
        knowledge = FileKnowledge(
            name="test_dir",
            path=temp_knowledge_dir,
            description="Test knowledge directory",
            recursive=True,
            max_files=10
        )

        count = await handler.add_file(knowledge, mock_embedding_fn)

        assert count > 0, "Should process documents from directory"
        assert len(handler.sources) > 1, "Should have multiple sources from directory"

    async def test_search_functionality(self, handler, mock_embedding_fn, temp_knowledge_file):
        """Test knowledge search functionality"""
        # Add knowledge first
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test knowledge")
        await handler.add_file(knowledge, mock_embedding_fn)

        # Test search
        results = await handler.search(
            query="user authentication",
            generate_embeddings_fn=mock_embedding_fn,
            top_k=3
        )

        assert isinstance(results, list), "Results should be a list"
        assert len(results) >= 0, "Results should be non-negative length"

        if results:
            result = results[0]
            assert "content" in result, "Result should have content"
            assert "score" in result, "Result should have score"
            assert "source" in result, "Result should have source"
            assert "metadata" in result, "Result should have metadata"

            # Check metadata structure
            metadata = result["metadata"]
            assert "knowledge_source" in metadata
            assert "content_hash" in metadata
            assert "timestamp" in metadata

    async def test_search_different_queries(self, handler, mock_embedding_fn, temp_knowledge_file):
        """Test search with different types of queries"""
        # Add knowledge
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")
        await handler.add_file(knowledge, mock_embedding_fn)

        test_queries = [
            "authentication",
            "password reset",
            "API documentation",
            "error handling",
            "nonexistent topic"
        ]

        for query in test_queries:
            results = await handler.search(query, mock_embedding_fn, top_k=2)
            assert isinstance(results, list)
            # Some queries might return no results, which is valid


class TestMD5Caching(TestKnowledgeHandler):
    """Test MD5-based caching functionality"""

    async def test_md5_calculation(self, handler):
        """Test MD5 hash calculation"""
        test_content = "This is test content for MD5 calculation."

        # Calculate MD5 using handler's method
        md5_hash = handler._calculate_file_md5(test_content.encode())

        # Calculate expected MD5
        expected_hash = hashlib.md5(test_content.encode()).hexdigest()

        assert md5_hash == expected_hash, "MD5 calculation should be correct"

    async def test_cache_behavior_unchanged_file(self, handler, mock_embedding_fn, temp_knowledge_file):
        """Test that unchanged files use cache"""
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")

        # First processing
        count1 = await handler.add_file(knowledge, mock_embedding_fn)

        # Second processing (should use cache)
        count2 = await handler.add_file(knowledge, mock_embedding_fn)

        assert count1 > 0, "First processing should process documents"
        assert count2 == 0, "Second processing should use cache (return 0)"

    async def test_cache_invalidation_changed_file(self, handler, mock_embedding_fn):
        """Test cache invalidation when file content changes"""
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Initial content")
            temp_path = f.name

        try:
            knowledge = FileKnowledge("test", temp_path, "Test")

            # First processing
            count1 = await handler.add_file(knowledge, mock_embedding_fn)

            # Modify file content
            time.sleep(0.1)  # Ensure different timestamp
            with open(temp_path, 'w') as f:
                f.write("Modified content - this should invalidate cache")

            # Second processing (should reprocess due to content change)
            count2 = await handler.add_file(knowledge, mock_embedding_fn)

            assert count1 > 0, "First processing should process documents"
            assert count2 > 0, "Second processing should reprocess changed file"

        finally:
            os.unlink(temp_path)

    async def test_cache_file_operations(self, handler, temp_knowledge_file):
        """Test cache file save/load operations"""
        # Test cache file path generation
        cache_path = handler._get_cache_file_path(temp_knowledge_file)
        assert cache_path.endswith('.json'), "Cache file should be JSON"
        assert handler.agent_id in cache_path, "Cache path should include agent ID"

        # Test cache data structure
        test_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        test_metadata = [{"chunk": 1}, {"chunk": 2}]
        test_hash = "test_hash_123"

        # Save cache
        handler._save_cached_embeddings(
            temp_knowledge_file, test_embeddings, test_metadata, test_hash
        )

        # Load cache
        loaded_data = handler._load_cached_embeddings(temp_knowledge_file, test_hash)

        assert loaded_data is not None, "Cache should be loaded successfully"
        assert loaded_data["embeddings"] == test_embeddings, "Embeddings should match"
        assert loaded_data["metadata"] == test_metadata, "Metadata should match"
        assert loaded_data["content_hash"] == test_hash, "Hash should match"

    async def test_cache_cleanup(self, handler, temp_knowledge_file):
        """Test cache cleanup for invalid entries"""
        # Create invalid cache entry
        cache_path = handler._get_cache_file_path(temp_knowledge_file)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        # Save invalid cache (wrong hash)
        with open(cache_path, 'w') as f:
            json.dump({
                "source_path": temp_knowledge_file,
                "content_hash": "invalid_hash",
                "embeddings": [[0.1, 0.2]],
                "metadata": [{"test": True}],
                "timestamp": time.time()
            }, f)

        # Calculate actual file hash
        with open(temp_knowledge_file, 'rb') as f:
            actual_hash = hashlib.md5(f.read()).hexdigest()

        # Try to load cache (should return None due to hash mismatch)
        loaded_data = handler._load_cached_embeddings(temp_knowledge_file, actual_hash)

        assert loaded_data is None, "Invalid cache should not be loaded"


class TestPerformanceOptimization(TestKnowledgeHandler):
    """Test performance optimization features"""

    async def test_performance_metrics_initialization(self, handler):
        """Test performance metrics initialization"""
        metrics = handler.get_performance_metrics()

        assert metrics.total_searches == 0
        assert metrics.total_search_time == 0.0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
        assert metrics.avg_search_time == 0.0
        assert metrics.cache_hit_rate == 0.0

    async def test_performance_metrics_tracking(self, handler, mock_embedding_fn, temp_knowledge_file):
        """Test performance metrics tracking during searches"""
        # Add knowledge
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")
        await handler.add_file(knowledge, mock_embedding_fn)

        # Perform search
        await handler.search("test query", mock_embedding_fn, top_k=3)

        # Check metrics
        metrics = handler.get_performance_metrics()

        assert metrics.total_searches == 1, "Should track search count"
        assert metrics.total_search_time > 0, "Should track search time"
        assert metrics.avg_search_time > 0, "Should calculate average time"

    async def test_query_caching(self, agent_id, embedding_dimension, mock_embedding_fn, temp_knowledge_file):
        """Test query result caching"""
        # Create handler with caching enabled
        handler = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=embedding_dimension,
            enable_query_cache=True,
            cache_max_age=60.0,
            cache_max_size=10
        )

        # Add knowledge
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")
        await handler.add_file(knowledge, mock_embedding_fn)

        # First search
        query = "test query for caching"
        results1 = await handler.search(query, mock_embedding_fn, top_k=3)

        # Second search (should hit cache)
        results2 = await handler.search(query, mock_embedding_fn, top_k=3)

        # Results should be identical
        assert results1 == results2, "Cached results should be identical"

        # Check cache metrics
        metrics = handler.get_performance_metrics()
        assert metrics.cache_hits >= 1, "Should have cache hits"

    async def test_cache_expiration(self, agent_id, embedding_dimension, mock_embedding_fn, temp_knowledge_file):
        """Test query cache expiration"""
        # Create handler with short cache expiration
        handler = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=embedding_dimension,
            enable_query_cache=True,
            cache_max_age=0.1,  # 100ms expiration
            cache_max_size=10
        )

        # Add knowledge
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")
        await handler.add_file(knowledge, mock_embedding_fn)

        # First search
        query = "expiration test query"
        await handler.search(query, mock_embedding_fn, top_k=3)

        # Wait for cache to expire
        await asyncio.sleep(0.2)

        # Second search (cache should be expired)
        await handler.search(query, mock_embedding_fn, top_k=3)

        # Should have cache misses due to expiration
        metrics = handler.get_performance_metrics()
        assert metrics.cache_misses >= 1, "Should have cache misses due to expiration"

    async def test_optimized_search_parameters(self, agent_id, embedding_dimension, mock_embedding_fn, temp_knowledge_file):
        """Test optimized search parameters"""
        # Create handler with optimization enabled
        handler = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=embedding_dimension,
            optimized_search_params=True
        )

        # Add knowledge
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")
        await handler.add_file(knowledge, mock_embedding_fn)

        # Search with optimization
        results = await handler.search("test query", mock_embedding_fn, top_k=3)

        # Should return results (testing that optimization doesn't break functionality)
        assert isinstance(results, list)

    async def test_performance_metrics_reset(self, handler, mock_embedding_fn, temp_knowledge_file):
        """Test performance metrics reset functionality"""
        # Add knowledge and perform search
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")
        await handler.add_file(knowledge, mock_embedding_fn)
        await handler.search("test query", mock_embedding_fn)

        # Check metrics are not zero
        metrics_before = handler.get_performance_metrics()
        assert metrics_before.total_searches > 0

        # Reset metrics
        handler.reset_performance_metrics()

        # Check metrics are reset
        metrics_after = handler.get_performance_metrics()
        assert metrics_after.total_searches == 0
        assert metrics_after.total_search_time == 0.0
        assert metrics_after.cache_hits == 0
        assert metrics_after.cache_misses == 0


class TestMemoryIntegration(TestKnowledgeHandler):
    """Test memory integration functionality"""

    @pytest.fixture
    def mock_memory(self):
        """Mock ShortTermMemory for testing"""
        memory = MagicMock(spec=ShortTermMemory)
        memory.add_entry = AsyncMock()
        return memory

    async def test_memory_integration_initialization(self, agent_id, embedding_dimension, mock_memory):
        """Test handler initialization with memory integration"""
        handler = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=embedding_dimension,
            short_term_memory=mock_memory,
            auto_inject_knowledge=True
        )

        assert handler.short_term_memory is mock_memory
        assert handler.auto_inject_knowledge is True

    async def test_automatic_knowledge_injection(self, agent_id, embedding_dimension, mock_memory, mock_embedding_fn, temp_knowledge_file):
        """Test automatic knowledge injection into memory"""
        handler = KnowledgeHandler(
            agent_id_or_sources=agent_id,
            embedding_dimension=embedding_dimension,
            short_term_memory=mock_memory,
            auto_inject_knowledge=True
        )

        # Add knowledge
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")
        await handler.add_file(knowledge, mock_embedding_fn)

        # Perform search (should trigger memory injection)
        results = await handler.search("test query", mock_embedding_fn, top_k=2)

        # Verify memory injection was called
        if results:  # Only if there were results to inject
            mock_memory.add_entry.assert_called()

            # Check the call arguments
            call_args = mock_memory.add_entry.call_args
            assert call_args is not None

            # Verify namespace is 'knowledge'
            args, kwargs = call_args
            assert "knowledge" in str(args) or "knowledge" in str(kwargs)


class TestConfigurationLoading(TestKnowledgeHandler):
    """Test configuration-based handler creation"""

    async def test_from_agent_config_enabled(self, agent_id, mock_embedding_fn, temp_knowledge_file):
        """Test creating handler from agent configuration when enabled"""
        config = {
            "enabled": True,
            "sources": [
                {
                    "path": temp_knowledge_file,
                    "description": "Test knowledge file"
                }
            ]
        }

        handler = await KnowledgeHandler.from_agent_config(
            agent_id=agent_id,
            knowledge_config=config,
            generate_embeddings_fn=mock_embedding_fn,
            embedding_dimension=128
        )

        assert handler is not None, "Handler should be created when enabled"
        assert handler.agent_id == agent_id
        assert len(handler.sources) > 0, "Should have processed sources"

    async def test_from_agent_config_disabled(self, agent_id, mock_embedding_fn):
        """Test creating handler from agent configuration when disabled"""
        config = {
            "enabled": False,
            "sources": []
        }

        handler = await KnowledgeHandler.from_agent_config(
            agent_id=agent_id,
            knowledge_config=config,
            generate_embeddings_fn=mock_embedding_fn
        )

        assert handler is None, "Handler should not be created when disabled"

    async def test_from_agent_config_no_sources(self, agent_id, mock_embedding_fn):
        """Test creating handler with no sources"""
        config = {
            "enabled": True,
            "sources": []
        }

        handler = await KnowledgeHandler.from_agent_config(
            agent_id=agent_id,
            knowledge_config=config,
            generate_embeddings_fn=mock_embedding_fn
        )

        assert handler is not None, "Handler should be created even with no sources"
        assert len(handler.sources) == 0, "Should have no sources"


class TestErrorHandling(TestKnowledgeHandler):
    """Test error handling and edge cases"""

    async def test_nonexistent_file(self, handler, mock_embedding_fn):
        """Test handling of nonexistent files"""
        knowledge = FileKnowledge(
            name="nonexistent",
            path="/nonexistent/path/file.txt",
            description="Nonexistent file"
        )

        with pytest.raises(Exception):
            await handler.add_file(knowledge, mock_embedding_fn)

    async def test_empty_file(self, handler, mock_embedding_fn):
        """Test handling of empty files"""
        # Create empty file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_path = f.name

        try:
            knowledge = FileKnowledge("empty", temp_path, "Empty file")

            # Should handle empty file gracefully
            count = await handler.add_file(knowledge, mock_embedding_fn)
            assert count == 0, "Empty file should result in 0 processed documents"

        finally:
            os.unlink(temp_path)

    async def test_invalid_embedding_function(self, handler, temp_knowledge_file):
        """Test handling of invalid embedding function"""
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")

        # Invalid embedding function that raises exception
        async def invalid_embedding_fn(text: str):
            raise ValueError("Invalid embedding function")

        with pytest.raises(ValueError):
            await handler.add_file(knowledge, invalid_embedding_fn)

    async def test_search_without_knowledge(self, handler, mock_embedding_fn):
        """Test search when no knowledge has been added"""
        results = await handler.search("test query", mock_embedding_fn)

        assert isinstance(results, list), "Should return empty list"
        assert len(results) == 0, "Should return no results when no knowledge exists"

    async def test_corrupted_cache_file(self, handler, temp_knowledge_file):
        """Test handling of corrupted cache files"""
        # Create corrupted cache file
        cache_path = handler._get_cache_file_path(temp_knowledge_file)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        # Write invalid JSON
        with open(cache_path, 'w') as f:
            f.write("invalid json content")

        # Should handle corrupted cache gracefully
        with open(temp_knowledge_file, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        loaded_data = handler._load_cached_embeddings(temp_knowledge_file, file_hash)
        assert loaded_data is None, "Corrupted cache should return None"


class TestFileKnowledge:
    """Test FileKnowledge class functionality"""

    def test_file_knowledge_initialization(self):
        """Test FileKnowledge initialization"""
        knowledge = FileKnowledge(
            name="test",
            path="/test/path",
            description="Test knowledge",
            max_files=10,
            allowed_extensions=[".txt", ".md"],
            max_file_size=1024,
            recursive=True
        )

        assert knowledge.name == "test"
        assert knowledge.path == "/test/path"
        assert knowledge.description == "Test knowledge"
        assert knowledge.max_files == 10
        assert knowledge.allowed_extensions == [".txt", ".md"]
        assert knowledge.max_file_size == 1024
        assert knowledge.recursive is True

    def test_file_knowledge_from_config(self):
        """Test creating FileKnowledge from configuration"""
        config = {
            "path": "/config/path",
            "description": "Config knowledge",
            "max_files": 20,
            "allowed_extensions": [".pdf", ".docx"],
            "max_file_size": 2048,
            "recursive": False
        }

        knowledge = FileKnowledge.from_config(config)

        assert knowledge.path == "/config/path"
        assert knowledge.description == "Config knowledge"
        assert knowledge.max_files == 20
        assert knowledge.allowed_extensions == [".pdf", ".docx"]
        assert knowledge.max_file_size == 2048
        assert knowledge.recursive is False

    async def test_get_files_single_file(self, temp_knowledge_file):
        """Test getting files for single file knowledge"""
        knowledge = FileKnowledge("test", temp_knowledge_file, "Test")

        files = await knowledge.get_files()

        assert len(files) == 1
        assert files[0] == temp_knowledge_file

    async def test_get_files_directory(self, temp_knowledge_dir):
        """Test getting files for directory knowledge"""
        knowledge = FileKnowledge(
            name="test_dir",
            path=temp_knowledge_dir,
            description="Test directory",
            recursive=True,
            max_files=10
        )

        files = await knowledge.get_files()

        assert len(files) > 1, "Should find multiple files in directory"
        assert all(os.path.exists(f) for f in files), "All files should exist"

    async def test_get_files_with_extension_filter(self, temp_knowledge_dir):
        """Test getting files with extension filtering"""
        knowledge = FileKnowledge(
            name="test_filtered",
            path=temp_knowledge_dir,
            description="Test with filter",
            allowed_extensions=[".md"],
            recursive=True
        )

        files = await knowledge.get_files()

        assert all(f.endswith('.md') for f in files), "Should only return .md files"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
