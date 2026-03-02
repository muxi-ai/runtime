"""Unit tests for dynamic memory model factory and dimension resolution."""


class TestMemoryModelFactory:
    """Tests for get_memory_model() factory function."""

    def test_creates_correct_tablename(self):
        from muxi.runtime.services.memory.long_term import get_memory_model

        m384 = get_memory_model(384)
        m768 = get_memory_model(768)
        m1536 = get_memory_model(1536)
        m2056 = get_memory_model(2056)

        assert m384.__tablename__ == "memories_384"
        assert m768.__tablename__ == "memories_768"
        assert m1536.__tablename__ == "memories_1536"
        assert m2056.__tablename__ == "memories_2056"

    def test_caches_model_instances(self):
        from muxi.runtime.services.memory.long_term import get_memory_model

        first = get_memory_model(384)
        second = get_memory_model(384)
        assert first is second

    def test_backwards_compat_alias(self):
        from muxi.runtime.services.memory.long_term import Memory, get_memory_model

        assert Memory is get_memory_model(1536)
        assert Memory.__tablename__ == "memories_1536"

    def test_model_has_correct_columns(self):
        from muxi.runtime.services.memory.long_term import get_memory_model

        model = get_memory_model(384)
        columns = {c.name for c in model.__table__.columns}
        assert columns == {
            "id",
            "user_id",
            "embedding",
            "text",
            "meta_data",
            "created_at",
            "updated_at",
            "collection",
        }


class TestLocalModelResolution:
    """Tests for local/ prefix model name resolution."""

    def test_is_local_model(self):
        from muxi.runtime.services.memory.local_embeddings import is_local_model

        assert is_local_model("local/all-MiniLM-L6-v2")
        assert is_local_model("local/all-mpnet-base-v2")
        assert is_local_model("all-MiniLM-L6-v2")  # bare name in registry
        assert not is_local_model("openai/text-embedding-3-small")
        assert not is_local_model("anthropic/some-model")

    def test_resolve_local_model_name(self):
        from muxi.runtime.services.memory.local_embeddings import resolve_local_model_name

        assert resolve_local_model_name("local/all-mpnet-base-v2") == "all-mpnet-base-v2"
        assert resolve_local_model_name("all-MiniLM-L6-v2") == "all-MiniLM-L6-v2"

    def test_resolve_embedding_dimension_local(self):
        from muxi.runtime.services.memory.local_embeddings import resolve_embedding_dimension

        assert resolve_embedding_dimension("local/all-MiniLM-L6-v2") == 384
        assert resolve_embedding_dimension("local/all-mpnet-base-v2") == 768
        assert resolve_embedding_dimension("local/paraphrase-multilingual-MiniLM-L12-v2") == 384

    def test_resolve_embedding_dimension_api(self):
        from muxi.runtime.services.memory.local_embeddings import resolve_embedding_dimension

        assert resolve_embedding_dimension("openai/text-embedding-3-small") == 1536
        assert resolve_embedding_dimension("openai/text-embedding-3-large") == 3072
        assert resolve_embedding_dimension("openai/text-embedding-ada-002") == 1536

    def test_resolve_embedding_dimension_unknown_defaults_1536(self):
        from muxi.runtime.services.memory.local_embeddings import resolve_embedding_dimension

        assert resolve_embedding_dimension("unknown/model") == 1536


class TestDimensionTiers:
    """Tests for the three embedding dimension tiers."""

    def test_all_three_tiers_create_distinct_tables(self):
        from muxi.runtime.services.memory.long_term import get_memory_model

        tables = {
            get_memory_model(384).__tablename__,
            get_memory_model(768).__tablename__,
            get_memory_model(1536).__tablename__,
        }
        assert tables == {"memories_384", "memories_768", "memories_1536"}

    def test_available_local_models(self):
        from muxi.runtime.services.memory.local_embeddings import AVAILABLE_LOCAL_MODELS

        assert "all-MiniLM-L6-v2" in AVAILABLE_LOCAL_MODELS
        assert AVAILABLE_LOCAL_MODELS["all-MiniLM-L6-v2"]["dimension"] == 384

        assert "all-mpnet-base-v2" in AVAILABLE_LOCAL_MODELS
        assert AVAILABLE_LOCAL_MODELS["all-mpnet-base-v2"]["dimension"] == 768

    def test_api_embedding_dimensions(self):
        from muxi.runtime.services.memory.local_embeddings import API_EMBEDDING_DIMENSIONS

        assert API_EMBEDDING_DIMENSIONS["openai/text-embedding-3-small"] == 1536
        assert API_EMBEDDING_DIMENSIONS["openai/text-embedding-3-large"] == 3072
