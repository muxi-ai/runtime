"""
Unit tests for soul document support (Proactiveness Phase 1).

Covers loader-time path resolution and confinement (relative to the
formation directory, no absolute paths or traversal, fail fast on missing
files) and the Agent-level injection (soul content is prepended to the
system message, framing the functional persona).
"""

import pytest

from muxi.runtime.formation.agents.agent import Agent
from muxi.runtime.formation.config.formation_loader import FormationLoader


def _agent_config(soul_path):
    return {
        "agents": [
            {
                "id": "main",
                "name": "Main",
                "description": "Main agent",
                "soul": soul_path,
            }
        ]
    }


class TestLoaderResolution:
    def test_soul_path_resolved_relative_to_formation_dir(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("# Soul\nHonesty over sycophancy.")
        loader = FormationLoader()
        config = loader._resolve_knowledge_paths(_agent_config("./SOUL.md"), str(tmp_path))
        assert config["agents"][0]["soul"] == str(tmp_path / "SOUL.md")

    def test_missing_soul_file_fails_fast(self, tmp_path):
        loader = FormationLoader()
        with pytest.raises(ValueError, match="Soul document not found"):
            loader._resolve_knowledge_paths(_agent_config("./SOUL.md"), str(tmp_path))

    def test_absolute_soul_path_rejected(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("soul")
        loader = FormationLoader()
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            loader._resolve_knowledge_paths(_agent_config(str(tmp_path / "SOUL.md")), str(tmp_path))

    def test_traversal_soul_path_rejected(self, tmp_path):
        formation_dir = tmp_path / "formation"
        formation_dir.mkdir()
        (tmp_path / "SOUL.md").write_text("outside soul")
        loader = FormationLoader()
        with pytest.raises(ValueError, match="traversal"):
            loader._resolve_knowledge_paths(_agent_config("../SOUL.md"), str(formation_dir))

    def test_agents_without_soul_untouched(self, tmp_path):
        loader = FormationLoader()
        config = {"agents": [{"id": "main", "name": "Main", "description": "d"}]}
        resolved = loader._resolve_knowledge_paths(config, str(tmp_path))
        assert "soul" not in resolved["agents"][0]


class _DummyModel:
    """Placeholder model object: system-message tests never invoke it."""


class TestAgentInjection:
    def _make_agent(self, **kwargs):
        return Agent(
            model=_DummyModel(),
            overlord=object(),
            a2a_internal=False,
            a2a_external=False,
            **kwargs,
        )

    def test_soul_prepended_to_system_message(self):
        agent = self._make_agent(
            system_message="You are a productivity assistant.",
            soul="## My Values\nHonesty over sycophancy.",
        )
        assert agent.system_message.startswith("## My Values\nHonesty over sycophancy.")
        assert "You are a productivity assistant." in agent.system_message
        assert agent.system_message.index("My Values") < agent.system_message.index(
            "productivity assistant"
        )
        # The live conversation context carries the combined message
        assert agent._messages[0]["role"] == "system"
        assert "My Values" in agent._messages[0]["content"]

    def test_soul_prepended_to_default_system_message(self):
        agent = self._make_agent(soul="I am direct.")
        assert agent.system_message.startswith("I am direct.")
        assert "helpful assistant" in agent.system_message

    def test_no_soul_leaves_system_message_unchanged(self):
        agent = self._make_agent(system_message="You are a helper.")
        assert agent.soul is None
        assert agent.system_message == "You are a helper."

    def test_blank_soul_ignored(self):
        agent = self._make_agent(system_message="You are a helper.", soul="   \n")
        assert agent.soul is None
        assert agent.system_message == "You are a helper."
