"""
Test Task 4.1: MD5-Based Cache Enhancement

This test verifies that the knowledge system uses MD5 hashing for cache invalidation
instead of modification time, providing more reliable caching behavior.
"""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, patch
from muxi.formation.agents.knowledge.handler import KnowledgeHandler
from muxi.formation.agents.knowledge.base import FileKnowledge


class TestTask41MD5Caching:
    """Test MD5-based caching implementation for Task 4.1."""

    @pytest.fixture
    def mock_embedding_fn(self):
        """Create a mock embedding function."""
        async def mock_fn(text):
            if isinstance(text, list):
                return [[0.1] * 1536 for _ in text]
            return [0.1] * 1536
        return mock_fn

    @pytest.fixture
    def temp_knowledge_file(self):
        """Create a temporary knowledge file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Initial content for testing MD5 caching.")
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_calculate_file_md5(self, temp_knowledge_file):
        """Test MD5 hash calculation for files."""
        handler = KnowledgeHandler("test_agent")

        # Calculate MD5 hash
        md5_hash = handler._calculate_file_md5(temp_knowledge_file)

        # Verify hash is generated
        assert md5_hash != ""
        assert len(md5_hash) == 32  # MD5 hash length
        assert all(c in '0123456789abcdef' for c in md5_hash)

    def test_md5_hash_consistency(self, temp_knowledge_file):
        """Test that MD5 hash is consistent for same content."""
        handler = KnowledgeHandler("test_agent")

        # Calculate hash twice
        hash1 = handler._calculate_file_md5(temp_knowledge_file)
        hash2 = handler._calculate_file_md5(temp_knowledge_file)

        # Hashes should be identical
        assert hash1 == hash2

    def test_md5_hash_changes_with_content(self, temp_knowledge_file):
        """Test that MD5 hash changes when file content changes."""
        handler = KnowledgeHandler("test_agent")

        # Calculate initial hash
        initial_hash = handler._calculate_file_md5(temp_knowledge_file)

        # Modify file content
        with open(temp_knowledge_file, 'w') as f:
            f.write("Modified content for testing MD5 caching.")

        # Calculate new hash
        new_hash = handler._calculate_file_md5(temp_knowledge_file)

        # Hashes should be different
        assert initial_hash != new_hash

    def test_md5_hash_unchanged_with_timestamp_modification(self, temp_knowledge_file):
        """Test that MD5 hash remains same when only timestamp changes."""
        handler = KnowledgeHandler("test_agent")

        # Calculate initial hash
        initial_hash = handler._calculate_file_md5(temp_knowledge_file)

        # Modify only the file timestamp (touch the file)
        import time
        time.sleep(0.1)  # Ensure timestamp difference
        os.utime(temp_knowledge_file, None)  # Update access and modification time

        # Calculate hash after timestamp change
        new_hash = handler._calculate_file_md5(temp_knowledge_file)

        # Hash should remain the same (content hasn't changed)
        assert initial_hash == new_hash

    def test_md5_hash_nonexistent_file(self):
        """Test MD5 hash calculation for non-existent file."""
        handler = KnowledgeHandler("test_agent")

        # Try to calculate hash for non-existent file
        md5_hash = handler._calculate_file_md5("/nonexistent/file.txt")

        # Should return empty string
        assert md5_hash == ""

    @patch('muxi.formation.agents.knowledge.handler.DocumentSemanticIndex')
    @patch('muxi.formation.agents.knowledge.handler.DocumentChunkManager')
    async def test_md5_based_cache_behavior(
        self, mock_chunk_manager, mock_semantic_index, temp_knowledge_file, mock_embedding_fn
    ):
        """Test that files are cached based on MD5 hash, not modification time."""
        # Setup mocks
        mock_semantic_index_instance = AsyncMock()
        mock_semantic_index.return_value = mock_semantic_index_instance

        mock_chunk_manager_instance = AsyncMock()
        mock_chunk_manager.return_value = mock_chunk_manager_instance

        # Mock existing document check - initially no documents
        mock_semantic_index_instance.get_documents_by_metadata.return_value = []

        # Create handler
        handler = KnowledgeHandler("test_agent")
        handler.semantic_index = mock_semantic_index_instance
        handler.chunk_manager = mock_chunk_manager_instance

        # Create knowledge source
        knowledge_source = FileKnowledge(
            path=temp_knowledge_file,
            description="Test file for MD5 caching"
        )

        # First call - should process file
        await handler.add_file(knowledge_source, mock_embedding_fn)

        # Verify MD5 hash was used in metadata filter
        call_args = mock_semantic_index_instance.get_documents_by_metadata.call_args
        metadata_filter = call_args[1]['metadata_filter']

        assert 'content_hash' in metadata_filter
        assert 'source' in metadata_filter
        assert metadata_filter['source'] == temp_knowledge_file

        # Store the hash for comparison
        first_hash = metadata_filter['content_hash']
        assert len(first_hash) == 32  # MD5 hash length

        # Reset mock for second call
        mock_semantic_index_instance.reset_mock()

        # Modify file timestamp but not content
        import time
        time.sleep(0.1)
        os.utime(temp_knowledge_file, None)

        # Mock that document exists with same hash (simulating cache hit)
        mock_semantic_index_instance.get_documents_by_metadata.return_value = [
            {"id": "test_doc", "content": "existing"}
        ]

        # Second call - should find cached version
        result2 = await handler.add_file(knowledge_source, mock_embedding_fn)

        # Verify same hash was used (content unchanged)
        call_args = mock_semantic_index_instance.get_documents_by_metadata.call_args
        metadata_filter = call_args[1]['metadata_filter']
        second_hash = metadata_filter['content_hash']

        assert first_hash == second_hash
        assert result2 == 0  # Should return 0 (cached, not reprocessed)

    def test_md5_integration_with_file_knowledge(self, temp_knowledge_file):
        """Test MD5 caching integration with FileKnowledge processing."""
        handler = KnowledgeHandler("test_agent")

        # Test that MD5 calculation works with FileKnowledge
        knowledge_source = FileKnowledge(
            path=temp_knowledge_file,
            description="Test file for MD5 integration"
        )

        # Calculate MD5 directly
        md5_hash = handler._calculate_file_md5(knowledge_source.path)

        # Verify hash is valid
        assert md5_hash != ""
        assert len(md5_hash) == 32

        # Verify hash is consistent
        md5_hash2 = handler._calculate_file_md5(knowledge_source.path)
        assert md5_hash == md5_hash2
