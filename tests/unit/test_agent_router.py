from types import SimpleNamespace

import pytest

from muxi.runtime.formation.overlord.agent_router import AgentRouter


class FakeActiveAgentTracker:
    async def get_available_agents(self, agent_ids, request_id=None):
        return list(agent_ids)


class FakeRoutingModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


class FakeOverlord:
    def __init__(self, routing_model, include_muxi_generalist=False):
        self.routing_model = routing_model
        self.agents = {
            "assistant": SimpleNamespace(),
            "ms365-assistant": SimpleNamespace(),
        }
        self.agent_descriptions = {
            "assistant": "General-purpose assistant for broad tasks.",
            "ms365-assistant": "Handles Microsoft 365 account and productivity tasks.",
        }
        self.agent_metadata = {
            "assistant": {
                "name": "Assistant",
                "description": self.agent_descriptions["assistant"],
                "role": "general",
                "specialties": [],
                "specialization_domain": "",
                "specialization_keywords": [],
                "tool_names": [],
                "tool_descriptions": [],
            },
            "ms365-assistant": {
                "name": "MS365 Assistant",
                "description": self.agent_descriptions["ms365-assistant"],
                "role": "specialist",
                "specialties": ["microsoft 365", "user profile"],
                "specialization_domain": "microsoft-365",
                "specialization_keywords": ["profile", "current user profile", "email"],
                "tool_names": ["get current user", "list mail messages"],
                "tool_descriptions": [
                    "Get the current user's profile from Microsoft 365.",
                    "List the user's recent email messages from Outlook.",
                ],
            },
        }
        if include_muxi_generalist:
            self.agents["muxi-generalist"] = SimpleNamespace()
            self.agent_descriptions["muxi-generalist"] = (
                "Built-in fallback assistant for general tasks."
            )
            self.agent_metadata["muxi-generalist"] = {
                "name": "MUXI Generalist",
                "description": self.agent_descriptions["muxi-generalist"],
                "role": "general",
                "specialties": ["general help", "broad questions"],
                "specialization_domain": "",
                "specialization_keywords": ["general", "help", "questions"],
            }
        self.active_agent_tracker = FakeActiveAgentTracker()
        self.formation_config = {"overlord": {"caching": {"enabled": True, "ttl": 3600}}}
        self.default_agent_id = "muxi-generalist" if include_muxi_generalist else "assistant"

    async def get_model_for_capability(self, capability):
        return self.routing_model


class TestAgentRouter:
    @pytest.mark.asyncio
    async def test_prompt_includes_specialist_metadata(self):
        overlord = FakeOverlord(FakeRoutingModel(["ms365-assistant"]))
        router = AgentRouter(overlord)

        messages = router._create_routing_messages(
            "What is my current user profile?",
            session_id="session-1",
            available_agents=["assistant", "ms365-assistant"],
        )

        prompt = messages[0]["content"]
        assert "role: specialist" in prompt
        assert "specialization domain: microsoft-365" in prompt
        assert "specialization keywords: profile, current user profile, email" in prompt

    @pytest.mark.asyncio
    async def test_cache_is_scoped_by_session(self):
        routing_model = FakeRoutingModel(["assistant", "ms365-assistant"])
        overlord = FakeOverlord(routing_model)
        router = AgentRouter(overlord)

        first = await router.select_agent_for_message("yes", session_id="session-a")
        second = await router.select_agent_for_message("yes", session_id="session-b")

        assert first == "assistant"
        assert second == "ms365-assistant"
        assert len(routing_model.calls) == 2

    @pytest.mark.asyncio
    async def test_fallback_prefers_specialist_metadata_over_default_generalist(self):
        overlord = FakeOverlord(FakeRoutingModel([]))
        router = AgentRouter(overlord)

        selected = await router._select_best_available_agent(
            "What is my current user profile?", session_id="session-1"
        )

        assert selected == "ms365-assistant"

    @pytest.mark.asyncio
    async def test_llm_muxi_generalist_selection_is_overridden_by_strong_non_muxi_match(self):
        overlord = FakeOverlord(FakeRoutingModel(["muxi-generalist"]), include_muxi_generalist=True)
        router = AgentRouter(overlord)

        selected = await router.select_agent_for_message(
            "What is my current user profile?", session_id="session-1"
        )

        assert selected == "ms365-assistant"

    @pytest.mark.asyncio
    async def test_llm_muxi_generalist_selection_is_kept_without_strong_non_muxi_match(self):
        overlord = FakeOverlord(FakeRoutingModel(["muxi-generalist"]), include_muxi_generalist=True)
        router = AgentRouter(overlord)

        selected = await router.select_agent_for_message("Tell me a joke", session_id="session-1")

        assert selected == "muxi-generalist"

    @pytest.mark.asyncio
    async def test_llm_general_agent_selection_is_overridden_by_strong_specialist_tool_match(self):
        overlord = FakeOverlord(FakeRoutingModel(["assistant"]))
        router = AgentRouter(overlord)

        selected = await router.select_agent_for_message(
            "What is my current user profile?", session_id="session-1"
        )

        assert selected == "ms365-assistant"

    @pytest.mark.asyncio
    async def test_routing_cache_evicts_oldest_entries_beyond_max_size(self):
        routing_model = FakeRoutingModel(["assistant"] * 4)
        overlord = FakeOverlord(routing_model)
        router = AgentRouter(overlord)
        router.MAX_ROUTING_CACHE_SIZE = 3

        for message in ("hello one", "hello two", "hello three", "hello four"):
            await router.select_agent_for_message(message, session_id="session-a")

        assert len(router._routing_cache) == 3
        assert "session:session-a:hello one" not in router._routing_cache
        assert "session:session-a:hello four" in router._routing_cache

    @pytest.mark.asyncio
    async def test_routing_cache_hit_refreshes_recency(self):
        routing_model = FakeRoutingModel(["assistant"] * 3)
        overlord = FakeOverlord(routing_model)
        router = AgentRouter(overlord)
        router.MAX_ROUTING_CACHE_SIZE = 2

        await router.select_agent_for_message("hello one", session_id="session-a")
        await router.select_agent_for_message("hello two", session_id="session-a")

        # Cache hit on "hello one" refreshes its recency (no model call)
        await router.select_agent_for_message("hello one", session_id="session-a")
        assert len(routing_model.calls) == 2

        # Inserting a third entry evicts "hello two", the least recently used
        await router.select_agent_for_message("hello three", session_id="session-a")

        assert "session:session-a:hello one" in router._routing_cache
        assert "session:session-a:hello two" not in router._routing_cache
        assert "session:session-a:hello three" in router._routing_cache
