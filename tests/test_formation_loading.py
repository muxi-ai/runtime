"""
Test Formation loading functionality.

This module tests basic Formation class loading and initialization.
"""

import pytest
from pathlib import Path
import yaml

from muxi.formation import Formation


class TestFormationLoading:
    """Test Formation loading from various sources."""

    @pytest.mark.asyncio
    async def test_load_basic_formation(self, basic_formation_yaml: Path):
        """Test loading a basic formation configuration."""
        formation = Formation(basic_formation_yaml.parent)

        # Verify formation can be created
        assert formation is not None
        assert formation.formation_dir == basic_formation_yaml.parent

        # Load and verify configuration
        config = yaml.safe_load(basic_formation_yaml.read_text())
        assert config["name"] == "test-formation"
        assert len(config["agents"]) == 1
        assert config["agents"][0]["id"] == "assistant"

    @pytest.mark.asyncio
    async def test_load_multi_agent_formation(self, multi_agent_formation_yaml: Path):
        """Test loading a multi-agent formation configuration."""
        formation = Formation(multi_agent_formation_yaml.parent)

        # Load and verify configuration
        config = yaml.safe_load(multi_agent_formation_yaml.read_text())
        assert config["name"] == "multi-agent-test"
        assert len(config["agents"]) == 2

        # Verify agent IDs
        agent_ids = [agent["id"] for agent in config["agents"]]
        assert "researcher" in agent_ids
        assert "writer" in agent_ids

    @pytest.mark.asyncio
    async def test_load_file_generation_formation(self, file_generation_formation_yaml: Path):
        """Test loading a formation with MCP configuration."""
        formation = Formation(file_generation_formation_yaml.parent)

        # Load and verify configuration
        config = yaml.safe_load(file_generation_formation_yaml.read_text())
        assert config["name"] == "file-generation-test"
        assert "mcp_servers" in config
        assert len(config["mcp_servers"]) == 1
        assert config["mcp_servers"][0]["builtin_name"] == "file_generation"

    @pytest.mark.asyncio
    async def test_formation_with_secrets(self, formation_with_secrets: Path):
        """Test formation with initialized secrets."""
        formation = Formation(formation_with_secrets)

        # Verify secrets files exist
        assert (formation_with_secrets / ".key").exists()
        assert (formation_with_secrets / "secrets.enc").exists()

    def test_formation_directory_structure(self, temp_formation_dir: Path):
        """Test that formation directory has proper structure."""
        assert (temp_formation_dir / "agents").is_dir()
        assert (temp_formation_dir / "mcp").is_dir()
        assert (temp_formation_dir / "a2a").is_dir()
        assert (temp_formation_dir / "knowledge").is_dir()

    @pytest.mark.asyncio
    async def test_load_from_existing_test_formations(self, test_formations_dir: Path):
        """Test loading from the actual test-formations directory."""
        # Check if test formations exist
        if not test_formations_dir.exists():
            pytest.skip("Test formations directory not found")

        # List available formations
        formations = [d for d in test_formations_dir.iterdir()
                     if d.is_dir() and d.name.startswith("formation-")]

        if not formations:
            pytest.skip("No test formations found")

        # Try to load each formation
        for formation_dir in formations:
            formation = Formation(formation_dir)
            assert formation.formation_dir == formation_dir
