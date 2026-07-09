"""Unit tests for GBAC Phase 3: request-time resource filtering enforcement.

Covers the Phase 3 surfaces of the group-based access control PRD
(2026-07-06 revision):

1. Context -- the request-scoped permissions ContextVar and the no-op
   guarantee when no permissions are set (no groups/ directory).
2. Agents -- routing only sees permitted agents; a directly-addressed
   denied agent behaves exactly like an unknown agent; a user whose
   groups grant no agents gets a graceful reply; workflow decomposition
   and task assignment are constrained to permitted agents.
3. SOPs -- SOP matching and the analyzer's available-SOP list exclude
   SOPs the user's groups don't permit.
4. Triggers -- the API trigger route returns 403 for denied triggers.
5. MCP tools -- the per-turn tool surface passes through the group tool
   override cascade (``effective_tools``).
6. Single resolve -- permissions are resolved once per request by the
   overlord gate; enforcement sites read the context, not the resolver.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from muxi.runtime.datatypes.exceptions import NoAvailableAgentsError
from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.datatypes.workflow import SubTask
from muxi.runtime.formation.overlord.active_agents_tracker import ActiveAgentsTracker
from muxi.runtime.formation.overlord.agent_router import AgentRouter
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.formation.server.routes.client.triggers import (
    TriggerRequest,
    execute_trigger,
)
from muxi.runtime.formation.workflow.decomposer import TaskDecomposer
from muxi.runtime.formation.workflow.executor import WorkflowExecutor
from muxi.runtime.services.gbac import ResolvedPermissions, enforcement, load_groups

FORMATION_ID = "gbac-phase3-test"


def make_perms(tmp_path, files: dict, *group_ids: str) -> ResolvedPermissions:
    """Load group YAML files and build a ResolvedPermissions for group_ids."""
    groups_dir = tmp_path / "groups"
    groups_dir.mkdir(exist_ok=True)
    for filename, content in files.items():
        (groups_dir / filename).write_text(content)
    groups = load_groups(str(groups_dir))
    ordered = tuple(sorted(group_ids))
    return ResolvedPermissions(group_ids=ordered, groups=tuple(groups[gid] for gid in ordered))


@pytest.fixture(autouse=True)
def clean_permission_context():
    """Every test starts and ends with no request-scoped permissions/groups."""
    token = enforcement.set_current_permissions(None)
    groups_token = enforcement.set_request_groups(None)
    yield
    enforcement.reset_request_groups(groups_token)
    enforcement.reset_current_permissions(token)


class FakeResolver:
    """Counts resolve_request() calls and returns fixed permissions.

    Mimics PermissionResolver's request-resolution surface: groups arrive
    from the middleware (via the request context); ``None`` from
    resolve_request means "reject" (no groups + fallback: false).
    """

    def __init__(self, permissions: ResolvedPermissions, reject_without_groups: bool = False):
        self.permissions = permissions
        self.reject_without_groups = reject_without_groups
        self.calls = 0
        self.seen_groups: list = []

    def resolve_request(self, groups) -> ResolvedPermissions:
        self.calls += 1
        self.seen_groups.append(tuple(groups) if groups else ())
        if not groups and self.reject_without_groups:
            return None
        return self.permissions


# ===================================================================
# 1. Context helpers and no-op guarantees
# ===================================================================


class TestPermissionContext:
    def test_default_is_none(self):
        assert enforcement.get_current_permissions() is None

    def test_set_get_reset(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [a]\n"}, "g")
        token = enforcement.set_current_permissions(perms)
        assert enforcement.get_current_permissions() is perms
        enforcement.reset_current_permissions(token)
        assert enforcement.get_current_permissions() is None

    def test_is_allowed_true_without_permissions(self):
        assert enforcement.is_allowed("agents", "anything")
        assert enforcement.is_allowed("sops", "anything")
        assert enforcement.is_allowed("triggers", "anything")

    def test_filter_ids_passthrough_without_permissions(self):
        ids = ["a", "b", "c"]
        assert enforcement.filter_ids("agents", ids) == ids

    def test_filter_agent_registry_identity_without_permissions(self):
        registry = {"a": object(), "b": object()}
        assert enforcement.filter_agent_registry(registry) is registry

    def test_effective_tool_registry_identity_without_permissions(self):
        registry = {"server": {"tool": {"description": "x"}}}
        assert enforcement.effective_tool_registry("agent", registry) is registry


class TestFilterHelpers:
    def test_filter_ids_applies_permissions(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents:\n  - hr-*\n"}, "g")
        enforcement.set_current_permissions(perms)
        assert enforcement.filter_ids("agents", ["hr-assistant", "code-assistant"]) == [
            "hr-assistant"
        ]

    def test_filter_ids_empty_permissions_denies_everything(self):
        enforcement.set_current_permissions(ResolvedPermissions(group_ids=(), groups=()))
        assert enforcement.filter_ids("agents", ["a", "b"]) == []

    def test_filter_agent_registry_applies_permissions(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [b]\n"}, "g")
        enforcement.set_current_permissions(perms)
        registry = {"a": "agent-a", "b": "agent-b"}
        assert enforcement.filter_agent_registry(registry) == {"b": "agent-b"}


# ===================================================================
# 2. MCP tool surface (effective_tools cascade at planning time)
# ===================================================================


class TestEffectiveToolRegistry:
    REGISTRY = {
        "database-mcp": {
            "get_records": {"description": "read"},
            "update_records": {"description": "write"},
            "delete_records": {"description": "delete"},
        }
    }

    def test_group_wide_deny_removes_tools(self, tmp_path):
        perms = make_perms(
            tmp_path,
            {
                "g.yaml": (
                    "agents: [assistant]\n"
                    "mcp_servers:\n"
                    "  database-mcp:\n"
                    "    tools:\n"
                    "      deny: [delete_*, update_*]\n"
                )
            },
            "g",
        )
        enforcement.set_current_permissions(perms)
        filtered = enforcement.effective_tool_registry("assistant", self.REGISTRY)
        assert set(filtered["database-mcp"]) == {"get_records"}

    def test_agent_scoped_allow_supersedes_inherited(self, tmp_path):
        """An allow override expands against the catalog, not the inherited set."""
        perms = make_perms(
            tmp_path,
            {
                "g.yaml": (
                    "agents:\n"
                    "  - assistant:\n"
                    "      database-mcp:\n"
                    "        tools:\n"
                    "          allow: [get_records, delete_records]\n"
                )
            },
            "g",
        )
        enforcement.set_current_permissions(perms)
        # Inherited view lacks delete_records (attachment narrowed), but the
        # catalog has it -- the group override supersedes the attachment.
        inherited = {"database-mcp": {"get_records": {}, "update_records": {}}}
        filtered = enforcement.effective_tool_registry(
            "assistant", inherited, catalogs=self.REGISTRY
        )
        assert set(filtered["database-mcp"]) == {"get_records", "delete_records"}

    def test_denied_agent_has_empty_tool_surface(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [other-agent]\n"}, "g")
        enforcement.set_current_permissions(perms)
        filtered = enforcement.effective_tool_registry("assistant", self.REGISTRY)
        assert filtered == {}

    def test_hide_server_entirely(self, tmp_path):
        perms = make_perms(
            tmp_path,
            {
                "g.yaml": (
                    "agents: [assistant]\n"
                    "mcp_servers:\n"
                    "  database-mcp:\n"
                    "    tools:\n"
                    '      deny: "*"\n'
                )
            },
            "g",
        )
        enforcement.set_current_permissions(perms)
        filtered = enforcement.effective_tool_registry("assistant", self.REGISTRY)
        assert "database-mcp" not in filtered

    def test_no_override_keeps_inherited_tools(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [assistant]\n"}, "g")
        enforcement.set_current_permissions(perms)
        filtered = enforcement.effective_tool_registry("assistant", self.REGISTRY)
        assert set(filtered["database-mcp"]) == {
            "get_records",
            "update_records",
            "delete_records",
        }


# ===================================================================
# 3. Overlord permission gate (resolution + direct addressing)
# ===================================================================


def make_overlord_stub(resolver, agents: dict) -> Overlord:
    """Bare Overlord with just the attributes _apply_permission_gate needs."""
    overlord = Overlord.__new__(Overlord)
    overlord._configured_services = {"permission_resolver": resolver}
    overlord.agents = agents
    overlord.formation_id = FORMATION_ID
    return overlord


class TestPermissionGate:
    async def test_no_resolver_is_noop(self):
        overlord = make_overlord_stub(None, {"a": object()})
        assert await overlord._apply_permission_gate("alice", None) is None
        assert enforcement.get_current_permissions() is None

    async def test_no_user_id_is_noop(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [a]\n"}, "g")
        resolver = FakeResolver(perms)
        overlord = make_overlord_stub(resolver, {"a": object()})
        assert await overlord._apply_permission_gate(None, None) is None
        assert resolver.calls == 0
        assert enforcement.get_current_permissions() is None

    async def test_resolves_once_and_sets_context(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [a]\n"}, "g")
        resolver = FakeResolver(perms)
        overlord = make_overlord_stub(resolver, {"a": object(), "b": object()})

        # Middleware attached groups earlier in the pipeline
        enforcement.set_request_groups(("g",))
        assert await overlord._apply_permission_gate("Alice@Example.COM ", None) is None
        assert resolver.calls == 1
        assert resolver.seen_groups == [("g",)]
        assert enforcement.get_current_permissions() is perms

        # Enforcement sites read the context -- no further resolve calls
        assert enforcement.filter_ids("agents", ["a", "b"]) == ["a"]
        assert enforcement.is_allowed("agents", "a")
        assert resolver.calls == 1

    async def test_no_groups_without_fallback_returns_rejection(self, tmp_path):
        """No middleware-attached groups + fallback: false = rejected."""
        perms = make_perms(tmp_path, {"g.yaml": "agents: [a]\n"}, "g")
        resolver = FakeResolver(perms, reject_without_groups=True)
        overlord = make_overlord_stub(resolver, {"a": object()})

        response = await overlord._apply_permission_gate("alice", None)
        assert isinstance(response, MuxiResponse)
        assert response.metadata["reason"] == "no_groups"
        assert response.metadata["error_code"] == "AUTHORIZATION_FAILED"

    async def test_denied_direct_address_matches_unknown_agent_error(self, tmp_path):
        """Denied agent raises the exact error get_agent uses for unknown ids."""
        perms = make_perms(tmp_path, {"g.yaml": "agents: [a]\n"}, "g")
        overlord = make_overlord_stub(FakeResolver(perms), {"a": object(), "b": object()})

        with pytest.raises(ValueError) as denied:
            await overlord._apply_permission_gate("alice", "b")

        # Compare against the real unknown-agent error from get_agent()
        full_overlord = Overlord.__new__(Overlord)
        full_overlord.agents = {"a": object()}
        full_overlord.default_agent_id = "a"
        with pytest.raises(ValueError) as unknown:
            full_overlord.get_agent("b")

        assert str(denied.value) == str(unknown.value)

    async def test_no_permitted_agents_returns_graceful_response(self, tmp_path):
        perms = ResolvedPermissions(group_ids=(), groups=())  # no memberships
        overlord = make_overlord_stub(FakeResolver(perms), {"a": object(), "b": object()})

        response = await overlord._apply_permission_gate("stranger", None)
        assert isinstance(response, MuxiResponse)
        assert response.role == "assistant"
        assert response.content
        assert response.metadata["reason"] == "no_capabilities"

    async def test_gate_clears_stale_context_when_resolver_absent(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [a]\n"}, "g")
        enforcement.set_current_permissions(perms)
        overlord = make_overlord_stub(None, {"a": object()})
        await overlord._apply_permission_gate("alice", None)
        assert enforcement.get_current_permissions() is None


# ===================================================================
# 4. Agent routing
# ===================================================================


def make_router(agent_ids: list, metadata: Optional[dict] = None) -> AgentRouter:
    overlord = SimpleNamespace(
        agents={aid: object() for aid in agent_ids},
        active_agent_tracker=ActiveAgentsTracker(),
        formation_config={},
        agent_metadata=metadata or {},
        agent_descriptions={},
        default_agent_id=None,
        routing_model=None,
    )
    return AgentRouter(overlord)


class TestAgentRouterFiltering:
    async def test_routing_narrowed_to_single_permitted_agent(self, tmp_path):
        """With one permitted agent the router returns it without any LLM."""
        perms = make_perms(tmp_path, {"g.yaml": "agents: [hr-assistant]\n"}, "g")
        enforcement.set_current_permissions(perms)
        router = make_router(["hr-assistant", "code-assistant", "finance-assistant"])

        selected = await router.select_agent_for_message("show me salaries")
        assert selected == "hr-assistant"

    async def test_all_agents_denied_raises_no_available_agents(self):
        enforcement.set_current_permissions(ResolvedPermissions(group_ids=(), groups=()))
        router = make_router(["a", "b"])
        with pytest.raises(NoAvailableAgentsError):
            await router.select_agent_for_message("hello")

    async def test_no_permissions_behavior_unchanged(self):
        router = make_router(["only-agent"])
        assert await router.select_agent_for_message("hello") == "only-agent"

    async def test_fallback_selection_respects_permissions(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [code-assistant]\n"}, "g")
        enforcement.set_current_permissions(perms)
        metadata = {
            "hr-assistant": {"role": "specialist", "specialties": ["salaries"]},
            "code-assistant": {"role": "specialist", "specialties": ["deployments"]},
        }
        router = make_router(["hr-assistant", "code-assistant"], metadata)
        selected = await router._select_best_available_agent("tell me about salaries")
        assert selected == "code-assistant"


# ===================================================================
# 5. SOP matching
# ===================================================================


def make_sop_overlord(sops: list) -> Overlord:
    """Bare Overlord whose sop_system returns the given ranked SOP list."""
    overlord = Overlord.__new__(Overlord)
    captured = {}

    async def find_relevant_sops(message, top_k=3):
        captured["top_k"] = top_k
        return sops[:top_k]

    overlord.sop_system = SimpleNamespace(
        enabled=True,
        sops={sop["id"]: sop for sop in sops},
        find_relevant_sops=find_relevant_sops,
    )
    overlord._sop_captured = captured
    return overlord


class TestSopFiltering:
    SOPS = [
        {"id": "payroll-review", "name": "Payroll Review", "relevance_score": 0.95},
        {"id": "deploy-service", "name": "Deploy Service", "relevance_score": 0.85},
    ]

    async def test_denied_top_match_falls_through_to_permitted_sop(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "sops: [deploy-*]\n"}, "g")
        enforcement.set_current_permissions(perms)
        overlord = make_sop_overlord(self.SOPS)

        sop = await overlord._find_relevant_sop("how do I deploy?")
        assert sop is not None
        assert sop["id"] == "deploy-service"
        # Over-fetches candidates so a denied #1 can't hide a permitted #2
        assert overlord._sop_captured["top_k"] > 1

    async def test_all_matches_denied_returns_none(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "sops: [onboarding]\n"}, "g")
        enforcement.set_current_permissions(perms)
        overlord = make_sop_overlord(self.SOPS)
        assert await overlord._find_relevant_sop("payroll?") is None

    async def test_no_permissions_returns_top_match_with_topk_one(self):
        overlord = make_sop_overlord(self.SOPS)
        sop = await overlord._find_relevant_sop("payroll?")
        assert sop["id"] == "payroll-review"
        assert overlord._sop_captured["top_k"] == 1


# ===================================================================
# 6. Trigger route (API channel: 403 on denial)
# ===================================================================


def make_trigger_request(user_id: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/triggers/hr-report",
        "raw_path": b"/v1/triggers/hr-report",
        "query_string": b"",
        "headers": [(b"x-muxi-user-id", user_id.encode())],
    }
    return Request(scope)


def make_trigger_formation(tmp_path, resolver) -> SimpleNamespace:
    return SimpleNamespace(
        formation_id=FORMATION_ID,
        permission_resolver=resolver,
        is_overlord_running=lambda: True,
        get_formation_path=lambda: str(tmp_path),
        _overlord=None,
    )


class TestTriggerRouteEnforcement:
    async def test_denied_trigger_returns_403(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "triggers: [invoice-*]\n"}, "g")
        formation = make_trigger_formation(tmp_path, FakeResolver(perms))
        request = make_trigger_request("carol@example.com")
        request.scope["app"] = SimpleNamespace(state=SimpleNamespace(formation=formation))

        with pytest.raises(HTTPException) as exc_info:
            await execute_trigger(
                "hr-report",
                request,
                TriggerRequest(data={}),
                BackgroundTasks(),
            )
        assert exc_info.value.status_code == 403
        # Generic message: no resource enumeration in the detail
        assert "hr-report" not in exc_info.value.detail

    async def test_permitted_trigger_passes_gate(self, tmp_path):
        """A permitted trigger clears the gate (then 404s on the missing file)."""
        perms = make_perms(tmp_path, {"g.yaml": "triggers: [hr-report]\n"}, "g")
        formation = make_trigger_formation(tmp_path, FakeResolver(perms))
        request = make_trigger_request("alice@example.com")
        request.scope["app"] = SimpleNamespace(state=SimpleNamespace(formation=formation))

        with pytest.raises(HTTPException) as exc_info:
            await execute_trigger(
                "hr-report",
                request,
                TriggerRequest(data={}),
                BackgroundTasks(),
            )
        assert exc_info.value.status_code == 404

    async def test_no_resolver_skips_gate(self, tmp_path):
        formation = make_trigger_formation(tmp_path, None)
        request = make_trigger_request("anyone")
        request.scope["app"] = SimpleNamespace(state=SimpleNamespace(formation=formation))

        with pytest.raises(HTTPException) as exc_info:
            await execute_trigger(
                "hr-report",
                request,
                TriggerRequest(data={}),
                BackgroundTasks(),
            )
        assert exc_info.value.status_code == 404


# ===================================================================
# 7. Workflow decomposition and task assignment
# ===================================================================


class TestWorkflowFiltering:
    @staticmethod
    def _agents():
        return {
            "hr-assistant": SimpleNamespace(
                agent_id="hr-assistant",
                name="HR Assistant",
                description="Handles HR data",
                role="specialist",
                specialties=["hr"],
            ),
            "code-assistant": SimpleNamespace(
                agent_id="code-assistant",
                name="Code Assistant",
                description="Handles engineering",
                role="specialist",
                specialties=["engineering"],
            ),
        }

    def test_decomposer_capabilities_exclude_denied_agents(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [code-assistant]\n"}, "g")
        enforcement.set_current_permissions(perms)
        decomposer = TaskDecomposer(agent_registry=self._agents())

        info = decomposer._get_available_capabilities_info()
        assert "code-assistant" in info
        assert "hr-assistant" not in info

    def test_decomposer_unchanged_without_permissions(self):
        decomposer = TaskDecomposer(agent_registry=self._agents())
        info = decomposer._get_available_capabilities_info()
        assert "code-assistant" in info
        assert "hr-assistant" in info

    def test_executor_never_assigns_denied_agent(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [code-assistant]\n"}, "g")
        enforcement.set_current_permissions(perms)
        executor = WorkflowExecutor(agent_registry=self._agents())

        # Even a plan that explicitly names the denied agent can't reach it
        task = SubTask(
            id="task_1",
            description="summarize salaries",
            required_capabilities=["hr"],
            assigned_agent_id="hr-assistant",
        )
        selected = executor._select_agent_for_task(task)
        assert selected is not None
        assert selected.agent_id == "code-assistant"

        # Registry swap is restored after selection
        assert set(executor.agent_registry) == {"hr-assistant", "code-assistant"}

    def test_executor_unchanged_without_permissions(self):
        executor = WorkflowExecutor(agent_registry=self._agents())
        task = SubTask(
            id="task_1",
            description="summarize salaries",
            required_capabilities=["hr"],
            assigned_agent_id="hr-assistant",
        )
        selected = executor._select_agent_for_task(task)
        assert selected.agent_id == "hr-assistant"


class TestNestedReentryPreservesPermissions:
    """Internal re-entries must not un-filter the outer request.

    _process_sync_chat re-enters itself synchronously with user_id=None;
    ContextVar mutations are visible within the same coroutine, so the
    gate must inherit (not clear) the outer requester's permissions
    (review follow-up on #207).
    """

    async def test_gate_with_none_user_inherits_outer_context(self, tmp_path):
        perms = make_perms(tmp_path, {"g.yaml": "agents: [a]\n"}, "g")
        resolver = FakeResolver(perms)
        overlord = make_overlord_stub(resolver, {"a": object()})

        await overlord._apply_permission_gate("alice", None)
        assert enforcement.get_current_permissions() is perms

        # Nested internal re-entry: gate returns None (the caller treats
        # any non-None return as a MuxiResponse) while the outer
        # permissions survive untouched in the context
        result = await overlord._apply_permission_gate(None, None)
        assert result is None
        assert enforcement.get_current_permissions() is perms
        assert resolver.calls == 1  # no second resolve

        enforcement.set_current_permissions(None)
