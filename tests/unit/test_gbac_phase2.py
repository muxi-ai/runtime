"""Unit tests for GBAC Phase 2: group loading and the permission resolution engine.

Covers the Phase 2 surfaces of the group-based access control PRD
(2026-07-06 revision):

1. Parsing -- the simplified group file format: plain-list shorthand, "*",
   long form {allow, deny}, agent grant+override entries, mcp_servers
   overrides, memory.write, and precise fail-fast errors for malformed files.
2. Inheritance -- parents resolve first, child overlays additively, child
   deny overrides parent allow, tool override blocks supersede per key,
   circular and unknown parents are load-time errors.
3. Resolution -- multi-group union of allows, any-deny-wins, fnmatch globs,
   the four-level tool override cascade, and empty-membership behavior.
4. Resolver -- membership TTL cache, LRU resolution cache, unknown
   membership group ids, and formation wiring (auto-discovery).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
from muxi.runtime.formation.formation import Formation
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.gbac import (
    GroupPermissionError,
    PermissionResolver,
    ResolvedPermissions,
    load_groups,
)
from muxi.runtime.services.memory.long_term import UserGroup

FORMATION_ID = "gbac-phase2-test"


def make_groups(tmp_path, files: dict) -> dict:
    """Write group YAML files into tmp_path/groups and load them."""
    groups_dir = tmp_path / "groups"
    groups_dir.mkdir(exist_ok=True)
    for filename, content in files.items():
        (groups_dir / filename).write_text(content)
    return load_groups(str(groups_dir))


def perms_for(groups: dict, *group_ids: str) -> ResolvedPermissions:
    """Build a ResolvedPermissions for a combination of loaded groups."""
    ordered = tuple(sorted(group_ids))
    return ResolvedPermissions(group_ids=ordered, groups=tuple(groups[gid] for gid in ordered))


class TestGroupFileParsing:
    """Parsing: the simplified group definition format."""

    def test_plain_list_is_allow_list(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {"analyst.yaml": "agents:\n  - researcher\n  - report-writer\n"},
        )
        rules = groups["analyst"].agents
        assert rules.specified
        assert rules.allow == ("researcher", "report-writer")
        assert rules.deny == ()

    def test_group_id_is_filename_stem(self, tmp_path):
        groups = make_groups(tmp_path, {"read-only.yml": 'sops: "*"\n'})
        assert set(groups) == {"read-only"}
        assert groups["read-only"].group_id == "read-only"

    def test_star_string_section(self, tmp_path):
        groups = make_groups(tmp_path, {"admin.yaml": 'sops: "*"\n'})
        assert groups["admin"].sops.allow == ("*",)

    def test_long_form_allow_and_deny(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {"ops.yaml": ("triggers:\n" '  allow: ["*"]\n' "  deny: [deploy-*]\n")},
        )
        rules = groups["ops"].triggers
        assert rules.allow == ("*",)
        assert rules.deny == ("deploy-*",)

    def test_long_form_scalar_deny(self, tmp_path):
        """The PRD writes tools: {deny: \"*\"}; scalar strings normalize to lists."""
        groups = make_groups(
            tmp_path,
            {"locked.yaml": 'mcp_servers:\n  database-mcp:\n    tools:\n      deny: "*"\n'},
        )
        rules = groups["locked"].mcp_servers["database-mcp"]
        assert rules.allow is None
        assert rules.deny == ("*",)

    def test_optional_metadata_fields(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "analyst.yaml": (
                    'name: "Business Analyst"\n'
                    'description: "Analysis and reporting"\n'
                    "agents: [researcher]\n"
                )
            },
        )
        group = groups["analyst"]
        assert group.name == "Business Analyst"
        assert group.description == "Analysis and reporting"

    def test_agent_entry_with_tool_override(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "analyst.yaml": (
                    "agents:\n"
                    "  - researcher\n"
                    "  - db-assistant:\n"
                    "      database-mcp:\n"
                    "        tools:\n"
                    "          allow: [get_financials, list_orders]\n"
                )
            },
        )
        group = groups["analyst"]
        # The dict entry grants the agent AND records the override
        assert group.agents.allow == ("researcher", "db-assistant")
        override = group.agent_tool_overrides["db-assistant"]["database-mcp"]
        assert override.allow == ("get_financials", "list_orders")
        assert override.deny is None

    def test_agent_entry_with_empty_body_is_plain_grant(self, tmp_path):
        """``- some-agent:`` with no body parses as a plain grant."""
        groups = make_groups(tmp_path, {"g.yaml": "agents:\n  - helper:\n"})
        assert groups["g"].agents.allow == ("helper",)
        assert groups["g"].agent_tool_overrides == {}

    def test_mcp_servers_group_wide_override(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "analyst.yaml": (
                    "mcp_servers:\n"
                    "  database-mcp:\n"
                    "    tools:\n"
                    "      deny: [update_*, delete_*]\n"
                )
            },
        )
        rules = groups["analyst"].mcp_servers["database-mcp"]
        assert rules.allow is None
        assert rules.deny == ("update_*", "delete_*")

    def test_memory_write_parsing(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {"analyst.yaml": "memory:\n  write: [group:analyst, group:shared]\n"},
        )
        assert groups["analyst"].memory_write == ("group:analyst", "group:shared")

    def test_memory_write_scalar(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": "memory:\n  write: group:g\n"})
        assert groups["g"].memory_write == ("group:g",)

    def test_empty_file_is_valid_empty_group(self, tmp_path):
        groups = make_groups(tmp_path, {"inactive.yaml": ""})
        group = groups["inactive"]
        assert not group.agents.specified
        assert group.agents.allow == ()

    def test_non_yaml_files_are_ignored(self, tmp_path):
        groups_dir = tmp_path / "groups"
        groups_dir.mkdir()
        (groups_dir / "notes.md").write_text("# not a group")
        (groups_dir / "real.yaml").write_text("agents: [a]\n")
        groups = load_groups(str(groups_dir))
        assert set(groups) == {"real"}


class TestGroupFileErrors:
    """Parsing: malformed files fail with errors naming file and problem."""

    def assert_error(self, tmp_path, files: dict, *fragments: str):
        with pytest.raises(GroupPermissionError) as exc_info:
            make_groups(tmp_path, files)
        message = str(exc_info.value)
        for fragment in fragments:
            assert fragment in message, f"{fragment!r} not in error: {message}"

    def test_invalid_yaml_names_file(self, tmp_path):
        self.assert_error(tmp_path, {"bad.yaml": "agents: [unclosed\n"}, "bad.yaml", "invalid YAML")

    def test_non_mapping_top_level(self, tmp_path):
        self.assert_error(tmp_path, {"bad.yaml": "- just\n- a\n- list\n"}, "bad.yaml", "mapping")

    def test_unknown_top_level_key(self, tmp_path):
        self.assert_error(
            tmp_path, {"bad.yaml": "agent: [typo]\n"}, "bad.yaml", "unknown key", "agent"
        )

    def test_unknown_rule_key_in_long_form(self, tmp_path):
        self.assert_error(
            tmp_path,
            {"bad.yaml": "triggers:\n  whitelist: [x]\n"},
            "bad.yaml",
            "'allow' and 'deny'",
        )

    def test_non_string_section_entry(self, tmp_path):
        self.assert_error(tmp_path, {"bad.yaml": "sops:\n  - 42\n"}, "bad.yaml", "sops", "entry 0")

    def test_agent_entry_multi_key_dict(self, tmp_path):
        self.assert_error(
            tmp_path,
            {"bad.yaml": "agents:\n  - a: {m: {tools: {allow: [t]}}}\n    b: {}\n"},
            "bad.yaml",
            "single-key",
        )

    def test_mcp_server_missing_tools_key(self, tmp_path):
        self.assert_error(
            tmp_path,
            {"bad.yaml": "mcp_servers:\n  db:\n    allow: [x]\n"},
            "bad.yaml",
            "'tools'",
        )

    def test_empty_tools_block(self, tmp_path):
        self.assert_error(
            tmp_path,
            {"bad.yaml": "mcp_servers:\n  db:\n    tools: {}\n"},
            "bad.yaml",
            "allow",
        )

    def test_memory_unknown_key(self, tmp_path):
        self.assert_error(tmp_path, {"bad.yaml": "memory:\n  read: [x]\n"}, "bad.yaml", "write")

    def test_duplicate_group_stems(self, tmp_path):
        self.assert_error(
            tmp_path,
            {"dup.yaml": "agents: [a]\n", "dup.yml": "agents: [b]\n"},
            "duplicate group id 'dup'",
        )


class TestInheritance:
    """Inheritance: parents first, child overlays, deny is sticky."""

    def test_child_inherits_parent_allows(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "base.yaml": "agents: [helper]\nsops: [onboarding]\n",
                "analyst.yaml": "inherits: base\nagents: [researcher]\n",
            },
        )
        perms = perms_for(groups, "analyst")
        assert perms.is_allowed("agents", "helper")
        assert perms.is_allowed("agents", "researcher")
        assert perms.is_allowed("sops", "onboarding")

    def test_child_deny_overrides_parent_allow(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "base.yaml": 'agents: "*"\n',
                "restricted.yaml": ("inherits: base\nagents:\n  deny: [hr-assistant]\n"),
            },
        )
        perms = perms_for(groups, "restricted")
        assert perms.is_allowed("agents", "code-assistant")
        assert not perms.is_allowed("agents", "hr-assistant")

    def test_parent_deny_is_sticky(self, tmp_path):
        """A child allow cannot resurrect a parent's deny (deny wins)."""
        groups = make_groups(
            tmp_path,
            {
                "base.yaml": 'agents:\n  allow: ["*"]\n  deny: [hr-assistant]\n',
                "child.yaml": "inherits: base\nagents: [hr-assistant]\n",
            },
        )
        assert not perms_for(groups, "child").is_allowed("agents", "hr-assistant")

    def test_inherits_list_of_parents(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "a.yaml": "agents: [agent-a]\n",
                "b.yaml": "triggers: [trigger-b]\n",
                "both.yaml": "inherits: [a, b]\nsops: [sop-c]\n",
            },
        )
        perms = perms_for(groups, "both")
        assert perms.is_allowed("agents", "agent-a")
        assert perms.is_allowed("triggers", "trigger-b")
        assert perms.is_allowed("sops", "sop-c")

    def test_transitive_inheritance(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "a.yaml": "agents: [agent-a]\n",
                "b.yaml": "inherits: a\nagents: [agent-b]\n",
                "c.yaml": "inherits: b\nagents: [agent-c]\n",
            },
        )
        perms = perms_for(groups, "c")
        for agent in ("agent-a", "agent-b", "agent-c"):
            assert perms.is_allowed("agents", agent)

    def test_circular_inheritance_names_cycle(self, tmp_path):
        with pytest.raises(GroupPermissionError) as exc_info:
            make_groups(
                tmp_path,
                {
                    "a.yaml": "inherits: b\n",
                    "b.yaml": "inherits: c\n",
                    "c.yaml": "inherits: a\n",
                },
            )
        message = str(exc_info.value)
        assert "Circular group inheritance" in message
        for gid in ("a", "b", "c"):
            assert gid in message

    def test_self_inheritance_is_a_cycle(self, tmp_path):
        with pytest.raises(GroupPermissionError, match="Circular"):
            make_groups(tmp_path, {"a.yaml": "inherits: a\n"})

    def test_unknown_parent_errors(self, tmp_path):
        with pytest.raises(GroupPermissionError) as exc_info:
            make_groups(tmp_path, {"a.yaml": "inherits: nonexistent\n"})
        message = str(exc_info.value)
        assert "nonexistent" in message
        assert "a.yaml" in message

    def test_tool_override_supersedes_on_inherit(self, tmp_path):
        """Child's tools block for the same server replaces the parent's."""
        groups = make_groups(
            tmp_path,
            {
                "base.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      deny: [delete_*]\n"
                ),
                "child.yaml": (
                    "inherits: base\n" "mcp_servers:\n  db:\n    tools:\n      allow: [get_*]\n"
                ),
            },
        )
        child = groups["child"]
        assert child.mcp_servers["db"].allow == ("get_*",)
        assert child.mcp_servers["db"].deny is None  # parent's block replaced

    def test_tool_override_inherited_when_child_silent(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "base.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      deny: [delete_*]\n"
                ),
                "child.yaml": "inherits: base\n",
            },
        )
        assert groups["child"].mcp_servers["db"].deny == ("delete_*",)

    def test_memory_write_unions_on_inherit(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "base.yaml": "memory:\n  write: [group:base]\n",
                "child.yaml": "inherits: base\nmemory:\n  write: [group:child]\n",
            },
        )
        perms = perms_for(groups, "child")
        assert perms.memory_write_scopes == ("group:base", "group:child")


class TestMultiGroupResolution:
    """Resolution: union of allows across groups, any deny wins."""

    def test_union_of_allows(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "eng.yaml": "agents: [code-assistant]\n",
                "atlas.yaml": "agents: [project-assistant]\n",
            },
        )
        perms = perms_for(groups, "eng", "atlas")
        assert perms.is_allowed("agents", "code-assistant")
        assert perms.is_allowed("agents", "project-assistant")
        assert not perms.is_allowed("agents", "hr-assistant")

    def test_any_group_deny_wins(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "broad.yaml": 'agents: "*"\n',
                "narrow.yaml": "agents:\n  deny: [hr-assistant]\n",
            },
        )
        perms = perms_for(groups, "broad", "narrow")
        assert perms.is_allowed("agents", "code-assistant")
        assert not perms.is_allowed("agents", "hr-assistant")

    def test_wildcard_globs(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "ops.yaml": (
                    "triggers:\n" '  allow: ["report-*", "invoice-??"]\n' '  deny: ["report-x*"]\n'
                )
            },
        )
        perms = perms_for(groups, "ops")
        assert perms.is_allowed("triggers", "report-daily")
        assert perms.is_allowed("triggers", "report-")  # '*' matches empty
        assert not perms.is_allowed("triggers", "report-x1")  # deny glob
        assert perms.is_allowed("triggers", "invoice-42")  # '?' one char each
        assert not perms.is_allowed("triggers", "invoice-1")
        assert not perms.is_allowed("triggers", "Report-daily")  # case-sensitive

    def test_empty_membership_denies_everything(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": 'agents: "*"\n'})
        perms = perms_for(groups)  # no groups: registered but inactive
        assert not perms.has_groups
        assert not perms.is_allowed("agents", "anything")
        assert not perms.is_allowed("native_apps", "memory-visualizer")
        assert perms.memory_write_scopes == ()
        assert perms.effective_tools("agent", "mcp", ["t1", "t2"]) == set()

    def test_native_apps_unspecified_allows_all(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": "agents: [a]\n"})
        assert perms_for(groups, "g").is_allowed("native_apps", "memory-visualizer")

    def test_native_apps_specified_restricts(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": "native_apps:\n  - memory-visualizer\n"})
        perms = perms_for(groups, "g")
        assert perms.is_allowed("native_apps", "memory-visualizer")
        assert not perms.is_allowed("native_apps", "formation-editor")

    def test_filter_preserves_order(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": "agents: [b, a]\n"})
        perms = perms_for(groups, "g")
        assert perms.filter("agents", ["a", "x", "b"]) == ["a", "b"]

    def test_unknown_kind_raises(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": "agents: [a]\n"})
        with pytest.raises(KeyError):
            perms_for(groups, "g").is_allowed("workflows", "x")

    def test_memory_write_union_across_groups(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "a.yaml": "memory:\n  write: [group:a, group:shared]\n",
                "b.yaml": "memory:\n  write: [group:b, group:shared]\n",
            },
        )
        perms = perms_for(groups, "a", "b")
        assert set(perms.memory_write_scopes) == {"group:a", "group:b", "group:shared"}


INHERITED = ["get_financials", "list_orders", "update_order", "delete_order"]


class TestToolOverrideCascade:
    """The four-level tool override cascade and cross-group merge."""

    def test_no_override_passes_inherited_through(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": "agents: [db-assistant]\n"})
        perms = perms_for(groups, "g")
        assert perms.effective_tools("db-assistant", "db", INHERITED) == set(INHERITED)

    def test_group_wide_deny_subtracts_from_inherited(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "g.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      deny: [update_*, delete_*]\n"
                )
            },
        )
        perms = perms_for(groups, "g")
        assert perms.effective_tools("db-assistant", "db", INHERITED) == {
            "get_financials",
            "list_orders",
        }

    def test_allow_alone_is_exactly_that_set(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "g.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      allow: [get_financials]\n"
                )
            },
        )
        perms = perms_for(groups, "g")
        assert perms.effective_tools("db-assistant", "db", INHERITED) == {"get_financials"}

    def test_allow_supersedes_not_intersects(self, tmp_path):
        """An allow can reach catalog tools the attachment config excluded."""
        groups = make_groups(
            tmp_path,
            {
                "g.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      allow: [run_report]\n"
                )
            },
        )
        perms = perms_for(groups, "g")
        catalog = INHERITED + ["run_report"]
        # run_report is outside the attachment surface but in the catalog:
        # the group override supersedes the attachment config.
        effective = perms.effective_tools("db-assistant", "db", INHERITED, catalog=catalog)
        assert effective == {"run_report"}

    def test_allow_and_deny_is_allow_then_subtract(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "g.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n"
                    '      allow: ["*_order", get_financials]\n'
                    "      deny: [delete_order]\n"
                )
            },
        )
        perms = perms_for(groups, "g")
        assert perms.effective_tools("db-assistant", "db", INHERITED) == {
            "update_order",
            "get_financials",
        }

    def test_deny_star_hides_server(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "g.yaml": (
                    "agents: [db-assistant]\n" 'mcp_servers:\n  db:\n    tools:\n      deny: "*"\n'
                )
            },
        )
        perms = perms_for(groups, "g")
        assert perms.effective_tools("db-assistant", "db", INHERITED) == set()

    def test_agent_scoped_override_beats_group_wide(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "g.yaml": (
                    "agents:\n"
                    "  - db-assistant:\n"
                    "      db:\n"
                    "        tools:\n"
                    "          allow: [get_financials]\n"
                    "mcp_servers:\n  db:\n    tools:\n      deny: [get_*]\n"
                )
            },
        )
        perms = perms_for(groups, "g")
        # The agent-scoped block wins for db-assistant on db
        assert perms.effective_tools("db-assistant", "db", INHERITED) == {"get_financials"}

    def test_group_wide_applies_to_other_granted_agents(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "g.yaml": (
                    "agents:\n"
                    "  - other-agent\n"
                    "  - db-assistant:\n"
                    "      db:\n"
                    "        tools:\n"
                    "          allow: [get_financials]\n"
                    "mcp_servers:\n  db:\n    tools:\n      deny: [delete_*]\n"
                )
            },
        )
        perms = perms_for(groups, "g")
        # other-agent has no agent-scoped block; group-wide deny applies
        assert perms.effective_tools("other-agent", "db", INHERITED) == {
            "get_financials",
            "list_orders",
            "update_order",
        }

    def test_cross_group_union_of_effective_sets(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "a.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      allow: [get_financials]\n"
                ),
                "b.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      allow: [list_orders]\n"
                ),
            },
        )
        perms = perms_for(groups, "a", "b")
        assert perms.effective_tools("db-assistant", "db", INHERITED) == {
            "get_financials",
            "list_orders",
        }

    def test_cross_group_any_deny_wins(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "open.yaml": "agents: [db-assistant]\n",
                "strict.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      deny: [delete_*]\n"
                ),
            },
        )
        perms = perms_for(groups, "open", "strict")
        # open contributes the full inherited set, but strict's deny wins
        assert perms.effective_tools("db-assistant", "db", INHERITED) == {
            "get_financials",
            "list_orders",
            "update_order",
        }

    def test_non_granting_group_does_not_contribute(self, tmp_path):
        """A group that doesn't grant the agent joins neither allows nor denies."""
        groups = make_groups(
            tmp_path,
            {
                "granting.yaml": (
                    "agents: [db-assistant]\n"
                    "mcp_servers:\n  db:\n    tools:\n      allow: [get_financials]\n"
                ),
                "unrelated.yaml": (
                    "agents: [other-agent]\n" 'mcp_servers:\n  db:\n    tools:\n      deny: "*"\n'
                ),
            },
        )
        perms = perms_for(groups, "granting", "unrelated")
        # unrelated's server-wide deny does not apply: it grants no access
        # to db-assistant in the first place ("every granted agent").
        assert perms.effective_tools("db-assistant", "db", INHERITED) == {"get_financials"}

    def test_agent_denying_group_does_not_contribute(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "granting.yaml": "agents: [db-assistant]\n",
                "denying.yaml": "agents:\n  deny: [db-assistant]\n",
            },
        )
        perms = perms_for(groups, "granting", "denying")
        # Agent-level deny wins everywhere: is_allowed and effective_tools
        # must agree, so a globally denied agent has an EMPTY tool surface
        # even though another group grants it (review follow-up on #204).
        assert not perms.is_allowed("agents", "db-assistant")
        assert perms.effective_tools("db-assistant", "db", INHERITED) == set()


@pytest.fixture
def membership_db(tmp_path):
    """File-backed SQLite DatabaseManager with the user_groups table."""
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/gbac.db")
    Base.metadata.create_all(db_manager.engine, tables=[UserGroup.__table__])
    yield db_manager
    db_manager.engine.dispose()


def add_membership(db_manager, user_id: str, group_id: str) -> None:
    Session = sessionmaker(bind=db_manager.engine)
    with Session() as session:
        session.add(UserGroup(user_id=user_id, group_id=group_id, formation_id=FORMATION_ID))
        session.commit()


def make_resolver(groups: dict, db_manager, **kwargs) -> PermissionResolver:
    return PermissionResolver(
        groups=groups,
        formation_id=FORMATION_ID,
        db_manager_getter=lambda: db_manager,
        **kwargs,
    )


class TestPermissionResolver:
    """Resolver: membership lookup, TTL cache, LRU resolution cache."""

    async def test_resolve_user_with_memberships(self, tmp_path, membership_db):
        groups = make_groups(
            tmp_path,
            {"hr.yaml": "agents: [hr-assistant]\n", "eng.yaml": "agents: [code-assistant]\n"},
        )
        add_membership(membership_db, "alice@example.com", "hr")
        resolver = make_resolver(groups, membership_db)

        perms = await resolver.resolve("alice@example.com")
        assert perms.group_ids == ("hr",)
        assert perms.is_allowed("agents", "hr-assistant")
        assert not perms.is_allowed("agents", "code-assistant")

    async def test_resolve_multi_group_user(self, tmp_path, membership_db):
        groups = make_groups(
            tmp_path,
            {"eng.yaml": "agents: [code-assistant]\n", "atlas.yaml": "agents: [atlas-bot]\n"},
        )
        add_membership(membership_db, "dave@example.com", "eng")
        add_membership(membership_db, "dave@example.com", "atlas")
        resolver = make_resolver(groups, membership_db)

        perms = await resolver.resolve("dave@example.com")
        assert perms.group_ids == ("atlas", "eng")
        assert perms.is_allowed("agents", "code-assistant")
        assert perms.is_allowed("agents", "atlas-bot")

    async def test_empty_membership_resolves_to_empty_permissions(self, tmp_path, membership_db):
        groups = make_groups(tmp_path, {"g.yaml": 'agents: "*"\n'})
        resolver = make_resolver(groups, membership_db)

        perms = await resolver.resolve("nobody@example.com")
        assert perms.group_ids == ()
        assert not perms.has_groups
        assert not perms.is_allowed("agents", "anything")

    async def test_unknown_membership_group_grants_nothing(self, tmp_path, membership_db):
        groups = make_groups(tmp_path, {"real.yaml": "agents: [a]\n"})
        add_membership(membership_db, "bob@example.com", "real")
        add_membership(membership_db, "bob@example.com", "ghost")  # no ghost.yaml
        resolver = make_resolver(groups, membership_db)

        perms = await resolver.resolve("bob@example.com")
        assert perms.group_ids == ("real",)

    async def test_membership_ttl_caches_within_window(self, tmp_path, membership_db):
        groups = make_groups(tmp_path, {"a.yaml": "agents: [x]\n", "b.yaml": "agents: [y]\n"})
        add_membership(membership_db, "carol@example.com", "a")
        resolver = make_resolver(groups, membership_db, membership_ttl=60.0)

        perms = await resolver.resolve("carol@example.com")
        assert perms.group_ids == ("a",)

        # New membership is invisible while the TTL cache is warm
        add_membership(membership_db, "carol@example.com", "b")
        perms = await resolver.resolve("carol@example.com")
        assert perms.group_ids == ("a",)

        # Invalidation forces a fresh lookup
        resolver.invalidate_memberships("carol@example.com")
        perms = await resolver.resolve("carol@example.com")
        assert perms.group_ids == ("a", "b")

    async def test_membership_ttl_expires(self, tmp_path, membership_db):
        groups = make_groups(tmp_path, {"a.yaml": "agents: [x]\n", "b.yaml": "agents: [y]\n"})
        add_membership(membership_db, "erin@example.com", "a")
        resolver = make_resolver(groups, membership_db, membership_ttl=0.05)

        perms = await resolver.resolve("erin@example.com")
        assert perms.group_ids == ("a",)

        add_membership(membership_db, "erin@example.com", "b")
        await asyncio.sleep(0.06)
        perms = await resolver.resolve("erin@example.com")
        assert perms.group_ids == ("a", "b")

    async def test_resolution_cached_per_group_combination(self, tmp_path, membership_db):
        groups = make_groups(tmp_path, {"a.yaml": "agents: [x]\n", "b.yaml": "agents: [y]\n"})
        add_membership(membership_db, "u1@example.com", "a")
        add_membership(membership_db, "u2@example.com", "a")
        add_membership(membership_db, "u3@example.com", "b")
        resolver = make_resolver(groups, membership_db)

        p1 = await resolver.resolve("u1@example.com")
        p2 = await resolver.resolve("u2@example.com")
        p3 = await resolver.resolve("u3@example.com")
        assert p1 is p2  # same combination -> same cached object
        assert p1 is not p3

    async def test_resolve_without_database_raises(self, tmp_path):
        groups = make_groups(tmp_path, {"g.yaml": "agents: [a]\n"})
        resolver = PermissionResolver(
            groups=groups,
            formation_id=FORMATION_ID,
            db_manager_getter=lambda: None,
        )
        with pytest.raises(RuntimeError, match="no persistent database"):
            await resolver.resolve("alice@example.com")


class TestFormationWiring:
    """Auto-discovery: _setup_groups activates iff groups/ exists."""

    @staticmethod
    def _formation_stub(tmp_path) -> SimpleNamespace:
        return SimpleNamespace(
            _formation_path=str(tmp_path),
            _permission_resolver=None,
            _group_permissions={},
            formation_id=FORMATION_ID,
            config={"runtime": {}},
            # Group files require the auth gate (see
            # test_gbac_auth_groups_validation.py for the rule itself)
            _server_config={"auth": "required"},
        )

    def test_no_groups_dir_is_inert(self, tmp_path):
        stub = self._formation_stub(tmp_path)
        Formation._setup_groups(stub)
        assert stub._permission_resolver is None
        assert stub._group_permissions == {}

    def test_groups_dir_activates_resolver(self, tmp_path):
        (tmp_path / "groups").mkdir()
        (tmp_path / "groups" / "analyst.yaml").write_text("agents: [researcher]\n")
        stub = self._formation_stub(tmp_path)
        Formation._setup_groups(stub)
        assert stub._permission_resolver is not None
        assert stub._permission_resolver.group_ids == ("analyst",)

    def test_groups_dir_next_to_formation_file(self, tmp_path):
        """When the formation path is a file, groups/ sits in its directory."""
        formation_file = tmp_path / "formation.afs"
        formation_file.write_text("id: test\n")
        (tmp_path / "groups").mkdir()
        (tmp_path / "groups" / "g.yaml").write_text("agents: [a]\n")
        stub = self._formation_stub(tmp_path)
        stub._formation_path = str(formation_file)
        Formation._setup_groups(stub)
        assert stub._permission_resolver is not None

    def test_empty_groups_dir_is_inert(self, tmp_path):
        (tmp_path / "groups").mkdir()
        stub = self._formation_stub(tmp_path)
        Formation._setup_groups(stub)
        assert stub._permission_resolver is None

    def test_malformed_group_file_fails_load(self, tmp_path):
        (tmp_path / "groups").mkdir()
        (tmp_path / "groups" / "bad.yaml").write_text("agent: [typo]\n")
        stub = self._formation_stub(tmp_path)
        with pytest.raises(ConfigurationValidationError) as exc_info:
            Formation._setup_groups(stub)
        assert "bad.yaml" in str(exc_info.value)

    def test_circular_inheritance_fails_load(self, tmp_path):
        (tmp_path / "groups").mkdir()
        (tmp_path / "groups" / "a.yaml").write_text("inherits: b\n")
        (tmp_path / "groups" / "b.yaml").write_text("inherits: a\n")
        stub = self._formation_stub(tmp_path)
        with pytest.raises(ConfigurationValidationError) as exc_info:
            Formation._setup_groups(stub)
        assert "Circular" in str(exc_info.value)

    def test_setup_groups_is_idempotent(self, tmp_path):
        (tmp_path / "groups").mkdir()
        (tmp_path / "groups" / "g.yaml").write_text("agents: [a]\n")
        stub = self._formation_stub(tmp_path)
        Formation._setup_groups(stub)
        resolver = stub._permission_resolver
        Formation._setup_groups(stub)
        assert stub._permission_resolver is resolver

    def test_membership_ttl_configurable_via_runtime(self, tmp_path):
        (tmp_path / "groups").mkdir()
        (tmp_path / "groups" / "g.yaml").write_text("agents: [a]\n")
        stub = self._formation_stub(tmp_path)
        stub.config = {"runtime": {"group_membership_ttl": 5}}
        Formation._setup_groups(stub)
        assert stub._permission_resolver._membership_ttl == 5.0


class TestSlackMotivatingExample:
    """The PRD's Slack example end to end at the resolution layer."""

    @pytest.fixture
    def org_groups(self, tmp_path):
        return make_groups(
            tmp_path,
            {
                "hr.yaml": "agents: [hr-assistant]\n",
                "finance.yaml": "agents: [finance-assistant]\n",
                "engineering.yaml": "agents: [code-assistant]\n",
                "project-atlas.yaml": (
                    "agents: [code-assistant]\n"
                    "mcp_servers:\n"
                    "  projects:\n"
                    "    tools:\n"
                    "      allow: [lookup_atlas]\n"
                ),
            },
        )

    def test_alice_hr_reaches_hr_assistant(self, org_groups):
        alice = perms_for(org_groups, "hr")
        assert alice.is_allowed("agents", "hr-assistant")
        assert not alice.is_allowed("agents", "finance-assistant")

    def test_carol_engineering_cannot_reach_hr(self, org_groups):
        carol = perms_for(org_groups, "engineering")
        assert not carol.is_allowed("agents", "hr-assistant")
        assert carol.is_allowed("agents", "code-assistant")

    def test_dave_atlas_gets_lookup_atlas_tool(self, org_groups):
        dave = perms_for(org_groups, "engineering", "project-atlas")
        catalog = ["lookup_atlas", "lookup_other"]
        effective = dave.effective_tools(
            "code-assistant", "projects", ["lookup_other"], catalog=catalog
        )
        # engineering contributes the inherited surface; project-atlas's
        # override adds lookup_atlas (union across groups)
        assert effective == {"lookup_atlas", "lookup_other"}

    def test_carol_without_atlas_never_sees_lookup_atlas(self, org_groups):
        carol = perms_for(org_groups, "engineering")
        catalog = ["lookup_atlas", "lookup_other"]
        effective = carol.effective_tools(
            "code-assistant", "projects", ["lookup_other"], catalog=catalog
        )
        assert "lookup_atlas" not in effective


class TestCrossGroupAgentDenialInEffectiveTools:
    """A globally denied agent has an empty tool surface (review follow-up).

    is_allowed() and effective_tools() must agree even when the granting
    group carries a permissive agent-scoped tool override.
    """

    def test_denied_agent_with_permissive_override_is_empty(self, tmp_path):
        groups = make_groups(
            tmp_path,
            {
                "restrictors.yaml": "agents:\n  deny: [agent-x]\n",
                "granters.yaml": (
                    "agents:\n"
                    "  - agent-x:\n"
                    "      db:\n"
                    "        tools:\n"
                    '          allow: "*"\n'
                ),
            },
        )
        perms = perms_for(groups, "restrictors", "granters")
        assert not perms.is_allowed("agents", "agent-x")
        assert perms.effective_tools("agent-x", "db", INHERITED) == set()


class TestGroupsLoadedEventDeferral:
    """GROUPS_LOADED must not be swallowed by the load-time observability gate.

    _setup_groups() runs during load() while observability is disabled, so
    it stashes the event payload; start_overlord() emits it after enable().
    """

    def test_setup_groups_stashes_event_instead_of_emitting(self, tmp_path):
        (tmp_path / "groups").mkdir()
        (tmp_path / "groups" / "analyst.yaml").write_text("agents: [researcher]\n")
        stub = SimpleNamespace(
            _formation_path=str(tmp_path),
            _permission_resolver=None,
            _group_permissions={},
            formation_id=FORMATION_ID,
            config={"runtime": {}},
            _server_config={"auth": "required"},
        )
        Formation._setup_groups(stub)
        event = stub._groups_loaded_event
        assert event is not None
        assert event["group_count"] == 1
        assert event["group_ids"] == ["analyst"]
