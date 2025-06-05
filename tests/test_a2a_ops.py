"""
A2A Operations Test with Modular Formation

Tests A2A registration and discovery using the new modular formation template.
This demonstrates the recommended approach for testing MUXI formations.
"""

import pytest
from pathlib import Path

from muxi.runtime.config.formation_loader import FormationLoader
from muxi.runtime.secrets import SecretsManager


class TestA2AWithModularFormation:
    """Test A2A operations using modular formation template."""

    @pytest.fixture
    def formation_path(self):
        """Path to test formation directory."""
        return Path(__file__).parent / "test-formations" / "basic-a2a-formation"

    @pytest.fixture
    async def formation_loader(self):
        """Create a formation loader."""
        return FormationLoader()

    @pytest.fixture
    async def secrets_manager(self, formation_path):
        """Create a secrets manager for the test formation."""
        manager = SecretsManager(formation_path)
        await manager.initialize_encryption()

        # Store test secrets
        await manager.store_secret("OPENAI_API_KEY", "test-key-123", overwrite=True)

        return manager

    @pytest.mark.asyncio
    async def test_formation_loading(self, formation_loader, formation_path, secrets_manager):
        """Test loading the modular A2A formation."""
        # Test formation type detection
        formation_type = formation_loader.detect_formation_type(str(formation_path))
        assert formation_type == "modular"

        # Load the formation
        config = await formation_loader.load(str(formation_path), secrets_manager)

        # Verify core configuration
        assert config["id"] == "basic-a2a-test-formation"
        assert config["a2a"]["enabled"] is True
        assert "http://localhost:9090" in config["a2a"]["outbound"]["registries"]

    @pytest.mark.asyncio
    async def test_agent_discovery(self, formation_loader, formation_path, secrets_manager):
        """Test that agents are discovered from the agents/ directory."""
        config = await formation_loader.load(str(formation_path), secrets_manager)

        # Should have discovered the test agent
        assert "agents" in config
        assert len(config["agents"]) >= 1

        # Find the test agent
        test_agent = None
        for agent in config["agents"]:
            if agent["id"] == "test-agent":
                test_agent = agent
                break

        assert test_agent is not None
        assert test_agent["name"] == "Test Agent"
        assert test_agent["a2a"]["external"] is True

            @pytest.mark.asyncio
    async def test_knowledge_path_resolution(self, formation_loader, formation_path,
                                             secrets_manager):
        """Test that knowledge paths are resolved correctly."""
        await formation_loader.load(str(formation_path), secrets_manager)

        # Note: This test assumes agents have knowledge configurations
        # The actual path resolution would depend on agent configs with knowledge sources

        # Verify formation directory structure exists
        assert (formation_path / "knowledge").exists()
        assert (formation_path / "knowledge" / "test_knowledge.md").exists()

    def test_formation_structure(self, formation_path):
        """Test that the formation follows the modular template structure."""
        # Verify directory structure
        assert formation_path.exists()
        assert (formation_path / "formation.yaml").exists()
        assert (formation_path / "agents").exists()
        assert (formation_path / "mcp").exists()
        assert (formation_path / "a2a").exists()
        assert (formation_path / "knowledge").exists()

        # Verify agent file exists
        assert (formation_path / "agents" / "test_agent.yaml").exists()

    @pytest.mark.asyncio
    async def test_secrets_interpolation(self, formation_loader, formation_path, secrets_manager):
        """Test that secrets are properly interpolated in the loaded configuration."""
        config = await formation_loader.load(str(formation_path), secrets_manager)

        # Check that the OpenAI API key was interpolated
        assert config["llm"]["api_keys"]["openai"] == "test-key-123"


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
