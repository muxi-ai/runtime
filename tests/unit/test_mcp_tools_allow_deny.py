"""Unit tests for the allow/deny tools vocabulary and attachment overrides.

Covers the registry/agent-level unification with the group-level GBAC
semantics (see prds/completed/group-based-access-control.md):

* ``allow`` / ``deny`` are canonical; ``whitelist`` / ``blacklist`` are
  accepted aliases with identical behaviour.
* Both rules may appear in one block — allow applies first, deny
  subtracts (deny wins on overlap), matching group-level ``ToolRules``.
* Agent ``mcp_servers`` attachments may reference a declared server as
  ``{id, tools}`` — the override chains AFTER the referenced server's
  own ``tools`` block, so level 2 of the override cascade can narrow
  but never resurrect registry-pruned tools.
"""

from typing import Any, Dict, List

import pytest

from muxi.runtime.formation.config.formation_loader import FormationLoader
from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.services.mcp.tool_filter import ToolFilterSpec, apply_filter


def _catalog(*names: str) -> List[Dict[str, Any]]:
    return [{"name": n, "description": f"{n} description", "inputSchema": {}} for n in names]


GITHUB = _catalog(
    "list_issues",
    "list_branches",
    "create_issue",
    "delete_repo",
    "delete_branch",
)


# ---------------------------------------------------------------------------
# 1. Alias equivalence
# ---------------------------------------------------------------------------


def test_allow_is_equivalent_to_whitelist() -> None:
    via_alias, _ = apply_filter(GITHUB, ToolFilterSpec.from_config({"whitelist": ["list_*"]}))
    via_canonical, _ = apply_filter(GITHUB, ToolFilterSpec.from_config({"allow": ["list_*"]}))
    assert via_alias == via_canonical
    assert [t["name"] for t in via_canonical] == ["list_issues", "list_branches"]


def test_deny_is_equivalent_to_blacklist() -> None:
    via_alias, _ = apply_filter(GITHUB, ToolFilterSpec.from_config({"blacklist": ["delete_*"]}))
    via_canonical, _ = apply_filter(GITHUB, ToolFilterSpec.from_config({"deny": ["delete_*"]}))
    assert via_alias == via_canonical
    assert [t["name"] for t in via_canonical] == ["list_issues", "list_branches", "create_issue"]


def test_canonical_key_wins_over_alias_at_runtime() -> None:
    """Validation rejects the conflict fail-fast; the runtime spec is tolerant
    and prefers the canonical spelling rather than guessing a merge."""
    spec = ToolFilterSpec.from_config({"allow": ["list_*"], "whitelist": ["delete_*"]})
    assert spec.allow == ("list_*",)


def test_report_mode_uses_canonical_vocabulary() -> None:
    _, report = apply_filter(GITHUB, ToolFilterSpec.from_config({"whitelist": ["list_*"]}))
    assert report is not None and report.mode == "allow"
    _, report = apply_filter(GITHUB, ToolFilterSpec.from_config({"blacklist": ["delete_*"]}))
    assert report is not None and report.mode == "deny"


# ---------------------------------------------------------------------------
# 2. Relaxed mutex: allow + deny in one block (deny after allow)
# ---------------------------------------------------------------------------


def test_allow_and_deny_together_subtract_after_allow() -> None:
    spec = ToolFilterSpec.from_config({"allow": ["list_*", "delete_*"], "deny": ["delete_repo"]})
    kept, report = apply_filter(GITHUB, spec)
    assert [t["name"] for t in kept] == ["list_issues", "list_branches", "delete_branch"]
    assert report is not None and report.mode == "allow+deny"


def test_deny_wins_on_full_overlap() -> None:
    """A tool matched by both rules is denied — same as group-level rules."""
    spec = ToolFilterSpec.from_config({"allow": ["delete_*"], "deny": ["delete_*"]})
    kept, report = apply_filter(GITHUB, spec)
    assert kept == []
    assert report is not None and report.registered_tool_count == 0


def test_alias_spellings_participate_in_relaxed_mutex() -> None:
    """whitelist+blacklist in one block now means allow+deny, not an error."""
    spec = ToolFilterSpec.from_config({"whitelist": ["list_*"], "blacklist": ["*_branches"]})
    kept, _ = apply_filter(GITHUB, spec)
    assert [t["name"] for t in kept] == ["list_issues"]


def test_deny_star_string_shorthand_hides_everything() -> None:
    """``deny: "*"`` — the group-level hide-server idiom works here too."""
    spec = ToolFilterSpec.from_config({"deny": "*"})
    kept, report = apply_filter(GITHUB, spec)
    assert kept == []
    assert report is not None and report.registered_tool_count == 0


def test_deny_pattern_resolves_against_stage_input_not_post_allow() -> None:
    """A deny overlapping the allowed set must not be reported unknown."""
    spec = ToolFilterSpec.from_config({"allow": ["list_*"], "deny": ["create_issue"]})
    kept, report = apply_filter(GITHUB, spec)
    assert [t["name"] for t in kept] == ["list_issues", "list_branches"]
    assert report is not None
    assert report.unknown_patterns == []


# ---------------------------------------------------------------------------
# 3. Chained specs (attachment override after catalog bound)
# ---------------------------------------------------------------------------


def test_chained_override_narrows_base() -> None:
    base = ToolFilterSpec.from_config({"allow": ["list_*", "create_*"]})
    spec = ToolFilterSpec.from_config({"allow": ["list_issues"]}, base=base)
    kept, report = apply_filter(GITHUB, spec)
    assert [t["name"] for t in kept] == ["list_issues"]
    assert report is not None and report.mode == "allow > allow"


def test_chained_override_cannot_resurrect_base_pruned_tools() -> None:
    """Level 2 selects from the post-level-1 catalog — never widens it."""
    base = ToolFilterSpec.from_config({"deny": ["delete_*"]})
    spec = ToolFilterSpec.from_config({"allow": ["delete_repo", "list_*"]}, base=base)
    kept, _ = apply_filter(GITHUB, spec)
    # delete_repo was pruned by the base (registry) filter; the override's
    # allow cannot bring it back.
    assert [t["name"] for t in kept] == ["list_issues", "list_branches"]


def test_chained_deny_subtracts_from_base_result() -> None:
    base = ToolFilterSpec.from_config({"allow": ["list_*", "create_*"]})
    spec = ToolFilterSpec.from_config({"deny": ["list_branches"]}, base=base)
    kept, _ = apply_filter(GITHUB, spec)
    assert [t["name"] for t in kept] == ["list_issues", "create_issue"]


def test_inactive_base_is_dropped_from_chain() -> None:
    spec = ToolFilterSpec.from_config({"allow": ["list_*"]}, base=ToolFilterSpec())
    assert spec.base is None
    assert len(spec.stages()) == 1


def test_inactive_override_with_active_base_still_filters() -> None:
    """A bare ``{id}`` reference keeps the referenced server's own filter."""
    base = ToolFilterSpec.from_config({"allow": ["list_*"]})
    spec = ToolFilterSpec.from_config(None, base=base)
    assert spec.is_active is True
    kept, _ = apply_filter(GITHUB, spec)
    assert [t["name"] for t in kept] == ["list_issues", "list_branches"]


# ---------------------------------------------------------------------------
# 4. Validation: agent-level blocks and the {id, tools} reference form
# ---------------------------------------------------------------------------


def test_agent_inline_tools_block_is_validated() -> None:
    v = FormationValidator()
    v._validate_agent_mcp_servers(
        [
            {
                "id": "private-tool",
                "description": "Private",
                "type": "http",
                "endpoint": "https://private.example.com/mcp",
                "tools": {"allow": ["a"], "whitelist": ["b"]},  # alias conflict
            }
        ],
        "my-agent",
    )
    assert any("alias" in e for e in v.result.errors)
    assert any("my-agent" in e for e in v.result.errors)


def test_agent_reference_with_tools_override_is_valid() -> None:
    v = FormationValidator()
    v._validate_agent_mcp_servers(
        [{"id": "github-mcp", "tools": {"allow": ["list_*"], "deny": ["delete_*"]}}],
        "my-agent",
    )
    assert v.result.errors == []


def test_agent_reference_with_alias_forms_is_valid() -> None:
    v = FormationValidator()
    v._validate_agent_mcp_servers(
        [{"id": "github-mcp", "tools": {"whitelist": ["list_*"]}}],
        "my-agent",
    )
    assert v.result.errors == []


def test_agent_reference_requires_string_id() -> None:
    v = FormationValidator()
    v._validate_agent_mcp_servers([{"tools": {"allow": ["list_*"]}}], "my-agent")
    assert any("non-empty string 'id'" in e for e in v.result.errors)


def test_agent_reference_bad_tools_block_fails_fast() -> None:
    v = FormationValidator()
    v._validate_agent_mcp_servers(
        [{"id": "github-mcp", "tools": {"alow": ["list_*"]}}],  # typo'd key
        "my-agent",
    )
    assert any("unknown key" in e for e in v.result.errors)


def test_agent_reference_duplicate_id_rejected() -> None:
    v = FormationValidator()
    v._validate_agent_mcp_servers(
        ["placeholder-unused", {"id": "github-mcp"}, {"id": "github-mcp"}],
        "my-agent",
    )
    assert any("duplicate MCP server id" in e for e in v.result.errors)


def test_formation_level_allow_deny_and_aliases_are_valid() -> None:
    v = FormationValidator()
    for block in (
        {"allow": ["list_*"]},
        {"deny": ["delete_*"]},
        {"allow": ["list_*"], "deny": ["list_branches"]},
        {"whitelist": ["list_*"]},
        {"blacklist": ["delete_*"]},
        {"whitelist": ["list_*"], "blacklist": ["delete_*"]},
        {"deny": "*"},
    ):
        v._validate_mcp_tools_block(block, "demo-mcp")
    assert v.result.errors == []


# ---------------------------------------------------------------------------
# 5. Loader: {id, tools} attachment references
# ---------------------------------------------------------------------------


FORMATION_WITH_REFERENCE = """
schema: "1.0.0"
id: test
description: test
agents:
  - id: my-agent
    name: My Agent
    description: Test agent
    system_message: "Hello"
    mcp_servers:
      - id: github-mcp
        tools:
          allow: [list_*]
          deny: [list_branches]
mcp:
  servers:
    - id: github-mcp
      description: GitHub tools
      type: command
      command: npx
      tools:
        deny: [delete_*]
llm:
  models:
    - text: "openai/gpt-4o-mini"
"""


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def loader():
    return FormationLoader()


@pytest.mark.asyncio
async def test_reference_with_tools_resolves_and_carries_override(loader, tmp_path) -> None:
    _write(tmp_path / "formation.yaml", FORMATION_WITH_REFERENCE)
    config, _, _ = await loader.load(str(tmp_path))
    servers = config["agents"][0]["mcp_servers"]
    assert len(servers) == 1
    resolved = servers[0]
    # Full formation-level definition, including its own tools block...
    assert resolved["id"] == "github-mcp"
    assert resolved["type"] == "command"
    assert resolved["tools"] == {"deny": ["delete_*"]}
    # ...plus the attachment override, kept separate so the registration
    # path chains it after the catalog bound.
    assert resolved["_tools_override"] == {"allow": ["list_*"], "deny": ["list_branches"]}
    # The formation-level registry entry is untouched.
    assert "_tools_override" not in config["mcp"]["servers"][0]


@pytest.mark.asyncio
async def test_reference_without_tools_behaves_like_string_ref(loader, tmp_path) -> None:
    _write(
        tmp_path / "formation.yaml",
        FORMATION_WITH_REFERENCE.replace(
            """      - id: github-mcp
        tools:
          allow: [list_*]
          deny: [list_branches]""",
            "      - id: github-mcp",
        ),
    )
    config, _, _ = await loader.load(str(tmp_path))
    resolved = config["agents"][0]["mcp_servers"][0]
    assert resolved["id"] == "github-mcp"
    assert "_tools_override" not in resolved


@pytest.mark.asyncio
async def test_reference_to_directory_private_mcp_carries_override(loader, tmp_path) -> None:
    _write(
        tmp_path / "formation.yaml",
        """
schema: "1.0.0"
id: test
description: test
agents:
  - id: my-agent
    name: My Agent
    description: Test agent
    system_message: "Hello"
    mcp_servers:
      - id: private-mcp
        tools:
          deny: [drop_*]
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
    )
    _write(
        tmp_path / "mcp" / "private-mcp.yaml",
        """
id: private-mcp
description: Private tools
type: command
command: npx
""",
    )
    config, _, _ = await loader.load(str(tmp_path))
    resolved = config["agents"][0]["mcp_servers"][0]
    assert resolved["id"] == "private-mcp"
    assert resolved["_tools_override"] == {"deny": ["drop_*"]}


@pytest.mark.asyncio
async def test_reference_with_unknown_id_raises(loader, tmp_path) -> None:
    _write(
        tmp_path / "formation.yaml",
        FORMATION_WITH_REFERENCE.replace(
            "- id: github-mcp\n        tools:", "- id: nope\n        tools:"
        ),
    )
    with pytest.raises(ValueError, match="nope.*not found"):
        await loader.load(str(tmp_path))


@pytest.mark.asyncio
async def test_reference_with_blank_id_raises(loader, tmp_path) -> None:
    _write(
        tmp_path / "formation.yaml",
        FORMATION_WITH_REFERENCE.replace(
            "- id: github-mcp\n        tools:", '- id: ""\n        tools:'
        ),
    )
    with pytest.raises(ValueError, match="non-empty string 'id'"):
        await loader.load(str(tmp_path))


# ---------------------------------------------------------------------------
# 6. Registration-path chaining (overlord semantics, exercised directly)
# ---------------------------------------------------------------------------


def test_resolved_reference_chains_override_after_catalog_bound() -> None:
    """End-to-end over the resolved dict shape the overlord consumes."""
    server_config = {
        "id": "github-mcp",
        "type": "command",
        "command": "npx",
        "tools": {"deny": ["delete_*"]},
        "_tools_override": {"allow": ["list_*", "delete_repo"]},
    }
    base = ToolFilterSpec.from_config(server_config.get("tools"))
    spec = ToolFilterSpec.from_config(server_config.get("_tools_override"), base=base)
    kept, report = apply_filter(GITHUB, spec)
    # delete_repo stays pruned by the catalog bound despite the override allow.
    assert [t["name"] for t in kept] == ["list_issues", "list_branches"]
    assert report is not None and report.mode == "deny > allow"
