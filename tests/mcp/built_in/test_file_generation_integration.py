"""
Integration tests for File Generation MCP with MUXI Runtime.

Tests the complete integration including:
- Formation configuration
- MCP auto-registration
- System prompt augmentation
- End-to-end file generation
"""

import os
import tempfile
from pathlib import Path
import pytest
import sys

# Add the runtime source to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi import Formation  # noqa: F402


class TestFileGenerationIntegration:
    """Integration tests for file generation MCP."""

    @pytest.fixture
    def formation_config(self):
        """Create a test formation configuration."""
        return {
            "schema": "1.0.0",
            "id": "test-file-generation",
            "description": "Test formation for file generation MCP",
            "llm": {
                "api_keys": {
                    "openai": "test-key"
                },
                "models": [
                    {"text": "gpt-3.5-turbo", "provider": "openai"}
                ]
            },
            "agents": [
                {
                    "schema": "1.0.0",
                    "id": "test-agent",
                    "name": "Test Agent",
                    "description": "Agent for testing file generation"
                }
            ],
            "runtime": {
                "built_in_mcps": ["file-generation"]  # Enable only file generation
            }
        }

    @pytest.fixture
    def formation_config_all_mcps(self, formation_config):
        """Create a formation config with all MCPs enabled."""
        config = formation_config.copy()
        config["runtime"]["built_in_mcps"] = True  # Enable all built-in MCPs
        return config

    @pytest.fixture
    def formation_config_no_mcps(self, formation_config):
        """Create a formation config with MCPs disabled."""
        config = formation_config.copy()
        config["runtime"]["built_in_mcps"] = False  # Disable all built-in MCPs
        return config

    @pytest.mark.asyncio
    async def test_builtin_mcp_registration(self, formation_config):
        """Test that built-in MCP is registered when enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save formation config
            config_path = Path(tmpdir) / "formation.yaml"
            import yaml
            with open(config_path, "w") as f:
                yaml.dump(formation_config, f)

            # Create formation and load config
            formation = Formation()
            formation.load(str(config_path))

            # Mock the MCP service to track registrations
            registered_servers = []

            async def mock_register(server_id, **kwargs):
                registered_servers.append({
                    "server_id": server_id,
                    "command": kwargs.get("command"),
                    "transport_type": kwargs.get("transport_type")
                })
                return server_id

            # Start overlord (which should register built-in MCPs)
            from unittest.mock import patch
            with patch('muxi.services.mcp.service.MCPService.register_mcp_server', mock_register):
                overlord = formation.start_overlord()

                # Check that file-generation MCP was registered
                assert len(registered_servers) == 1
                assert registered_servers[0]["server_id"] == "builtin-file-generation"
                assert "file_generation.py" in registered_servers[0]["command"]
                assert registered_servers[0]["transport_type"] == "command"

            # Cleanup
            formation.stop_overlord()
            formation.stop()

    @pytest.mark.asyncio
    async def test_system_prompt_augmentation(self, formation_config):
        """Test that system prompts are augmented with MCP instructions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save formation config
            config_path = Path(tmpdir) / "formation.yaml"
            import yaml
            with open(config_path, "w") as f:
                yaml.dump(formation_config, f)

            # Create formation and load config
            formation = Formation()
            formation.load(str(config_path))

            # Start overlord
            overlord = formation.start_overlord()

            # Get system message
            system_message = overlord._create_overlord_system_message()

            # Check that file generation instructions are included
            assert "File Generation" in system_message
            assert "generate_file" in system_message
            assert "matplotlib" in system_message
            assert "pandas" in system_message

            # Cleanup
            formation.stop_overlord()
            formation.stop()

    @pytest.mark.asyncio
    async def test_builtin_mcps_disabled(self, formation_config_no_mcps):
        """Test that built-in MCPs are not registered when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save formation config
            config_path = Path(tmpdir) / "formation.yaml"
            import yaml
            with open(config_path, "w") as f:
                yaml.dump(formation_config_no_mcps, f)

            # Create formation and load config
            formation = Formation()
            formation.load(str(config_path))

            # Mock the MCP service to track registrations
            registered_servers = []

            async def mock_register(server_id, **kwargs):
                registered_servers.append(server_id)
                return server_id

            # Start overlord
            from unittest.mock import patch
            with patch('muxi.services.mcp.service.MCPService.register_mcp_server', mock_register):
                overlord = formation.start_overlord()

                # Check that no built-in MCPs were registered
                builtin_registrations = [s for s in registered_servers if s.startswith("builtin-")]
                assert len(builtin_registrations) == 0

            # Check system prompt has no MCP instructions
            system_message = overlord._create_overlord_system_message()
            assert "File Generation" not in system_message
            assert "generate_file" not in system_message

            # Cleanup
            formation.stop_overlord()
            formation.stop()

    @pytest.mark.asyncio
    async def test_granular_mcp_control(self):
        """Test granular control of built-in MCPs."""
        config = {
            "schema": "1.0.0",
            "id": "test-granular",
            "description": "Test granular MCP control",
            "llm": {
                "api_keys": {"openai": "test-key"},
                "models": [{"text": "gpt-3.5-turbo", "provider": "openai"}]
            },
            "agents": [{
                "schema": "1.0.0",
                "id": "test-agent",
                "name": "Test Agent",
                "description": "Test agent"
            }],
            "runtime": {
                "built_in_mcps": ["file-generation", "web-search"]  # Only these two
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "formation.yaml"
            import yaml
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            formation = Formation()
            formation.load(str(config_path))

            # Mock MCP registration
            registered_servers = []
            async def mock_register(server_id, **kwargs):
                registered_servers.append(server_id)
                return server_id

            from unittest.mock import patch
            with patch('muxi.services.mcp.service.MCPService.register_mcp_server', mock_register):
                overlord = formation.start_overlord()

                # Check only specified MCPs were registered
                builtin_registrations = [s for s in registered_servers if s.startswith("builtin-")]
                # Note: web-search doesn't exist yet, so only file-generation should register
                assert "builtin-file-generation" in builtin_registrations
                assert len(builtin_registrations) == 1  # Only file-generation exists

            formation.stop_overlord()
            formation.stop()

    @pytest.mark.asyncio
    async def test_runtime_config_validation(self):
        """Test validation of runtime configuration."""
        # Test invalid built_in_mcps type
        config = {
            "schema": "1.0.0",
            "id": "test-invalid",
            "description": "Test invalid runtime config",
            "llm": {
                "api_keys": {"openai": "test-key"},
                "models": [{"text": "gpt-3.5-turbo", "provider": "openai"}]
            },
            "agents": [{
                "schema": "1.0.0",
                "id": "test-agent",
                "name": "Test Agent",
                "description": "Test agent"
            }],
            "runtime": {
                "built_in_mcps": "invalid-string"  # Should be bool or list
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "formation.yaml"
            import yaml
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            formation = Formation()

            # Should raise validation error
            with pytest.raises(Exception) as exc_info:
                formation.load(str(config_path))

            assert "built_in_mcps" in str(exc_info.value)


class TestEndToEndFileGeneration:
    """Test end-to-end file generation through the runtime."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="Requires OPENAI_API_KEY for end-to-end test"
    )
    async def test_file_generation_through_chat(self):
        """Test file generation through overlord chat interface."""
        config = {
            "schema": "1.0.0",
            "id": "test-e2e",
            "description": "End-to-end file generation test",
            "llm": {
                "api_keys": {
                    "openai": os.environ.get("OPENAI_API_KEY", "test-key")
                },
                "models": [
                    {"text": "gpt-3.5-turbo", "provider": "openai"}
                ]
            },
            "agents": [{
                "schema": "1.0.0",
                "id": "file-creator",
                "name": "File Creator",
                "description": "Agent that creates files"
            }],
            "runtime": {
                "built_in_mcps": ["file-generation"]
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory for outputs
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                config_path = Path(tmpdir) / "formation.yaml"
                import yaml
                with open(config_path, "w") as f:
                    yaml.dump(config, f)

                formation = Formation()
                formation.load(str(config_path))
                overlord = formation.start_overlord()

                # Request file generation
                response = await overlord.chat(
                    "Create a simple bar chart showing sales data for Q1-Q4 with values 100, 150, 120, 180",
                    user_id="test-user"
                )

                # Check response mentions file creation
                assert "file" in response.lower() or "chart" in response.lower()

                # Check that a file was created in outputs directory
                outputs_dir = Path(tmpdir) / "outputs"
                if outputs_dir.exists():
                    files = list(outputs_dir.glob("*.png"))
                    assert len(files) > 0, "No chart file was created"

                formation.stop_overlord()
                formation.stop()

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
