"""
Integration tests for the MUXI Domain Knowledge System.

Tests cover:
- End-to-end workflows
- Formation loading with knowledge
- Memory integration
- Performance under load
- Real-world scenarios
"""

import pytest
import asyncio
import tempfile
import os
import time
from typing import List

from muxi.runtime.formation.agents.knowledge import KnowledgeHandler, FileKnowledge


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows"""

    @pytest.fixture
    def sample_knowledge_files(self):
        """Create sample knowledge files for testing"""
        temp_dir = tempfile.mkdtemp()

        files_content = {
            "user_guide.md": """
            # User Guide

            ## Getting Started
            Welcome to our platform! This guide will help you get started.

            ## Account Creation
            1. Visit the signup page
            2. Fill out the registration form
            3. Verify your email address
            4. Log in with your credentials

            ## Basic Features
            - Dashboard overview
            - Profile management
            - Settings configuration
            """,
            "api_documentation.md": """
            # API Documentation

            ## Authentication
            All API requests require authentication using API keys.
            Include your API key in the Authorization header.

            ## Endpoints

            ### Users
            - GET /api/users - List all users
            - POST /api/users - Create new user
            - PUT /api/users/{id} - Update user
            - DELETE /api/users/{id} - Delete user

            ### Rate Limiting
            API calls are limited to 1000 requests per hour per API key.
            """,
            "troubleshooting.txt": """
            Troubleshooting Guide

            Common Issues and Solutions:

            1. Login Problems
               - Check username and password
               - Clear browser cache
               - Reset password if needed

            2. API Errors
               - Verify API key is valid
               - Check request format
               - Review rate limits

            3. Performance Issues
               - Check network connection
               - Monitor system resources
               - Contact support if persistent
            """
        }

        file_paths = []
        for filename, content in files_content.items():
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, 'w') as f:
                f.write(content)
            file_paths.append(file_path)

        yield temp_dir, file_paths

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_embedding_fn(self):
        """Mock embedding function for testing"""
        async def embedding_fn(text: str) -> List[float]:
            # Simple hash-based embedding for testing
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()
            # Convert to float values
            values = []
            for i in range(0, min(len(text_hash), 32), 2):
                hex_pair = text_hash[i:i+2]
                values.append(int(hex_pair, 16) / 255.0)

            # Pad to 128 dimensions
            while len(values) < 128:
                values.extend(values)

            return values[:128]

        return embedding_fn

    async def test_complete_knowledge_workflow(self, sample_knowledge_files, mock_embedding_fn):
        """Test complete workflow from setup to search"""
        temp_dir, file_paths = sample_knowledge_files

        # 1. Initialize knowledge handler
        handler = KnowledgeHandler(
            agent_id_or_sources="integration_test_agent",
            embedding_dimension=128,
            enable_query_cache=True,
            optimized_search_params=True
        )

        # 2. Add knowledge sources
        knowledge_sources = [
            FileKnowledge("user_guide", file_paths[0], "User guide documentation"),
            FileKnowledge("api_docs", file_paths[1], "API documentation"),
            FileKnowledge("troubleshooting", file_paths[2], "Troubleshooting guide")
        ]

        total_processed = 0
        for source in knowledge_sources:
            count = await handler.add_file(source, mock_embedding_fn)
            total_processed += count
            print(f"Processed {source.name}: {count} documents")

        assert total_processed > 0, "Should process documents from all sources"
        assert len(handler.sources) == len(knowledge_sources), "Should have all sources registered"

        # 3. Test various search queries
        test_queries = [
            ("How do I create an account?", "user_guide"),
            ("What are the API endpoints?", "api_docs"),
            ("I'm having login problems", "troubleshooting"),
            ("API rate limiting", "api_docs"),
            ("password reset", "troubleshooting")
        ]

        for query, expected_source_type in test_queries:
            results = await handler.search(query, mock_embedding_fn, top_k=3)

            assert isinstance(results, list), f"Results should be list for query: {query}"

            if results:
                # Check result structure
                result = results[0]
                assert "content" in result
                assert "score" in result
                assert "source" in result
                assert "metadata" in result

                print(f"Query: '{query}' -> {len(results)} results")

        # 4. Test performance metrics
        metrics = handler.get_performance_metrics()
        assert metrics.total_searches > 0, "Should have recorded searches"
        assert metrics.avg_search_time >= 0, "Should have valid average search time"

        print(f"Performance: {metrics.total_searches} searches, avg {metrics.avg_search_time:.3f}s")

    async def test_configuration_based_workflow(self, sample_knowledge_files, mock_embedding_fn):
        """Test workflow using YAML configuration"""
        temp_dir, file_paths = sample_knowledge_files

        # 1. Create configuration
        config = {
            "enabled": True,
            "sources": [
                {
                    "path": file_paths[0],
                    "description": "User guide"
                },
                {
                    "path": file_paths[1],
                    "description": "API documentation"
                }
            ]
        }

        # 2. Create handler from configuration
        handler = await KnowledgeHandler.from_agent_config(
            agent_id="config_test_agent",
            knowledge_config=config,
            generate_embeddings_fn=mock_embedding_fn,
            embedding_dimension=128
        )

        assert handler is not None, "Handler should be created from config"
        assert len(handler.sources) > 0, "Should have processed sources from config"

        # 3. Test search functionality
        results = await handler.search("API authentication", mock_embedding_fn)
        assert isinstance(results, list), "Should return search results"

        print("Configuration-based workflow completed successfully")


class TestFormationLoading:
    """Test knowledge system integration with formation loading"""

    @pytest.fixture
    def agent_config_yaml(self, sample_knowledge_files):
        """Create agent configuration YAML"""
        temp_dir, file_paths = sample_knowledge_files

        config_content = f"""
schema: "1.0.0"
agent_id: formation_test_agent
description: "Test agent with knowledge integration"
system_message: "You are a helpful assistant with access to documentation."

knowledge:
  enabled: true
  sources:
    - path: "{file_paths[0]}"
      description: "User guide documentation"
    - path: "{file_paths[1]}"
      description: "API documentation"
      max_file_size: 1048576
    - path: "{temp_dir}"
      description: "All documentation"
      recursive: true
      max_files: 10
      allowed_extensions: [".md", ".txt"]
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            config_path = f.name

        yield config_path

        # Cleanup
        os.unlink(config_path)

    async def test_load_agent_configuration(self, sample_knowledge_files, mock_embedding_fn):
        """Test loading agent with knowledge from configuration"""
        temp_dir, file_paths = sample_knowledge_files

        # Create configuration
        config = {
            "enabled": True,
            "sources": [
                {"path": file_paths[0], "description": "User guide"},
                {"path": file_paths[1], "description": "API docs"}
            ]
        }

        # Create handler from configuration
        handler = await KnowledgeHandler.from_agent_config(
            agent_id="formation_test_agent",
            knowledge_config=config,
            generate_embeddings_fn=mock_embedding_fn,
            embedding_dimension=128
        )

        assert handler is not None, "Handler should be created from config"
        assert len(handler.sources) > 0, "Should have loaded knowledge sources"

        # Test functionality
        results = await handler.search("user guide", mock_embedding_fn)
        assert isinstance(results, list), "Should return search results"

        print(f"Successfully loaded agent with {len(handler.sources)} sources")


class TestPerformanceUnderLoad:
    """Test knowledge system performance under load"""

    @pytest.fixture
    def large_knowledge_base(self):
        """Create larger knowledge base for performance testing"""
        temp_dir = tempfile.mkdtemp()

        # Generate multiple files with substantial content
        for i in range(5):
            content = f"""
            # Document {i}

            This is document number {i} in our knowledge base.
            It contains various information about topic {i}.

            ## Section A
            Content for section A in document {i}.
            This section discusses important concepts related to topic {i}.

            ## Section B
            Content for section B in document {i}.
            This section provides detailed examples and use cases.

            The document concludes with a summary of key points for topic {i}.
            """

            file_path = os.path.join(temp_dir, f"doc_{i}.md")
            with open(file_path, 'w') as f:
                f.write(content)

        yield temp_dir

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_embedding_fn(self):
        """Mock embedding function for performance testing"""
        async def embedding_fn(text: str) -> List[float]:
            # Simulate some processing time
            await asyncio.sleep(0.01)  # 10ms delay

            # Generate deterministic embedding
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()
            values = []
            for i in range(0, min(len(text_hash), 32), 2):
                hex_pair = text_hash[i:i+2]
                values.append(int(hex_pair, 16) / 255.0)

            while len(values) < 256:
                values.extend(values)

            return values[:256]

        return embedding_fn

    async def test_search_performance(self, large_knowledge_base, mock_embedding_fn):
        """Test search performance with larger knowledge base"""
        # Initialize handler
        handler = KnowledgeHandler(
            agent_id_or_sources="search_perf_agent",
            embedding_dimension=256,
            enable_query_cache=True,
            optimized_search_params=True
        )

        # Add knowledge
        knowledge = FileKnowledge("large_kb", large_knowledge_base, "Large KB", recursive=True)
        await handler.add_file(knowledge, mock_embedding_fn)

        # Test multiple searches
        test_queries = [
            "document information",
            "section content",
            "advanced topics",
            "best practices",
            "key points"
        ]

        search_times = []

        for query in test_queries:
            start_time = time.time()

            results = await handler.search(query, mock_embedding_fn, top_k=5)

            search_time = time.time() - start_time
            search_times.append(search_time)

            assert isinstance(results, list), f"Should return results for query: {query}"

        # Performance assertions
        avg_search_time = sum(search_times) / len(search_times)
        max_search_time = max(search_times)

        assert avg_search_time < 2.0, \
            f"Average search time should be < 2s, got {avg_search_time:.3f}s"
        assert max_search_time < 5.0, \
            f"Max search time should be < 5s, got {max_search_time:.3f}s"

        # Test cache performance
        metrics = handler.get_performance_metrics()
        print(f"Search performance: avg {avg_search_time:.3f}s, cache hit rate {metrics.cache_hit_rate:.2%}")


class TestRealWorldScenarios:
    """Test real-world usage scenarios"""

    @pytest.fixture
    def realistic_knowledge_base(self):
        """Create realistic knowledge base with various file types and content"""
        temp_dir = tempfile.mkdtemp()

        files_content = {
            "README.md": """
            # Project Documentation

            Welcome to our project! This documentation will help you understand and use our system effectively.

            ## Quick Start
            1. Install dependencies
            2. Configure environment
            3. Run the application

            ## Features
            - User management
            - API access
            - Real-time notifications
            - Data analytics
            """,
            "api_reference.md": """
            # API Reference

            ## Authentication
            All API requests require authentication using Bearer tokens.

            ```
            Authorization: Bearer your-token-here
            ```

            ## Endpoints

            ### Users API
            - `GET /api/v1/users` - List users
            - `POST /api/v1/users` - Create user
            - `GET /api/v1/users/{id}` - Get user details

            ## Rate Limiting
            - 1000 requests per hour for authenticated users
            - 100 requests per hour for unauthenticated requests

            ## Error Codes
            - 400: Bad Request
            - 401: Unauthorized
            - 403: Forbidden
            - 404: Not Found
            - 429: Too Many Requests
            """,
            "faq.txt": """
            Frequently Asked Questions

            Q: How do I reset my password?
            A: Click the "Forgot Password" link on the login page and follow the instructions.

            Q: What browsers are supported?
            A: We support Chrome, Firefox, Safari, and Edge (latest versions).

            Q: How do I contact support?
            A: Email support@example.com or use the chat widget in the application.

            Q: What are the system requirements?
            A: Minimum 4GB RAM, modern web browser, stable internet connection.
            """
        }

        file_paths = []
        for filename, content in files_content.items():
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, 'w') as f:
                f.write(content)
            file_paths.append(file_path)

        yield temp_dir, file_paths

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_embedding_fn(self):
        """Realistic mock embedding function"""
        async def embedding_fn(text: str) -> List[float]:
            # Simulate realistic embedding generation time
            await asyncio.sleep(0.02)  # 20ms delay

            # Generate more realistic embeddings
            import hashlib
            import math

            # Create multiple hash sources for better distribution
            hash1 = hashlib.md5(text.encode()).hexdigest()
            hash2 = hashlib.sha1(text.encode()).hexdigest()

            values = []
            for i in range(384):  # 384-dimensional embeddings
                # Use different parts of hashes for variety
                if i < 128:
                    source = hash1[i % len(hash1)]
                else:
                    source = hash2[i % len(hash2)]

                # Convert to float with some mathematical transformation
                val = (ord(source) / 255.0 - 0.5) * 2  # Range: -1 to 1
                val = math.tanh(val)  # Apply tanh for more realistic distribution
                values.append(val)

            return values

        return embedding_fn

    async def test_customer_support_scenario(self, realistic_knowledge_base, mock_embedding_fn):
        """Test customer support agent scenario"""
        temp_dir, file_paths = realistic_knowledge_base

        # Initialize support agent knowledge
        handler = KnowledgeHandler(
            agent_id_or_sources="support_agent",
            embedding_dimension=384,
            enable_query_cache=True,
            optimized_search_params=True,
            cache_max_age=300.0,  # 5 minutes
            cache_max_size=100
        )

        # Add knowledge sources
        knowledge_sources = [
            FileKnowledge("documentation", file_paths[0], "Project documentation"),
            FileKnowledge("api_reference", file_paths[1], "API reference guide"),
            FileKnowledge("faq", file_paths[2], "Frequently asked questions")
        ]

        for source in knowledge_sources:
            await handler.add_file(source, mock_embedding_fn)

        # Simulate customer support queries
        support_queries = [
            "How do I reset my password?",
            "What are the API rate limits?",
            "What browsers do you support?",
            "What are the system requirements?",
            "How do I contact support?"
        ]

        successful_queries = 0
        total_response_time = 0

        for query in support_queries:
            start_time = time.time()

            try:
                results = await handler.search(query, mock_embedding_fn, top_k=3)
                response_time = time.time() - start_time
                total_response_time += response_time

                if results:
                    successful_queries += 1

                    # Verify result quality
                    top_result = results[0]
                    assert "content" in top_result
                    assert len(top_result["content"]) > 0
                    assert "score" in top_result
                    assert top_result["score"] > 0

                    print(f"Query: '{query}' -> {len(results)} results in {response_time:.3f}s")

            except Exception as e:
                print(f"Query failed: '{query}' - {e}")

        # Performance assertions for customer support scenario
        avg_response_time = total_response_time / len(support_queries)
        success_rate = successful_queries / len(support_queries)

        assert success_rate >= 0.6, \
            f"Success rate should be >= 60%, got {success_rate:.2%}"
        assert avg_response_time < 1.0, \
            f"Average response time should be < 1.0s, got {avg_response_time:.3f}s"

        # Check cache performance
        metrics = handler.get_performance_metrics()
        print(f"Support scenario: {success_rate:.1%} success rate, {avg_response_time:.3f}s avg response time")
        print(f"Cache performance: {metrics.cache_hit_rate:.1%} hit rate")


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-s"])
