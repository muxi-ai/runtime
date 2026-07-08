"""
Unit tests for the per-user channel state store (memory backend).

Covers preference updates, per-channel context merging, last-channel
tracking from inbound messages, user id normalization, and known-user
enumeration. Database write-through is exercised by the proactiveness
e2e tests against a real formation database.
"""

from muxi.runtime.formation.proactive import UserChannelStore


def _store():
    return UserChannelStore(formation_id="test-formation")


class TestPreferences:
    async def test_empty_state_defaults(self):
        store = _store()
        state = await store.get_state("ran")
        assert state == {
            "preferred_channel": None,
            "channels": {},
            "last_channel": None,
            "timezone": None,
        }

    async def test_set_and_get_preferences(self):
        store = _store()
        await store.set_preferences(
            "ran",
            preferred_channel="telegram",
            channels={"telegram": {"chat_id": "123"}},
            timezone="Europe/London",
        )
        state = await store.get_state("ran")
        assert state["preferred_channel"] == "telegram"
        assert state["channels"]["telegram"] == {"chat_id": "123"}
        assert state["timezone"] == "Europe/London"

    async def test_partial_update_leaves_other_fields(self):
        store = _store()
        await store.set_preferences("ran", preferred_channel="telegram")
        await store.set_preferences("ran", timezone="UTC")
        state = await store.get_state("ran")
        assert state["preferred_channel"] == "telegram"
        assert state["timezone"] == "UTC"

    async def test_channel_context_merges_per_channel(self):
        store = _store()
        await store.set_preferences("ran", channels={"slack": {"channel": "C1"}})
        await store.set_preferences("ran", channels={"slack": {"thread_ts": "42"}})
        state = await store.get_state("ran")
        assert state["channels"]["slack"] == {"channel": "C1", "thread_ts": "42"}

    async def test_empty_channel_mapping_removes_channel(self):
        store = _store()
        await store.set_preferences("ran", channels={"slack": {"channel": "C1"}})
        await store.set_preferences("ran", channels={"slack": {}})
        state = await store.get_state("ran")
        assert "slack" not in state["channels"]

    async def test_empty_string_clears_preference(self):
        store = _store()
        await store.set_preferences("ran", preferred_channel="telegram")
        await store.set_preferences("ran", preferred_channel="")
        state = await store.get_state("ran")
        assert state["preferred_channel"] is None

    async def test_returned_state_is_a_copy(self):
        store = _store()
        await store.set_preferences("ran", channels={"slack": {"channel": "C1"}})
        state = await store.get_state("ran")
        state["channels"]["slack"]["channel"] = "TAMPERED"
        fresh = await store.get_state("ran")
        assert fresh["channels"]["slack"]["channel"] == "C1"


class TestInboundRecording:
    async def test_record_inbound_sets_last_channel(self):
        store = _store()
        await store.record_inbound("ran", "telegram")
        state = await store.get_state("ran")
        assert state["last_channel"] == "telegram"

    async def test_record_inbound_merges_context(self):
        store = _store()
        await store.record_inbound("ran", "slack", {"channel": "C1"})
        await store.record_inbound("ran", "slack", {"thread_ts": "9", "channel": None})
        state = await store.get_state("ran")
        # None values from sparse platform payloads never clobber known values
        assert state["channels"]["slack"] == {"channel": "C1", "thread_ts": "9"}

    async def test_last_channel_moves_with_conversation(self):
        store = _store()
        await store.record_inbound("ran", "telegram", {"chat_id": "1"})
        await store.record_inbound("ran", "slack", {"channel": "C1"})
        state = await store.get_state("ran")
        assert state["last_channel"] == "slack"
        # Earlier channel addressing is retained for explicit routing
        assert state["channels"]["telegram"] == {"chat_id": "1"}


class TestNormalizationAndEnumeration:
    async def test_user_ids_are_normalized(self):
        store = _store()
        await store.record_inbound("  RaN ", "telegram")
        state = await store.get_state("ran")
        assert state["last_channel"] == "telegram"

    async def test_known_users(self):
        store = _store()
        await store.record_inbound("alice", "telegram")
        await store.set_preferences("bob", preferred_channel=None)
        assert await store.known_users() == ["alice", "bob"]
