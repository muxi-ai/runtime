"""Unit tests for memory namespaces Phases 2+3: shared scopes.

Covers the shared-scope surface end to end at the unit level:

  * Write-grant enforcement (``memory.write`` grants): formation vs
    ``group:{id}`` matching, fnmatch globs, deny-by-default with no
    permissions (system principals get no implicit bypass).
  * Read fan-out composition: explicit group_ids > per-request
    ResolvedPermissions (ContextVar) > registered resolver fallback >
    none (user + formation only).
  * SQLite backend: shared writes stamp their scope; default search
    fans out user -> member groups -> formation; group isolation (user A
    never sees group-B rows); specificity-wins weighting; per-query
    narrowing (``scopes=["user"]`` restores the Phase 1 query).
  * Extractor pin: conversation-derived extraction writes user scope
    only, and its dedup is scope-narrowed so a shared fact does not
    suppress the user's own fact.
  * Event substrate: appends record the write's true scope (default
    user), and FlatFactProjector replay reproduces scoped rows;
    projection reset wipes event-sourced shared rows.
  * Working memory: group partition routing, identity-chain fan-out for
    session searches (membership-gated), and the #200 dilution guard
    (non-buffer formation items stay out of chat recall).
  * The memories route's scope authorization helper (403 semantics).

Patches ``probe_dimension`` / ``embed`` (as imported into ``sqlite`` /
``working``) to avoid any OneLLM / network / HF calls.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.gbac import enforcement as gbac_enforcement
from muxi.runtime.services.gbac.loader import ResolvedGroup
from muxi.runtime.services.gbac.resolver import ResolvedPermissions
from muxi.runtime.services.memory import scopes as memory_scopes
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    MemoryEvent,
    ProjectionCheckpoint,
)
from muxi.runtime.services.memory.events.projectors import (
    FACT_EVENT_METADATA_KEY,
    FlatFactProjector,
    event_scope,
)
from muxi.runtime.services.memory.events.storage import MemoryEventStorage
from muxi.runtime.services.memory.scopes import (
    is_write_scope_allowed,
    normalize_read_scopes,
    register_group_membership_resolver,
    resolve_read_group_ids,
    write_scope_target,
)
from muxi.runtime.services.memory.sqlite import SQLiteMemory
from muxi.runtime.services.memory.working import (
    WorkingMemory,
)

DIM = 64
MODEL = "local/nomic-ai/nomic-embed-text-v1.5"
FORMATION_ID = "shared-scopes-formation"


def _permissions(*grants: str, group_ids=("team-a",)) -> ResolvedPermissions:
    """Build ResolvedPermissions whose groups carry the given memory.write grants."""
    groups = tuple(
        ResolvedGroup(group_id=gid, source_path=f"{gid}.yaml", memory_write=tuple(grants))
        for gid in group_ids
    )
    return ResolvedPermissions(group_ids=tuple(sorted(group_ids)), groups=groups)


@pytest.fixture(autouse=True)
def _clean_permission_context():
    """Every test starts and ends with no request-scoped permissions."""
    token = gbac_enforcement.set_current_permissions(None)
    yield
    gbac_enforcement.reset_current_permissions(token)


# ----------------------------------------------------------------------
# Write-grant enforcement
# ----------------------------------------------------------------------


class TestWriteGrants:
    def test_user_scope_is_never_gated(self):
        assert is_write_scope_allowed(None, "user") is True

    def test_no_permissions_denies_all_shared_scopes(self):
        assert is_write_scope_allowed(None, "formation") is False
        assert is_write_scope_allowed(None, "group", "team-a") is False

    def test_formation_grant(self):
        permissions = _permissions("formation")
        assert is_write_scope_allowed(permissions, "formation") is True
        assert is_write_scope_allowed(permissions, "group", "team-a") is False

    def test_group_grant_matches_exact_group_only(self):
        permissions = _permissions("group:team-a")
        assert is_write_scope_allowed(permissions, "group", "team-a") is True
        assert is_write_scope_allowed(permissions, "group", "team-b") is False
        assert is_write_scope_allowed(permissions, "formation") is False

    def test_glob_grant_matches_all_groups_but_not_formation(self):
        permissions = _permissions("group:*")
        assert is_write_scope_allowed(permissions, "group", "team-a") is True
        assert is_write_scope_allowed(permissions, "group", "anything") is True
        assert is_write_scope_allowed(permissions, "formation") is False

    def test_group_scope_requires_scope_id(self):
        with pytest.raises(ValueError):
            is_write_scope_allowed(_permissions("group:*"), "group", None)

    def test_write_scope_target_matches_grant_syntax(self):
        assert write_scope_target("formation") == "formation"
        assert write_scope_target("group", "hr") == "group:hr"

    def test_grants_union_across_groups(self):
        permissions = _permissions("group:team-a", "formation", group_ids=("team-a", "announcers"))
        assert is_write_scope_allowed(permissions, "formation") is True
        assert is_write_scope_allowed(permissions, "group", "team-a") is True


# ----------------------------------------------------------------------
# Read fan-out composition
# ----------------------------------------------------------------------


class TestFanOutComposition:
    async def test_explicit_group_ids_win(self):
        gbac_enforcement.set_current_permissions(_permissions(group_ids=("ctx-group",)))
        result = await resolve_read_group_ids(FORMATION_ID, "alice", group_ids=["explicit"])
        assert result == ("explicit",)

    async def test_context_permissions_supply_memberships(self):
        gbac_enforcement.set_current_permissions(_permissions(group_ids=("team-a", "team-b")))
        result = await resolve_read_group_ids(FORMATION_ID, "alice")
        assert result == ("team-a", "team-b")

    async def test_resolver_fallback_by_external_user_id(self):
        class FakeResolver:
            def __init__(self):
                self.seen = None

            async def resolve(self, user_id):
                self.seen = user_id
                return _permissions(group_ids=("resolved-group",))

        resolver = FakeResolver()
        register_group_membership_resolver("fallback-formation", resolver)
        try:
            result = await resolve_read_group_ids("fallback-formation", "Alice@Example.com ")
            assert result == ("resolved-group",)
            # Same normalization as the overlord chat path.
            assert resolver.seen == "alice@example.com"
        finally:
            register_group_membership_resolver("fallback-formation", None)

    async def test_resolver_failure_degrades_to_no_groups(self):
        class BrokenResolver:
            async def resolve(self, user_id):
                raise RuntimeError("db down")

        register_group_membership_resolver("broken-formation", BrokenResolver())
        try:
            assert await resolve_read_group_ids("broken-formation", "alice") == ()
        finally:
            register_group_membership_resolver("broken-formation", None)

    async def test_no_resolver_no_context_means_no_groups(self):
        assert await resolve_read_group_ids("unknown-formation", "alice") == ()

    def test_normalize_read_scopes(self):
        assert normalize_read_scopes(None) == ("user", "group", "formation")
        assert normalize_read_scopes(["user"]) == ("user",)
        with pytest.raises(ValueError):
            normalize_read_scopes(["everything"])
        with pytest.raises(ValueError):
            normalize_read_scopes([])


# ----------------------------------------------------------------------
# SQLite backend: scoped writes + read fan-out
# ----------------------------------------------------------------------


def _deterministic_vec(text: str, dim: int = DIM) -> list[float]:
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(np.float32).tolist()


def _deterministic_embed(model, text, *, task=None, **_kw):
    if isinstance(text, list):
        return [_deterministic_vec(t) for t in text]
    return [_deterministic_vec(text)]


def _sqlite_patched():
    return (
        patch(
            "muxi.runtime.services.memory.sqlite.probe_dimension",
            new_callable=AsyncMock,
        ),
        patch(
            "muxi.runtime.services.memory.sqlite.embed",
            new_callable=AsyncMock,
        ),
    )


@pytest.fixture
def sqlite_mem(tmp_path):
    probe_patch, embed_patch = _sqlite_patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        mock_embed.side_effect = _deterministic_embed
        yield SQLiteMemory(
            db_path=str(tmp_path / "scopes.db"),
            formation_id=FORMATION_ID,
            embedding_model=MODEL,
        )


async def _seed_scoped_rows(mem: SQLiteMemory) -> None:
    """One row per scope: alice's user fact, team-a/team-b facts, formation fact."""
    await mem.add("alice likes tea", user_id="alice")
    await mem.add("team-a ships on fridays", user_id="alice", scope=("group", "team-a"))
    await mem.add("team-b meets on mondays", user_id="bob", scope=("group", "team-b"))
    await mem.add("the refund policy is 30 days", user_id="bob", scope=("formation", "x"))


class TestSQLiteScopedWrites:
    async def test_shared_writes_stamp_scope(self, sqlite_mem):
        await _seed_scoped_rows(sqlite_mem)
        rows = sqlite_mem.conn.execute(
            f"SELECT text, scope_type, scope_id FROM {sqlite_mem.memories_table}"
        ).fetchall()
        by_text = {text: (stype, sid) for text, stype, sid in rows}
        alice_internal = await sqlite_mem.get_or_create_user("alice")
        assert by_text["alice likes tea"] == ("user", str(alice_internal))
        assert by_text["team-a ships on fridays"] == ("group", "team-a")
        assert by_text["team-b meets on mondays"] == ("group", "team-b")
        # Formation scope_id is forced to the backend's formation id --
        # the caller-supplied "x" cannot cross-stamp another formation.
        assert by_text["the refund policy is 30 days"] == ("formation", FORMATION_ID)

    async def test_invalid_scope_rejected(self, sqlite_mem):
        with pytest.raises(ValueError):
            await sqlite_mem.add("bad", user_id="alice", scope=("org", "acme"))
        with pytest.raises(ValueError):
            await sqlite_mem.add("bad", user_id="alice", scope=("group", None))


class TestSQLiteReadFanOut:
    async def test_default_fanout_with_explicit_memberships(self, sqlite_mem):
        await _seed_scoped_rows(sqlite_mem)
        results = await sqlite_mem.search(
            "what do we know", limit=10, user_id="alice", group_ids=["team-a"]
        )
        texts = {r["text"] for r in results}
        assert "alice likes tea" in texts
        assert "team-a ships on fridays" in texts
        assert "the refund policy is 30 days" in texts
        # Group isolation: team-b rows never surface for a team-a member.
        assert "team-b meets on mondays" not in texts
        # Scope provenance travels with the results.
        scopes_by_text = {r["text"]: r["scope_type"] for r in results}
        assert scopes_by_text["team-a ships on fridays"] == "group"
        assert scopes_by_text["the refund policy is 30 days"] == "formation"

    async def test_memberships_from_context_permissions(self, sqlite_mem):
        await _seed_scoped_rows(sqlite_mem)
        gbac_enforcement.set_current_permissions(_permissions(group_ids=("team-b",)))
        results = await sqlite_mem.search("meetings", limit=10, user_id="bob")
        texts = {r["text"] for r in results}
        assert "team-b meets on mondays" in texts
        assert "team-a ships on fridays" not in texts

    async def test_no_groups_fallback_is_user_plus_formation(self, sqlite_mem):
        await _seed_scoped_rows(sqlite_mem)
        # No ContextVar permissions, no registered resolver, no explicit ids.
        results = await sqlite_mem.search("what do we know", limit=10, user_id="alice")
        texts = {r["text"] for r in results}
        assert "alice likes tea" in texts
        assert "the refund policy is 30 days" in texts
        assert "team-a ships on fridays" not in texts
        assert "team-b meets on mondays" not in texts

    async def test_per_query_narrowing_restores_user_only(self, sqlite_mem):
        await _seed_scoped_rows(sqlite_mem)
        results = await sqlite_mem.search(
            "what do we know",
            limit=10,
            user_id="alice",
            group_ids=["team-a"],
            scopes=["user"],
        )
        assert {r["text"] for r in results} == {"alice likes tea"}

    async def test_specificity_wins_on_equal_relevance(self, sqlite_mem):
        # Identical text -> identical deterministic embedding -> equal raw
        # similarity; the user row must outrank the formation row.
        await sqlite_mem.add("the deploy day is friday", user_id="alice")
        await sqlite_mem.add(
            "the deploy day is friday", user_id="bob", scope=("formation", FORMATION_ID)
        )
        results = await sqlite_mem.search("the deploy day is friday", limit=2, user_id="alice")
        assert len(results) == 2
        assert results[0]["scope_type"] == "user"
        assert results[1]["scope_type"] == "formation"
        # Raw similarity is reported unweighted (user scores unchanged).
        assert results[0]["score"] == pytest.approx(results[1]["score"])

    async def test_user_scope_recall_unchanged_without_shared_rows(self, sqlite_mem):
        # Regression pin: with only user-scope data, the default cascade
        # returns exactly what the Phase 1 user-only query returns.
        await sqlite_mem.add("alice likes tea", user_id="alice")
        await sqlite_mem.add("alice owns a bike", user_id="alice")
        cascade = await sqlite_mem.search("alice", limit=10, user_id="alice")
        user_only = await sqlite_mem.search("alice", limit=10, user_id="alice", scopes=["user"])
        assert [(r["text"], r["score"]) for r in cascade] == [
            (r["text"], r["score"]) for r in user_only
        ]


# ----------------------------------------------------------------------
# Extractor pin: user scope only, always
# ----------------------------------------------------------------------


class TestExtractorUserScopeOnly:
    async def test_extraction_writes_user_scope_and_dedup_is_scope_narrowed(self, sqlite_mem):
        from muxi.runtime.services.memory.extractor import MemoryExtractor

        # A shared fact with the same text already exists: without the
        # scope-narrowed dedup it would suppress the user's own fact.
        await sqlite_mem.add(
            "User likes green tea", user_id="bob", scope=("formation", FORMATION_ID)
        )

        class StubOverlord:
            is_multi_user = False
            long_term_memory = sqlite_mem
            memory_events = None
            current_agent = "overlord"

        extractor = MemoryExtractor(overlord=StubOverlord())
        await extractor._process_extraction_results(
            {
                "extracted_info": [
                    {
                        "memory": "User likes green tea",
                        "importance": 0.9,
                        "confidence": 0.9,
                        "collection": "preferences",
                    }
                ]
            },
            "alice",
        )

        rows = sqlite_mem.conn.execute(
            f"SELECT text, scope_type, scope_id, user_id FROM {sqlite_mem.memories_table} "
            "WHERE json_extract(metadata, '$.source') = 'extraction'"
        ).fetchall()
        assert len(rows) == 1, "shared fact must not dedup away the user's own fact"
        text, scope_type, scope_id, owner = rows[0]
        assert scope_type == "user"
        assert scope_id == str(owner)


# ----------------------------------------------------------------------
# Event substrate: scoped appends + scoped replay
# ----------------------------------------------------------------------


EVENT_TABLES = [MemoryEvent.__table__, ProjectionCheckpoint.__table__]


@pytest.fixture
def event_storage(tmp_path):
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/events.db")
    db_manager.create_tables(Base.metadata, tables=EVENT_TABLES)
    yield MemoryEventStorage(db_manager, FORMATION_ID)
    db_manager.engine.dispose()


class TestScopedEvents:
    async def test_default_append_keeps_user_scope(self, event_storage):
        event, created = await event_storage.append(
            user_id="alice",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "fact", "collection": "context"},
            source="interaction",
        )
        assert created is True
        assert event["scope_type"] == "user"
        assert event["scope_id"] == "alice"
        assert event_scope(event) is None

    async def test_shared_append_records_true_scope(self, event_storage):
        event, _ = await event_storage.append(
            user_id="alice",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "team fact", "collection": "context"},
            source="user_edit",
            scope_type="group",
            scope_id="team-a",
        )
        assert event["scope_type"] == "group"
        assert event["scope_id"] == "team-a"
        assert event_scope(event) == ("group", "team-a")

    async def test_formation_append_defaults_scope_id(self, event_storage):
        event, _ = await event_storage.append(
            user_id="alice",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "org fact", "collection": "context"},
            source="user_edit",
            scope_type="formation",
        )
        assert event["scope_type"] == "formation"
        assert event["scope_id"] == FORMATION_ID

    async def test_group_append_requires_scope_id(self, event_storage):
        with pytest.raises(ValueError):
            await event_storage.append(
                user_id="alice",
                event_type=EVENT_FACT_EXTRACTED,
                payload={"memory": "fact", "collection": "context"},
                source="user_edit",
                scope_type="group",
            )

    async def test_replay_reproduces_scoped_rows_and_reset_wipes_them(
        self, event_storage, sqlite_mem
    ):
        event, _ = await event_storage.append(
            user_id="alice",
            event_type=EVENT_FACT_EXTRACTED,
            payload={
                "memory": "the refund policy is 30 days",
                "collection": "context",
                "metadata": {"source": "user_edit"},
            },
            source="user_edit",
            source_id="mem-1",
            scope_type="formation",
        )

        projector = FlatFactProjector(sqlite_mem)
        await projector.apply(event)

        rows = sqlite_mem.conn.execute(
            f"SELECT text, scope_type, scope_id, metadata FROM {sqlite_mem.memories_table}"
        ).fetchall()
        assert len(rows) == 1
        text, scope_type, scope_id, metadata = rows[0]
        assert (scope_type, scope_id) == ("formation", FORMATION_ID)
        import json as std_json

        assert std_json.loads(metadata)[FACT_EVENT_METADATA_KEY] == event["id"]

        # Reset wipes exactly the event-sourced rows, so replay is
        # idempotent under wipe-and-rebuild.
        deleted = await projector.reset("alice")
        assert deleted == 1
        remaining = sqlite_mem.conn.execute(
            f"SELECT COUNT(*) FROM {sqlite_mem.memories_table}"
        ).fetchone()[0]
        assert remaining == 0


# ----------------------------------------------------------------------
# Working memory: identity-chain fan-out
# ----------------------------------------------------------------------


def _wm_patched():
    return (
        patch(
            "muxi.runtime.services.memory.working.probe_dimension",
            new_callable=AsyncMock,
        ),
        patch(
            "muxi.runtime.services.memory.working.embed",
            new_callable=AsyncMock,
        ),
    )


WM_DIM = 8


def _one_hot(position: int) -> list:
    vector = [0.0] * WM_DIM
    vector[position] = 1.0
    return vector


class TestWorkingMemoryFanOut:
    def test_group_partition_key(self):
        probe_patch, embed_patch = _wm_patched()
        with probe_patch, embed_patch:
            mem = WorkingMemory(formation_id=FORMATION_ID, embedding_model=MODEL)
        assert mem._partition_key("buffer", {"group_id": "team-a"}) == "group:team-a"
        # Explicitly group-addressed items outrank the user key...
        assert (
            mem._partition_key("buffer", {"group_id": "team-a", "user_id": "u1"}) == "group:team-a"
        )
        # ...but session still wins (conversation turns stay per-session).
        assert (
            mem._partition_key("buffer", {"group_id": "team-a", "session_id": "s1"}) == "session:s1"
        )

    async def _seeded(self):
        mem = WorkingMemory(formation_id=FORMATION_ID, embedding_model=MODEL)
        await mem.add_with_embedding(
            "session chat", embedding=_one_hot(0), metadata={"session_id": "s1", "user_id": "u1"}
        )
        await mem.add_with_embedding(
            "u1 cross-session note", embedding=_one_hot(0), metadata={"user_id": "u1"}
        )
        await mem.add_with_embedding(
            "team-a shared note", embedding=_one_hot(0), metadata={"group_id": "team-a"}
        )
        await mem.add_with_embedding(
            "team-b shared note", embedding=_one_hot(0), metadata={"group_id": "team-b"}
        )
        await mem.add_with_embedding("formation announcement", embedding=_one_hot(0), metadata={})
        await mem.add_with_embedding(
            "runbook", embedding=_one_hot(0), metadata={"sop_id": "sop-1"}, namespace="sops"
        )
        return mem

    async def test_session_search_reads_identity_chain(self):
        probe_patch, embed_patch = _wm_patched()
        with probe_patch as mock_probe, embed_patch:
            mock_probe.return_value = WM_DIM
            mem = await self._seeded()
            gbac_enforcement.set_current_permissions(_permissions(group_ids=("team-a",)))

            results = await mem.search(
                "q",
                query_vector=_one_hot(0),
                limit=10,
                session_id="s1",
                filter_metadata={"user_id": "u1"},
            )
            texts = {r["text"] for r in results}
            # Session + the requester's chain: user, member groups, formation.
            assert "session chat" in texts
            assert "u1 cross-session note" in texts
            assert "team-a shared note" in texts
            assert "formation announcement" in texts
            # Membership gating: team-b's partition is not in the chain.
            assert "team-b shared note" not in texts
            # #200 dilution guard: non-buffer formation items stay out.
            assert "runbook" not in texts

    async def test_session_search_without_permissions_has_no_group_items(self):
        probe_patch, embed_patch = _wm_patched()
        with probe_patch as mock_probe, embed_patch:
            mock_probe.return_value = WM_DIM
            mem = await self._seeded()

            results = await mem.search(
                "q",
                query_vector=_one_hot(0),
                limit=10,
                session_id="s1",
                filter_metadata={"user_id": "u1"},
            )
            texts = {r["text"] for r in results}
            assert "team-a shared note" not in texts
            assert "team-b shared note" not in texts
            assert "session chat" in texts

    async def test_unscoped_search_gates_group_partitions_by_membership(self):
        probe_patch, embed_patch = _wm_patched()
        with probe_patch as mock_probe, embed_patch:
            mock_probe.return_value = WM_DIM
            mem = await self._seeded()
            gbac_enforcement.set_current_permissions(_permissions(group_ids=("team-a",)))

            results = await mem.search("q", query_vector=_one_hot(0), limit=10)
            texts = {r["text"] for r in results}
            assert "team-a shared note" in texts
            assert "team-b shared note" not in texts


# ----------------------------------------------------------------------
# Memories route: scope authorization helper (403 semantics)
# ----------------------------------------------------------------------


class TestRouteScopeAuthorization:
    @staticmethod
    def _formation(resolver=None):
        class FakeFormation:
            formation_id = FORMATION_ID
            permission_resolver = resolver

        return FakeFormation()

    @staticmethod
    def _memory(scope=None, scope_id=None):
        from muxi.runtime.formation.server.routes.client.memory import MemoryCreate

        return MemoryCreate(content="fact", scope=scope, scope_id=scope_id)

    async def _resolve(self, formation, memory):
        from muxi.runtime.formation.server.routes.client.memory import _resolve_write_scope

        return await _resolve_write_scope(formation, "alice", memory, "req-1")

    async def test_user_scope_passes_without_resolver(self):
        scope, error = await self._resolve(self._formation(), self._memory())
        assert scope is None and error is None

    async def test_shared_scope_without_resolver_is_403(self):
        scope, error = await self._resolve(self._formation(), self._memory(scope="formation"))
        assert scope is None
        assert error is not None and error.status_code == 403

    async def test_granted_shared_scope_resolves(self):
        class FakeResolver:
            group_ids = ("team-a",)

            async def resolve(self, user_id):
                return _permissions("group:team-a", "formation")

        formation = self._formation(FakeResolver())
        scope, error = await self._resolve(formation, self._memory(scope="formation"))
        assert error is None and scope == ("formation", FORMATION_ID)
        scope, error = await self._resolve(
            formation, self._memory(scope="group", scope_id="team-a")
        )
        assert error is None and scope == ("group", "team-a")

    async def test_ungranted_group_is_403(self):
        class FakeResolver:
            group_ids = ("team-a", "team-b")

            async def resolve(self, user_id):
                return _permissions("group:team-a")

        formation = self._formation(FakeResolver())
        scope, error = await self._resolve(
            formation, self._memory(scope="group", scope_id="team-b")
        )
        assert scope is None
        assert error is not None and error.status_code == 403

    async def test_glob_grant_to_unknown_group_is_422(self):
        class FakeResolver:
            group_ids = ("team-a",)

            async def resolve(self, user_id):
                return _permissions("group:*")

        formation = self._formation(FakeResolver())
        scope, error = await self._resolve(
            formation, self._memory(scope="group", scope_id="ghost-group")
        )
        assert scope is None
        assert error is not None and error.status_code == 422

    async def test_group_scope_without_scope_id_is_422(self):
        scope, error = await self._resolve(self._formation(), self._memory(scope="group"))
        assert scope is None
        assert error is not None and error.status_code == 422

    async def test_unknown_scope_is_422(self):
        scope, error = await self._resolve(self._formation(), self._memory(scope="org"))
        assert scope is None
        assert error is not None and error.status_code == 422


# ----------------------------------------------------------------------
# Registry hygiene
# ----------------------------------------------------------------------


class TestResolverRegistry:
    def test_register_and_unregister(self):
        sentinel = object()
        register_group_membership_resolver("f1", sentinel)
        assert memory_scopes._membership_resolvers["f1"] is sentinel
        register_group_membership_resolver("f1", None)
        assert "f1" not in memory_scopes._membership_resolvers
