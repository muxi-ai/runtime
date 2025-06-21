"""
Tests for dynamic component addition functionality in Formation.

Tests the new add_agent(), add_mcp(), remove_mcp(), list_mcp_servers(),
and get_mcp_status() methods along with schema loading and validation.
"""

import pytest
import tempfile
import os
import yaml
from unittest.mock import Mock, AsyncMock, patch

# Import the classes we're testing
from src.muxi.runtime.formation.formation import Formation
from src.muxi.runtime.datatypes.exceptions import (
    OverlordStateError,
    MCPServerNotFoundError,
    ConfigurationNotFoundError
)


class TestSchemaLoading:
    """Test schema loading functionality with both inline dicts and file paths."""

    @pytest.fixture
    async def formation(self):
        """Create a formation instance for testing."""
        formation = Formation()
        # Mock the secrets manager
        formation.secrets_manager = Mock()
        formation.secrets_manager.interpolate_secrets = AsyncMock(side_effect=lambda x: x)
        formation.config = {}
        return formation

    @pytest.fixture
    def valid_agent_schema(self):
        """Valid agent schema for testing."""
        return {
            "schema": "1.0.0",
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent for unit testing",
            "system_message": "You are a helpful test agent."
        }

    @pytest.fixture
    def valid_mcp_schema(self):
        """Valid MCP schema for testing."""
        return {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "A test MCP server",
            "type": "command",
            "command": "python",
            "args": ["-m", "test_server"]
        }

    async def test_resolve_schema_inline_dict(self, formation, valid_agent_schema):
        """Test resolving schema from inline dictionary."""
        result = await formation._resolve_schema(valid_agent_schema, "agent")
        assert result == valid_agent_schema
        # Verify secrets interpolation was called
        formation.secrets_manager.interpolate_secrets.assert_called_once()

    async def test_resolve_schema_file_path(self, formation, valid_agent_schema):
        """Test resolving schema from file path."""
        # Create a temporary YAML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(valid_agent_schema, f)
            temp_path = f.name

        try:
            # Mock FormationLoader
            with patch('src.muxi.runtime.formation.formation.FormationLoader') as mock_loader:
                mock_instance = Mock()
                mock_instance.load = AsyncMock(return_value=valid_agent_schema)
                mock_loader.return_value = mock_instance

                result = await formation._resolve_schema(temp_path, "agent")
                assert result == valid_agent_schema
                mock_instance.load.assert_called_once()
        finally:
            os.unlink(temp_path)

    async def test_resolve_schema_invalid_type(self, formation):
        """Test that invalid schema types raise TypeError."""
        with pytest.raises(TypeError, match="Schema must be dict or str"):
            await formation._resolve_schema(123, "agent")

    async def test_resolve_schema_file_not_found(self, formation):
        """Test behavior when schema file doesn't exist."""
        with patch('src.muxi.runtime.formation.formation.FormationLoader') as mock_loader:
            mock_instance = Mock()
            mock_instance.load = AsyncMock(side_effect=ConfigurationNotFoundError("not_found.yaml"))
            mock_loader.return_value = mock_instance

            with pytest.raises(ValueError, match="Failed to load agent schema from not_found.yaml"):
                await formation._resolve_schema("not_found.yaml", "agent")


class TestAgentManagement:
    """Test agent addition with schema support."""

    @pytest.fixture
    def formation_with_overlord(self):
        """Create a formation with a mocked running overlord."""
        formation = Formation()
        formation._is_running = True
        formation.config = {}

        # Mock overlord
        mock_overlord = Mock()

        # Mock the create methods to return the ID as expected
        mock_overlord.create_agent_from_schema = AsyncMock(return_value="test-agent")
        mock_overlord.create_mcp_server_from_schema = AsyncMock(return_value="test-mcp")

        # Mock list methods to return empty initially
        mock_overlord.list_agents = AsyncMock(return_value={})
        mock_overlord.list_mcp_servers = AsyncMock(return_value={})

        # Mock remove methods
        mock_overlord.remove_agent = AsyncMock(return_value=True)
        mock_overlord.remove_mcp_server = AsyncMock(return_value=True)

        formation._overlord = mock_overlord

        # Mock secrets manager for validation
        mock_secrets_manager = Mock()
        mock_secrets_manager.interpolate_secrets = AsyncMock(side_effect=lambda x: x)  # Return unchanged
        formation.secrets_manager = mock_secrets_manager

        return formation

    @pytest.fixture
    def valid_agent_schema(self):
        return {
            "schema": "1.0.0",
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent for unit testing"
        }

    async def test_add_agent_inline_schema(self, formation_with_overlord, valid_agent_schema):
        """Test adding agent with inline schema."""
        result = await formation_with_overlord.add_agent(valid_agent_schema)
        assert result == "test-agent"
        formation_with_overlord._overlord.create_agent_from_schema.assert_called_once_with(valid_agent_schema)

    async def test_add_agent_not_running(self, valid_agent_schema):
        """Test that add_agent fails when formation not running."""
        formation = Formation()
        formation._is_running = False

        with pytest.raises(OverlordStateError):
            await formation.add_agent(valid_agent_schema)

    async def test_add_agent_duplicate_id(self, formation_with_overlord, valid_agent_schema):
        """Test that duplicate agent IDs are rejected."""
        # Add existing agent to loaded config
        formation_with_overlord.config = {
            "agents": [{"id": "test-agent", "name": "Existing Agent"}]
        }

        with pytest.raises(ValueError, match="Agent ID 'test-agent' already exists"):
            await formation_with_overlord.add_agent(valid_agent_schema)

    async def test_add_agent_missing_required_field(self, formation_with_overlord):
        """Test that schemas missing required fields are rejected."""
        invalid_schema = {
            "schema": "1.0.0",
            "id": "test-agent"
            # Missing name and description
        }

        with pytest.raises(ValueError, match="missing required field"):
            await formation_with_overlord.add_agent(invalid_schema)


class TestMCPManagement:
    """Test MCP server management functionality."""

    @pytest.fixture
    def formation_with_overlord(self):
        """Create a formation with a mocked running overlord."""
        formation = Formation()
        formation._is_running = True
        formation.config = {}

        # Mock overlord
        mock_overlord = Mock()

        # Mock the create methods to return the ID as expected
        mock_overlord.create_agent_from_schema = AsyncMock(return_value="test-agent")
        mock_overlord.create_mcp_server_from_schema = AsyncMock(return_value="test-mcp")

        # Mock list methods to return empty initially
        mock_overlord.list_agents = AsyncMock(return_value={})
        mock_overlord.list_mcp_servers = AsyncMock(return_value={})

        # Mock remove methods
        mock_overlord.remove_agent = AsyncMock(return_value=True)
        mock_overlord.remove_mcp_server = AsyncMock(return_value=True)

        formation._overlord = mock_overlord

        # Mock secrets manager for validation
        mock_secrets_manager = Mock()
        mock_secrets_manager.interpolate_secrets = AsyncMock(side_effect=lambda x: x)  # Return unchanged
        formation.secrets_manager = mock_secrets_manager

        return formation

    @pytest.fixture
    def valid_mcp_schema(self):
        return {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "A test MCP server",
            "type": "command",
            "command": "python",
            "args": ["-m", "test_server"]
        }

    async def test_add_mcp_inline_schema(self, formation_with_overlord, valid_mcp_schema):
        """Test adding MCP server with inline schema."""
        result = await formation_with_overlord.add_mcp(valid_mcp_schema)
        assert result == "test-mcp"
        formation_with_overlord._overlord.create_mcp_server_from_schema.assert_called_once_with(valid_mcp_schema)

    async def test_add_mcp_not_running(self, valid_mcp_schema):
        """Test that add_mcp fails when formation not running."""
        formation = Formation()
        formation._is_running = False

        with pytest.raises(OverlordStateError):
            await formation.add_mcp(valid_mcp_schema)

    async def test_add_mcp_duplicate_id(self, formation_with_overlord, valid_mcp_schema):
        """Test that duplicate MCP server IDs are rejected."""
        formation_with_overlord.config = {
            "mcp": {"servers": [{"id": "test-mcp", "description": "Existing server"}]}
        }

        with pytest.raises(ValueError, match="MCP server ID 'test-mcp' already exists"):
            await formation_with_overlord.add_mcp(valid_mcp_schema)

    async def test_add_mcp_missing_required_field(self, formation_with_overlord):
        """Test that MCP schemas missing required fields are rejected."""
        invalid_schema = {
            "schema": "1.0.0",
            "id": "test-mcp"
            # Missing description and type
        }

        with pytest.raises(ValueError, match="missing required field"):
            await formation_with_overlord.add_mcp(invalid_schema)

    async def test_add_mcp_invalid_type(self, formation_with_overlord):
        """Test that invalid MCP server types are rejected."""
        invalid_schema = {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "Test server",
            "type": "invalid_type"
        }

        with pytest.raises(ValueError, match="Invalid MCP server type"):
            await formation_with_overlord.add_mcp(invalid_schema)

    def test_remove_mcp_sync(self, formation_with_overlord):
        """Test synchronous MCP server removal."""
        # Mock asyncio to simulate no running event loop
        with patch('asyncio.get_running_loop', side_effect=RuntimeError("No loop")):
            with patch('asyncio.run') as mock_run:
                mock_run.return_value = True

                result = formation_with_overlord.remove_mcp("test-mcp")
                assert result is True
                mock_run.assert_called_once()

    async def test_remove_mcp_async(self, formation_with_overlord):
        """Test asynchronous MCP server removal."""
        result = await formation_with_overlord.remove_mcp_async("test-mcp")
        assert result is True
        formation_with_overlord._overlord.remove_mcp_server.assert_called_once_with("test-mcp")

    async def test_remove_mcp_not_running(self):
        """Test that remove_mcp fails when formation not running."""
        formation = Formation()
        formation._is_running = False

        with pytest.raises(OverlordStateError):
            formation.remove_mcp("test-mcp")

    async def test_list_mcp_servers(self, formation_with_overlord):
        """Test listing MCP servers."""
        # Update the mock to return test data
        formation_with_overlord._overlord.list_mcp_servers.return_value = {
            "test-mcp": {"id": "test-mcp", "status": "connected"}
        }

        result = await formation_with_overlord.list_mcp_servers()
        assert "test-mcp" in result
        formation_with_overlord._overlord.list_mcp_servers.assert_called_once()

    async def test_get_mcp_status_exists(self, formation_with_overlord):
        """Test getting status for existing MCP server."""
        # Update the mock to return test data
        formation_with_overlord._overlord.list_mcp_servers.return_value = {
            "test-mcp": {"id": "test-mcp", "status": "connected"}
        }

        result = await formation_with_overlord.get_mcp_status("test-mcp")
        assert result["id"] == "test-mcp"
        assert result["status"] == "connected"

    async def test_get_mcp_status_not_found(self, formation_with_overlord):
        """Test getting status for non-existent MCP server."""
        formation_with_overlord._overlord.list_mcp_servers.return_value = {}

        with pytest.raises(MCPServerNotFoundError, match="MCP server 'nonexistent' not found"):
            await formation_with_overlord.get_mcp_status("nonexistent")


class TestSchemaValidation:
    """Test schema validation logic."""

    @pytest.fixture
    async def formation(self):
        formation = Formation()
        formation.config = {}
        return formation

    async def test_validate_agent_schema_valid(self, formation):
        """Test validation of valid agent schema."""
        valid_schema = {
            "schema": "1.0.0",
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent"
        }
        # Should not raise any exception
        formation._validate_agent_schema(valid_schema)

    async def test_validate_agent_schema_missing_schema_field(self, formation):
        """Test validation fails for missing schema field."""
        invalid_schema = {
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent"
        }
        with pytest.raises(ValueError, match="missing required field: 'schema'"):
            formation._validate_agent_schema(invalid_schema)

    async def test_validate_agent_schema_invalid_version(self, formation):
        """Test validation fails for invalid schema version."""
        invalid_schema = {
            "schema": "2.0.0",  # Invalid version
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent"
        }
        with pytest.raises(ValueError, match="Unsupported schema version"):
            formation._validate_agent_schema(invalid_schema)

    async def test_validate_mcp_schema_valid_command(self, formation):
        """Test validation of valid command-type MCP schema."""
        valid_schema = {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "Test MCP server",
            "type": "command",
            "command": "python"
        }
        # Should not raise any exception
        formation._validate_mcp_schema(valid_schema)

    async def test_validate_mcp_schema_valid_http(self, formation):
        """Test validation of valid HTTP-type MCP schema."""
        valid_schema = {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "Test MCP server",
            "type": "http",
            "endpoint": "http://localhost:3000"
        }
        # Should not raise any exception
        formation._validate_mcp_schema(valid_schema)

    async def test_validate_mcp_schema_command_missing_command(self, formation):
        """Test validation fails for command-type MCP missing command field."""
        invalid_schema = {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "Test MCP server",
            "type": "command"
            # Missing command field
        }
        with pytest.raises(ValueError, match="missing 'command' field"):
            formation._validate_mcp_schema(invalid_schema)

    async def test_validate_mcp_schema_http_missing_endpoint(self, formation):
        """Test validation fails for HTTP-type MCP missing endpoint field."""
        invalid_schema = {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "Test MCP server",
            "type": "http"
            # Missing endpoint field
        }
        with pytest.raises(ValueError, match="missing 'endpoint' field"):
            formation._validate_mcp_schema(invalid_schema)

    async def test_validate_mcp_schema_invalid_endpoint(self, formation):
        """Test validation fails for invalid endpoint URL."""
        invalid_schema = {
            "schema": "1.0.0",
            "id": "test-mcp",
            "description": "Test MCP server",
            "type": "http",
            "endpoint": "invalid-url"  # Invalid URL format
        }
        with pytest.raises(ValueError, match="Invalid endpoint URL"):
            formation._validate_mcp_schema(invalid_schema)


class TestEventLoopHandling:
    """Test proper event loop handling in sync/async contexts."""

    @pytest.fixture
    async def formation_with_overlord(self):
        formation = Formation()
        formation._is_running = True
        formation._overlord = AsyncMock()
        formation._overlord.remove_mcp_server = AsyncMock(return_value=True)
        return formation

    def test_remove_mcp_with_event_loop(self, formation_with_overlord):
        """Test remove_mcp handles existing event loop correctly."""
        # Simulate being called from within an event loop
        with patch('asyncio.get_running_loop'):
            with patch('threading.Thread') as mock_thread:
                mock_thread_instance = Mock()
                mock_thread.return_value = mock_thread_instance

                formation_with_overlord.remove_mcp("test-mcp")

                # Verify thread was created and started
                mock_thread.assert_called_once()
                mock_thread_instance.start.assert_called_once()
                mock_thread_instance.join.assert_called_once()

    def test_remove_mcp_no_event_loop(self, formation_with_overlord):
        """Test remove_mcp handles no event loop correctly."""
        # Simulate no running event loop
        with patch('asyncio.get_running_loop', side_effect=RuntimeError("No loop")):
            with patch('asyncio.run') as mock_run:
                mock_run.return_value = True

                result = formation_with_overlord.remove_mcp("test-mcp")
                assert result is True
                mock_run.assert_called_once()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
