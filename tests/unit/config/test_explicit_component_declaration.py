"""
Unit tests for explicit component declaration in FormationLoader.

Tests the new pattern where agents, MCP servers, and A2A services must be
explicitly declared in the formation file by ID (string references) or as
inline dicts. Files in subdirectories are definitions; the formation file
is the manifest.
"""

from pathlib import Path

import pytest

from muxi.runtime.formation.config.formation_loader import FormationLoader


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def loader():
    return FormationLoader()


# ---------------------------------------------------------------------------
# Agent resolution
# ---------------------------------------------------------------------------


class TestAgentResolution:

    @pytest.mark.asyncio
    async def test_string_ids_resolve_to_file_configs(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - agent-a
  - agent-b
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "agent-a.yaml",
            """
id: agent-a
name: Agent A
description: First agent
system_message: "Hello A"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "agent-b.yaml",
            """
id: agent-b
name: Agent B
description: Second agent
system_message: "Hello B"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agents = config["agents"]
        assert len(agents) == 2
        assert agents[0]["id"] == "agent-a"
        assert agents[1]["id"] == "agent-b"
        assert agents[0]["name"] == "Agent A"
        assert agents[1]["name"] == "Agent B"

    @pytest.mark.asyncio
    async def test_inline_dicts_pass_through(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - id: inline-bot
    name: Inline Bot
    description: Inline agent
    system_message: "Hi"
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agents = config["agents"]
        assert len(agents) == 1
        assert agents[0]["id"] == "inline-bot"
        assert agents[0]["name"] == "Inline Bot"

    @pytest.mark.asyncio
    async def test_mixed_string_and_inline(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - agent-a
  - id: inline-bot
    name: Inline Bot
    description: Inline
    system_message: "Hi"
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "agent-a.yaml",
            """
id: agent-a
name: Agent A
description: File agent
system_message: "Hello"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agents = config["agents"]
        assert len(agents) == 2
        assert agents[0]["id"] == "agent-a"
        assert agents[0]["source"] == "formation"
        assert agents[1]["id"] == "inline-bot"

    @pytest.mark.asyncio
    async def test_unknown_id_raises_error(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - nonexistent
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        (tmp_path / "agents").mkdir()
        with pytest.raises(ValueError, match="nonexistent.*not found"):
            await loader.load(str(tmp_path))

    @pytest.mark.asyncio
    async def test_empty_list_loads_nothing(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents: []
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "agent-a.yaml",
            """
id: agent-a
name: Agent A
description: Should not load
system_message: "Hello"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        assert config["agents"] == []

    @pytest.mark.asyncio
    async def test_omitted_field_loads_nothing(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "agent-a.yaml",
            """
id: agent-a
name: Agent A
description: Should not load
system_message: "Hello"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        assert "agents" not in config

    @pytest.mark.asyncio
    async def test_undeclared_file_is_ignored(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - agent-a
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "agent-a.yaml",
            """
id: agent-a
name: Agent A
description: Should load
system_message: "Hello"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "agent-b.yaml",
            """
id: agent-b
name: Agent B
description: Should NOT load
system_message: "Hello"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agents = config["agents"]
        assert len(agents) == 1
        assert agents[0]["id"] == "agent-a"

    @pytest.mark.asyncio
    async def test_id_defaults_to_filename_stem(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - my-agent
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "my-agent.yaml",
            """
name: My Agent
description: No explicit ID
system_message: "Hello"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agents = config["agents"]
        assert len(agents) == 1
        assert agents[0]["id"] == "my-agent"


# ---------------------------------------------------------------------------
# MCP server resolution
# ---------------------------------------------------------------------------


class TestMCPServerResolution:

    @pytest.mark.asyncio
    async def test_string_ids_resolve_mcp_configs(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
mcp:
  servers:
    - github-mcp
    - slack-mcp
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "mcp" / "github-mcp.yaml",
            """
id: github-mcp
description: GitHub tools
type: command
command: npx
args: ["-y", "@modelcontextprotocol/server-github"]
""",
        )
        _write_yaml(
            tmp_path / "mcp" / "slack-mcp.yaml",
            """
id: slack-mcp
description: Slack tools
type: http
endpoint: "https://slack.example.com/mcp"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        servers = config["mcp"]["servers"]
        assert len(servers) == 2
        assert servers[0]["id"] == "github-mcp"
        assert servers[1]["id"] == "slack-mcp"
        assert servers[0]["type"] == "command"

    @pytest.mark.asyncio
    async def test_inline_mcp_dicts_pass_through(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
mcp:
  servers:
    - id: inline-mcp
      type: http
      endpoint: "https://example.com/mcp"
      description: Inline MCP
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        servers = config["mcp"]["servers"]
        assert len(servers) == 1
        assert servers[0]["id"] == "inline-mcp"

    @pytest.mark.asyncio
    async def test_unknown_mcp_id_raises_error(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
mcp:
  servers:
    - missing-mcp
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        (tmp_path / "mcp").mkdir()
        with pytest.raises(ValueError, match="missing-mcp.*not found"):
            await loader.load(str(tmp_path))

    @pytest.mark.asyncio
    async def test_mcps_directory_supported(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
mcp:
  servers:
    - my-tool
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "mcps" / "my-tool.yaml",
            """
id: my-tool
description: Tool in mcps dir
type: command
command: echo
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        servers = config["mcp"]["servers"]
        assert len(servers) == 1
        assert servers[0]["id"] == "my-tool"


# ---------------------------------------------------------------------------
# Agent-level MCP references
# ---------------------------------------------------------------------------


class TestAgentMCPReferences:

    @pytest.mark.asyncio
    async def test_agent_references_formation_mcp_by_id(self, loader, tmp_path):
        _write_yaml(
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
      - github-mcp
mcp:
  servers:
    - github-mcp
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "mcp" / "github-mcp.yaml",
            """
id: github-mcp
description: GitHub tools
type: command
command: npx
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agent = config["agents"][0]
        assert len(agent["mcp_servers"]) == 1
        assert agent["mcp_servers"][0]["id"] == "github-mcp"
        assert agent["mcp_servers"][0]["type"] == "command"

    @pytest.mark.asyncio
    async def test_agent_inline_mcp_preserved(self, loader, tmp_path):
        _write_yaml(
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
      - id: private-tool
        type: http
        endpoint: "https://private.example.com/mcp"
        description: Private
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agent = config["agents"][0]
        assert len(agent["mcp_servers"]) == 1
        assert agent["mcp_servers"][0]["id"] == "private-tool"
        assert agent["mcp_servers"][0]["type"] == "http"

    @pytest.mark.asyncio
    async def test_agent_unknown_mcp_reference_raises_error(self, loader, tmp_path):
        _write_yaml(
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
      - nonexistent-mcp
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        with pytest.raises(ValueError, match="nonexistent-mcp.*not declared"):
            await loader.load(str(tmp_path))

    @pytest.mark.asyncio
    async def test_agent_mixes_references_and_inline(self, loader, tmp_path):
        _write_yaml(
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
      - github-mcp
      - id: private-tool
        type: http
        endpoint: "https://private.example.com/mcp"
        description: Private
mcp:
  servers:
    - github-mcp
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "mcp" / "github-mcp.yaml",
            """
id: github-mcp
description: GitHub tools
type: command
command: npx
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agent = config["agents"][0]
        assert len(agent["mcp_servers"]) == 2
        assert agent["mcp_servers"][0]["id"] == "github-mcp"
        assert agent["mcp_servers"][0]["type"] == "command"
        assert agent["mcp_servers"][1]["id"] == "private-tool"
        assert agent["mcp_servers"][1]["type"] == "http"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_non_dict_file_skipped(self, loader, tmp_path):
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - good-agent
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "good-agent.yaml",
            """
id: good-agent
name: Good Agent
description: Valid agent
system_message: "Hi"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "bad-agent.yaml",
            """
- this is a list
- not a dict
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agents = config["agents"]
        assert len(agents) == 1
        assert agents[0]["id"] == "good-agent"

    @pytest.mark.asyncio
    async def test_active_field_is_ignored(self, loader, tmp_path):
        """active: false should be meaningless -- if declared, it loads."""
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
agents:
  - disabled-agent
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "disabled-agent.yaml",
            """
id: disabled-agent
name: Disabled Agent
description: Has active false but should load anyway
system_message: "Hi"
active: false
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        agents = config["agents"]
        assert len(agents) == 1
        assert agents[0]["id"] == "disabled-agent"

    @pytest.mark.asyncio
    async def test_flattened_formation_with_inline_agents(self, loader, tmp_path):
        """Flattened (single file) formations with inline agents still work."""
        formation_file = tmp_path / "formation.yaml"
        _write_yaml(
            formation_file,
            """
schema: "1.0.0"
id: test
description: test
agents:
  - id: simple-bot
    name: Simple Bot
    description: Inline agent in flattened formation
    system_message: "Hi"
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        config, _, _ = await loader.load(str(formation_file))
        agents = config["agents"]
        assert len(agents) == 1
        assert agents[0]["id"] == "simple-bot"

    @pytest.mark.asyncio
    async def test_agents_dir_without_declaration_loads_nothing(self, loader, tmp_path):
        """agents/ directory exists but formation has no agents: key -> nothing loaded."""
        _write_yaml(
            tmp_path / "formation.yaml",
            """
schema: "1.0.0"
id: test
description: test
llm:
  models:
    - text: "openai/gpt-4o-mini"
""",
        )
        _write_yaml(
            tmp_path / "agents" / "orphan.yaml",
            """
id: orphan
name: Orphan
description: Nobody declared me
system_message: "Hello?"
""",
        )
        config, _, _ = await loader.load(str(tmp_path))
        assert "agents" not in config
