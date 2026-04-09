from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.formation.memory.persistent_manager import PersistentMemoryManager
from muxi.runtime.formation.memory.user_context import UserContextManager
from muxi.runtime.formation.overlord.chat_orchestrator import ChatOrchestrator
from muxi.runtime.formation.prompts.loader import PromptLoader
from muxi.runtime.services import observability
from muxi.runtime.services.memory.long_term import ensure_memory_table_indexes


class MultiCollectionBackend:
    def __init__(self, search_results=None):
        self.build_calls = []
        self.search_calls = []
        self.search_results = search_results or [
            {
                "id": "mem-1",
                "text": "Corey likes turtles",
                "metadata": {"collection": "preferences"},
                "score": 0.95,
            }
        ]

    def build_search_parameters(
        self,
        query,
        k=5,
        user_id=None,
        full_filter=None,
        collection=None,
        collections=None,
        query_embedding=None,
    ):
        self.build_calls.append(
            {
                "query": query,
                "k": k,
                "user_id": user_id,
                "full_filter": full_filter,
                "collection": collection,
                "collections": collections,
                "query_embedding": query_embedding,
            }
        )
        params = {"query": query, "limit": k, "filter_metadata": full_filter}
        if user_id is not None:
            params["external_user_id"] = user_id
        if collections is not None:
            params["collections"] = collections
        elif collection is not None:
            params["collection"] = collection
        if query_embedding is not None:
            params["query_embedding"] = query_embedding
        return params

    async def search(
        self,
        query,
        limit=5,
        query_embedding=None,
        collection=None,
        collections=None,
        filter_metadata=None,
        external_user_id=None,
    ):
        self.search_calls.append(
            {
                "query": query,
                "limit": limit,
                "query_embedding": query_embedding,
                "collection": collection,
                "collections": collections,
                "filter_metadata": filter_metadata,
                "external_user_id": external_user_id,
            }
        )
        return list(self.search_results)


class FallbackBackend:
    def __init__(self, collection_scores=None):
        self.embedding_model = SimpleNamespace(embed=AsyncMock(return_value=[0.1, 0.2, 0.3]))
        self.search_calls = []
        self.collection_scores = collection_scores or {}

    def _extract_embedding_from_response(self, embedding_response):
        return embedding_response

    async def search(
        self,
        query,
        limit=5,
        query_embedding=None,
        collection=None,
        filter_metadata=None,
        external_user_id=None,
    ):
        self.search_calls.append(
            {
                "query": query,
                "limit": limit,
                "query_embedding": query_embedding,
                "collection": collection,
                "filter_metadata": filter_metadata,
                "external_user_id": external_user_id,
            }
        )
        return [
            {
                "id": f"{collection}-1",
                "text": f"{collection} result",
                "metadata": {"collection": collection},
                "score": self.collection_scores.get(collection, 0.5),
            }
        ]


class FakeConnection:
    def __init__(self, statements):
        self.statements = statements

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        self.statements.append(str(statement))

    def commit(self):
        self.statements.append("COMMIT")


class FakeEngine:
    def __init__(self, statements):
        self.statements = statements

    def connect(self):
        return FakeConnection(self.statements)


class FailingEngine:
    def connect(self):
        raise RuntimeError("ddl failed")


class TestPersistentMemoryManagerSpeedups:
    @pytest.mark.asyncio
    async def test_uses_single_multi_collection_search_when_backend_supports_it(self):
        backend = MultiCollectionBackend()
        overlord = SimpleNamespace(long_term_memory=backend, is_multi_user=True)
        manager = PersistentMemoryManager(overlord)

        results = await manager.search_long_term_memory(
            query="What is my current user profile?",
            k=3,
            user_id="tester",
            collections=["preferences", "user_identity"],
        )

        assert len(backend.search_calls) == 1
        assert backend.build_calls[0]["collections"] == ["preferences", "user_identity"]
        assert results[0]["text"] == "Corey likes turtles"

    @pytest.mark.asyncio
    async def test_reuses_query_embedding_when_backend_needs_collection_fallback(self):
        backend = FallbackBackend()
        overlord = SimpleNamespace(long_term_memory=backend, is_multi_user=True)
        manager = PersistentMemoryManager(overlord)

        await manager.search_long_term_memory(
            query="What is my current user profile?",
            k=3,
            user_id="tester",
            collections=["preferences", "user_identity"],
        )

        assert backend.embedding_model.embed.await_count == 1
        assert len(backend.search_calls) == 2
        assert backend.search_calls[0]["query_embedding"] == [0.1, 0.2, 0.3]
        assert backend.search_calls[1]["query_embedding"] == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_resorts_unified_multi_collection_results_by_score_and_top_k(self):
        backend = MultiCollectionBackend(
            search_results=[
                {"id": "mem-1", "text": "low", "metadata": {}, "score": 0.2},
                {"id": "mem-2", "text": "high", "metadata": {}, "score": 0.9},
                {"id": "mem-3", "text": "mid", "metadata": {}, "score": 0.6},
            ]
        )
        overlord = SimpleNamespace(long_term_memory=backend, is_multi_user=True)
        manager = PersistentMemoryManager(overlord)

        results = await manager.search_long_term_memory(
            query="profile",
            k=2,
            user_id="tester",
            collections=["preferences", "user_identity"],
        )

        assert [item["text"] for item in results] == ["high", "mid"]

    @pytest.mark.asyncio
    async def test_resorts_fallback_collection_results_by_score_and_top_k(self):
        backend = FallbackBackend(
            collection_scores={
                "preferences": 0.3,
                "user_identity": 0.95,
                "activities": 0.6,
            }
        )
        overlord = SimpleNamespace(long_term_memory=backend, is_multi_user=True)
        manager = PersistentMemoryManager(overlord)

        results = await manager.search_long_term_memory(
            query="profile",
            k=2,
            user_id="tester",
            collections=["preferences", "user_identity", "activities"],
        )

        assert [item["text"] for item in results] == ["user_identity result", "activities result"]


class TestUserSynopsisFastPath:
    @pytest.mark.asyncio
    async def test_identity_synopsis_uses_user_scoped_list_memories(self):
        long_term_memory = SimpleNamespace(
            get_user_id=AsyncMock(return_value=5),
            list_memories=AsyncMock(
                side_effect=[
                    [{"text": "Corey is the founder of MUXI"}],
                    [{"text": "Works with the engineering team"}],
                    [],
                ]
            ),
        )
        buffer_memory = SimpleNamespace(
            kv_get=AsyncMock(return_value=None),
            kv_set=AsyncMock(),
        )
        overlord = SimpleNamespace(
            formation_config={"memory": {"persistent": {"user_synopsis": {"enabled": True}}}},
            buffer_memory=buffer_memory,
            long_term_memory=long_term_memory,
            persistent_memory_manager=object(),
            is_multi_user=True,
        )
        manager = UserContextManager(overlord)
        manager._synthesize_synopsis_with_llm = AsyncMock(return_value="Corey runs MUXI.")

        synopsis = await manager._get_identity_synopsis("tester")

        assert synopsis == "Corey runs MUXI."
        assert long_term_memory.list_memories.await_count == 3
        for call in long_term_memory.list_memories.await_args_list:
            assert call.kwargs["external_user_id"] == "tester"

    @pytest.mark.asyncio
    async def test_profile_recall_skips_semantic_memory_search_when_synopsis_exists(self):
        overlord = SimpleNamespace(
            formation_config={"memory": {"buffer": {"size": 10, "vector_search": True}}},
            is_multi_user=True,
            get_user_synopsis=AsyncMock(return_value="Corey likes concise technical replies."),
            long_term_memory=object(),
            persistent_memory_manager=SimpleNamespace(search_long_term_memory=AsyncMock()),
            buffer_memory_manager=SimpleNamespace(
                search_buffer_memory=AsyncMock(return_value=None)
            ),
        )
        orchestrator = ChatOrchestrator(overlord)

        enhanced = await orchestrator._enhance_message_with_context(
            message="What is my current user profile?",
            user_id="tester",
            session_id="sess-1",
        )

        assert "=== USER PROFILE ===" in enhanced
        assert overlord.persistent_memory_manager.search_long_term_memory.await_count == 0

    @pytest.mark.asyncio
    async def test_profile_recall_uses_recent_profile_facts_before_semantic_search(self):
        long_term_memory = SimpleNamespace(
            list_memories=AsyncMock(
                side_effect=[
                    [{"text": "Corey is the founder of MUXI"}],
                    [],
                    [],
                    [{"text": "Prefers concise technical communication"}],
                    [],
                ]
            )
        )
        overlord = SimpleNamespace(
            formation_config={"memory": {"buffer": {"size": 10, "vector_search": True}}},
            is_multi_user=True,
            get_user_synopsis=AsyncMock(return_value=""),
            long_term_memory=long_term_memory,
            persistent_memory_manager=SimpleNamespace(search_long_term_memory=AsyncMock()),
            buffer_memory_manager=SimpleNamespace(
                search_buffer_memory=AsyncMock(return_value=None)
            ),
        )
        orchestrator = ChatOrchestrator(overlord)

        with patch.object(PromptLoader, "get", return_value="Use these memories."):
            enhanced = await orchestrator._enhance_message_with_context(
                message="What do you know about me?",
                user_id="tester",
                session_id="sess-1",
            )

        assert "=== RELEVANT MEMORIES ===" in enhanced
        assert "Corey is the founder of MUXI" in enhanced
        assert "Prefers concise technical communication" in enhanced
        assert overlord.persistent_memory_manager.search_long_term_memory.await_count == 0


class TestMemoryIndexCreation:
    def test_creates_lookup_and_vector_indexes_for_postgres(self):
        statements = []
        db_manager = SimpleNamespace(
            database_type="postgresql",
            engine=FakeEngine(statements),
        )

        ensure_memory_table_indexes(db_manager, 384)

        joined = "\n".join(statements)
        assert "idx_memories_384_user_collection" in joined
        assert "idx_memories_384_embedding_ivfflat" in joined
        assert "USING ivfflat" in joined

    def test_index_creation_failures_are_logged_and_non_fatal(self):
        db_manager = SimpleNamespace(
            database_type="postgresql",
            engine=FailingEngine(),
        )

        with patch("muxi.runtime.services.memory.long_term.observability.observe") as observe:
            ensure_memory_table_indexes(db_manager, 384)

        assert observe.call_count == 2
        for call in observe.call_args_list:
            assert call.kwargs["event_type"] == observability.ErrorEvents.DATABASE_OPERATION_FAILED
            assert call.kwargs["level"] == observability.EventLevel.WARNING
