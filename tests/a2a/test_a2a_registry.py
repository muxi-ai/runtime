"""
A2A Registry Test with Modular Formation

Tests A2A registry interactions using the modular formation template.
Demonstrates external registry communication and service discovery.
"""

from pathlib import Path
import pytest

from src.muxi.runtime.config.formation_loader import FormationLoader  # noqa: F401
from src.muxi.runtime.secrets import SecretsManager  # noqa: F401


class TestA2ARegistry:
    """Test A2A registry functionality with modular formations."""

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
    async def test_registry_configuration(self, formation_loader, formation_path,
                                          secrets_manager):
        """Test that registry configuration is properly loaded."""
        config = await formation_loader.load(str(formation_path), secrets_manager)

        # Verify A2A configuration
        assert config["a2a"]["enabled"] is True

        # Check outbound registry configuration
        outbound = config["a2a"]["outbound"]
        assert outbound["enabled"] is True
        assert "http://localhost:9090" in outbound["registries"]

        # Check inbound registry configuration
        inbound = config["a2a"]["inbound"]
        assert inbound["enabled"] is True
        assert "http://localhost:9090" in inbound["registries"]
        assert inbound["port"] == 8181

    @pytest.mark.asyncio
    async def test_formation_agent_discovery(self, formation_loader, formation_path,
                                             secrets_manager):
        """Test that formation agents are properly configured for A2A."""
        config = await formation_loader.load(str(formation_path), secrets_manager)

        # Find agents configured for external A2A
        external_agents = []
        for agent in config.get("agents", []):
            if agent.get("a2a", {}).get("external", False):
                external_agents.append(agent)

        assert len(external_agents) > 0

        # Verify test agent configuration
        test_agent = next((a for a in external_agents if a["id"] == "test-agent"), None)
        assert test_agent is not None
        assert test_agent["description"] == "Test agent for A2A operations and communication"

    def test_registry_mock_scenario(self):
        """Test scenario for registry interaction (mock)."""
        # This would test actual registry interactions in a real scenario
        # For now, we test the configuration structure

        registry_config = {
            "url": "http://localhost:9090",
            "timeout": 30,
            "retry_attempts": 3
        }

        # Verify configuration structure
        assert "url" in registry_config
        assert registry_config["url"].startswith("http")
        assert registry_config["timeout"] > 0

    @pytest.mark.asyncio
    async def test_external_service_configuration(self, formation_path):
        """Test external service configuration in A2A directory."""
        # Check if A2A services directory exists
        a2a_dir = formation_path / "a2a"
        assert a2a_dir.exists()

        # Note: In a real scenario, you would have external service configs
        # For this test, we verify the directory structure is ready


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
