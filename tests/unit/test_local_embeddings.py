"""
Unit tests for local embedding fallback feature.

Tests the local_embeddings module which provides sentence-transformer based
embeddings as a fallback when no API-based embedding model is configured.

Note: These tests import the local_embeddings module directly to avoid
triggering the full muxi package import chain which may have environment
dependencies.
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import patch, MagicMock

# Add src to path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# Skip all tests if pydantic has version issues
def _check_pydantic():
    """Check if pydantic can be imported without errors."""
    try:
        from pydantic import BaseModel
        return True
    except (ImportError, SystemError):
        return False


PYDANTIC_OK = _check_pydantic()
skip_if_pydantic_broken = pytest.mark.skipif(
    not PYDANTIC_OK,
    reason="Pydantic version mismatch in environment"
)


class TestLocalEmbeddingModule:
    """Tests for the local_embeddings module functions."""

    @skip_if_pydantic_broken
    def test_get_local_embedding_dimension_default(self):
        """Test default dimension for local embeddings."""
        from muxi.services.memory.local_embeddings import (
            get_local_embedding_dimension,
            LOCAL_EMBEDDING_MODEL_NAME,
        )

        # Default model (all-MiniLM-L6-v2) should return 384
        dimension = get_local_embedding_dimension()
        assert dimension == 384

        # Same for explicit default model name
        dimension = get_local_embedding_dimension(LOCAL_EMBEDDING_MODEL_NAME)
        assert dimension == 384

    @skip_if_pydantic_broken
    def test_get_local_embedding_dimension_multilingual(self):
        """Test dimension for multilingual model."""
        from muxi.services.memory.local_embeddings import get_local_embedding_dimension

        # Multilingual model should also return 384
        dimension = get_local_embedding_dimension("paraphrase-multilingual-MiniLM-L12-v2")
        assert dimension == 384

    @skip_if_pydantic_broken
    def test_get_local_embedding_dimension_mpnet(self):
        """Test dimension for mpnet model."""
        from muxi.services.memory.local_embeddings import get_local_embedding_dimension

        # MPNet model should return 768
        dimension = get_local_embedding_dimension("all-mpnet-base-v2")
        assert dimension == 768

    @skip_if_pydantic_broken
    def test_get_local_embedding_dimension_unknown(self):
        """Test dimension for unknown model defaults to 384."""
        from muxi.services.memory.local_embeddings import get_local_embedding_dimension

        # Unknown model should default to 384
        dimension = get_local_embedding_dimension("unknown-model")
        assert dimension == 384

    @skip_if_pydantic_broken
    def test_is_local_embedding_available(self):
        """Test that sentence-transformers availability check works."""
        from muxi.services.memory.local_embeddings import is_local_embedding_available

        # sentence-transformers should be installed per requirements.txt
        assert is_local_embedding_available() is True

    @skip_if_pydantic_broken
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    def test_get_local_embedding(self):
        """Test that local embedding generation works."""
        from muxi.services.memory.local_embeddings import (
            get_local_embedding,
            get_local_embedding_dimension,
            clear_local_embedding_cache,
        )

        # Clear cache to start fresh
        clear_local_embedding_cache()

        # Generate embedding
        text = "Hello, world!"
        embedding = get_local_embedding(text)

        # Check that we got a list of floats with correct dimension
        assert isinstance(embedding, list)
        assert len(embedding) == get_local_embedding_dimension()
        assert all(isinstance(x, float) for x in embedding)

    @skip_if_pydantic_broken
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    def test_get_local_embedding_consistency(self):
        """Test that same text produces same embedding."""
        from muxi.services.memory.local_embeddings import get_local_embedding

        text = "Test sentence for consistency check"
        embedding1 = get_local_embedding(text)
        embedding2 = get_local_embedding(text)

        # Embeddings should be identical for same input
        assert embedding1 == embedding2

    @skip_if_pydantic_broken
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    def test_get_local_embedding_different_texts(self):
        """Test that different texts produce different embeddings."""
        from muxi.services.memory.local_embeddings import get_local_embedding

        text1 = "I love programming"
        text2 = "The weather is nice today"

        embedding1 = get_local_embedding(text1)
        embedding2 = get_local_embedding(text2)

        # Embeddings should be different for different inputs
        assert embedding1 != embedding2

    @skip_if_pydantic_broken
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    async def test_get_local_embedding_async(self):
        """Test async version of local embedding generation."""
        from muxi.services.memory.local_embeddings import (
            get_local_embedding_async,
            get_local_embedding_dimension,
        )

        text = "Async test sentence"
        embedding = await get_local_embedding_async(text)

        # Check that we got a list of floats with correct dimension
        assert isinstance(embedding, list)
        assert len(embedding) == get_local_embedding_dimension()
        assert all(isinstance(x, float) for x in embedding)

    @skip_if_pydantic_broken
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    def test_clear_local_embedding_cache(self):
        """Test that cache clearing works."""
        from muxi.services.memory.local_embeddings import (
            get_local_embedding,
            clear_local_embedding_cache,
        )

        # Generate an embedding to ensure model is loaded
        get_local_embedding("Test")

        # Clear cache
        clear_local_embedding_cache()

        # Import module-level variables to check they were reset
        import muxi.services.memory.local_embeddings as le_module

        assert le_module._model is None
        assert le_module._model_name is None
        assert le_module._initialization_logged is False


class TestLocalEmbeddingProvider:
    """Tests for the LocalEmbeddingProvider class."""

    @skip_if_pydantic_broken
    def test_provider_initialization(self):
        """Test LocalEmbeddingProvider initialization."""
        from muxi.services.memory.local_embeddings import (
            LocalEmbeddingProvider,
            LOCAL_EMBEDDING_MODEL_NAME,
        )

        provider = LocalEmbeddingProvider()

        assert provider.model_name == LOCAL_EMBEDDING_MODEL_NAME
        assert provider.dimension == 384

    @skip_if_pydantic_broken
    def test_provider_custom_model(self):
        """Test LocalEmbeddingProvider with custom model."""
        from muxi.services.memory.local_embeddings import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider(model_name="all-mpnet-base-v2")

        assert provider.model_name == "all-mpnet-base-v2"
        assert provider.dimension == 768

    @skip_if_pydantic_broken
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    async def test_provider_embed_async(self):
        """Test async embedding generation via provider."""
        from muxi.services.memory.local_embeddings import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider()
        embedding = await provider.embed("Test sentence")

        assert isinstance(embedding, list)
        assert len(embedding) == provider.dimension
        assert all(isinstance(x, float) for x in embedding)

    @skip_if_pydantic_broken
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    def test_provider_embed_sync(self):
        """Test sync embedding generation via provider."""
        from muxi.services.memory.local_embeddings import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider()
        embedding = provider.embed_sync("Test sentence")

        assert isinstance(embedding, list)
        assert len(embedding) == provider.dimension
        assert all(isinstance(x, float) for x in embedding)


class TestMemoryLocalEmbeddingFallback:
    """Tests for local embedding fallback in memory services."""

    @skip_if_pydantic_broken
    def test_long_term_memory_uses_local_embeddings_when_no_model(self):
        """Test that LongTermMemory uses local embeddings when no model configured."""
        from muxi.services.memory.long_term import LongTermMemory
        from muxi.services.memory.local_embeddings import LocalEmbeddingProvider

        # Mock database manager
        mock_db_manager = MagicMock()
        mock_db_manager.database_type = "sqlite"  # Use SQLite to avoid pgvector setup

        # Create LongTermMemory without embedding model
        memory = LongTermMemory(
            db_manager=mock_db_manager,
            formation_id="test-formation",
            embedding_model=None,  # No model configured
        )

        # Check that local embeddings are configured
        assert memory._use_local_embeddings is True
        assert memory.dimension == 384  # Local model dimension

        # Check that embedding_model property returns LocalEmbeddingProvider
        model = memory.embedding_model
        assert isinstance(model, LocalEmbeddingProvider)

    @skip_if_pydantic_broken
    def test_long_term_memory_uses_api_model_when_configured(self):
        """Test that LongTermMemory uses API model when configured."""
        from muxi.services.memory.long_term import LongTermMemory

        # Mock database manager
        mock_db_manager = MagicMock()
        mock_db_manager.database_type = "sqlite"

        # Create LongTermMemory with embedding model name
        memory = LongTermMemory(
            db_manager=mock_db_manager,
            formation_id="test-formation",
            embedding_model="openai/text-embedding-3-small",
        )

        # Check that local embeddings are NOT used
        assert memory._use_local_embeddings is False
        assert memory.dimension == 1536  # Default OpenAI dimension

    @skip_if_pydantic_broken
    def test_working_memory_uses_local_embeddings_when_no_model(self):
        """Test that WorkingMemory uses local embeddings when no model configured."""
        from muxi.services.memory.working import WorkingMemory
        from muxi.services.memory.local_embeddings import LocalEmbeddingProvider

        # Create WorkingMemory without embedding model
        memory = WorkingMemory(
            formation_id="test-formation",
            model=None,  # No model configured
        )

        # Check that local embeddings are configured
        assert memory._use_local_embeddings is True
        assert memory.dimension == 384  # Local model dimension

        # Check that model property returns LocalEmbeddingProvider
        model = memory.model
        assert isinstance(model, LocalEmbeddingProvider)

    @skip_if_pydantic_broken
    def test_working_memory_uses_api_model_when_configured(self):
        """Test that WorkingMemory uses API model when configured."""
        from muxi.services.memory.working import WorkingMemory

        # Create a mock LLM model
        mock_llm = MagicMock()

        # Create WorkingMemory with embedding model
        memory = WorkingMemory(
            formation_id="test-formation",
            model=mock_llm,
        )

        # Check that local embeddings are NOT used
        assert memory._use_local_embeddings is False
        assert memory.dimension == 1536  # Default OpenAI dimension

        # Check that model property returns the provided model
        assert memory.model is mock_llm


class TestSemanticQuality:
    """Tests for semantic quality of local embeddings."""

    @skip_if_pydantic_broken
    @pytest.mark.skipif(
        not _check_pydantic(),
        reason="sentence-transformers may not be available"
    )
    def test_similar_sentences_have_high_similarity(self):
        """Test that semantically similar sentences have high cosine similarity."""
        from muxi.services.memory.local_embeddings import get_local_embedding
        import math

        # Similar sentences
        sentence1 = "The quick brown fox jumps over the lazy dog"
        sentence2 = "A fast brown fox leaps over a sleepy dog"

        # Different sentence
        sentence3 = "Machine learning is transforming the tech industry"

        emb1 = get_local_embedding(sentence1)
        emb2 = get_local_embedding(sentence2)
        emb3 = get_local_embedding(sentence3)

        # Calculate cosine similarity
        def cosine_similarity(a, b):
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            return dot_product / (norm_a * norm_b)

        sim_12 = cosine_similarity(emb1, emb2)  # Similar sentences
        sim_13 = cosine_similarity(emb1, emb3)  # Different sentences

        # Similar sentences should have higher similarity
        assert sim_12 > sim_13
        # Similar sentences should have high similarity (> 0.7)
        assert sim_12 > 0.7
