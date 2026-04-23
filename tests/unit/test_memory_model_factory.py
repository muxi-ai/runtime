"""Unit tests for the dynamic memory-model factory.

After the embedding-platform migration, the legacy dimension resolvers
are gone — dimension resolution now flows through the shared helper at
``services.memory.embedding.probe_dimension``, covered by
``tests/unit/test_memory_embedding_helper.py`` and the lazy-dim consumer
test modules.

What remains worth asserting here is the ``get_memory_model`` ORM
factory itself — it is the piece that binds each embedding dimension to
a dedicated ``memories_{dim}`` table and is exercised indirectly by
every memory consumer. These tests stay deliberately focused on the
factory's pure-Python behavior (table naming, instance caching, column
shape, backwards-compatible alias).
"""


class TestMemoryModelFactory:
    """Tests for ``get_memory_model()`` factory function."""

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


class TestDimensionTiers:
    """Tests that the three embedding dimension tiers yield distinct tables."""

    def test_all_three_tiers_create_distinct_tables(self):
        from muxi.runtime.services.memory.long_term import get_memory_model

        tables = {
            get_memory_model(384).__tablename__,
            get_memory_model(768).__tablename__,
            get_memory_model(1536).__tablename__,
        }
        assert tables == {"memories_384", "memories_768", "memories_1536"}
