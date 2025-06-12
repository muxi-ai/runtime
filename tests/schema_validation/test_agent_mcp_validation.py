#!/usr/bin/env python3
"""
Test agent-level MCP server validation according to SCHEMA_GUIDE.md

This test module validates:
1. Agent-level MCP server configuration validation
2. Required fields for agent MCP servers
3. Type-specific validation (HTTP vs command)
4. Agent-specific overrides (retry_attempts, timeout_seconds, active)
5. Authentication configuration for agent MCP servers
"""

import pytest
import tempfile
import yaml

# Import the validation classes
from src.muxi.runtime.config.validation import FormationValidator


class TestAgentMCPValidation:
    """Test agent-level MCP server validation according to SCHEMA_GUIDE.md"""

    def setup_method(self):
        """Set up test fixtures"""
        self.validator = FormationValidator()

    def _create_test_formation(self, agent_mcp_servers):
        """Helper to create a test formation with agent MCP servers"""
        return {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation for agent MCP validation',
            'agents': [{
                'schema': '1.0.0',
                'id': 'test-agent',
                'name': 'Test Agent',
                'description': 'Test agent with MCP servers',
                'mcp_servers': agent_mcp_servers
            }]
        }

    def test_valid_agent_http_mcp_server(self):
        """Test valid agent HTTP MCP server configuration"""
        mcp_servers = [{
            'id': 'weather_service',
            'description': 'External weather service',
            'type': 'http',
            'endpoint': 'https://api.weather.com/mcp',
            'active': True,
            'retry_attempts': 3,
            'timeout_seconds': 30
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_valid_agent_command_mcp_server(self):
        """Test valid agent command MCP server configuration"""
        mcp_servers = [{
            'id': 'local_tools',
            'description': 'Local development tools',
            'type': 'command',
            'command': ['python', '-m', 'mcp_tools'],
            'active': True,
            'retry_attempts': 2
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_agent_mcp_server_with_auth(self):
        """Test agent MCP server with authentication"""
        mcp_servers = [{
            'id': 'api_service',
            'description': 'API service with authentication',
            'type': 'http',
            'endpoint': 'https://api.example.com/mcp',
            'auth': {
                'type': 'api_key',
                'header': 'X-API-Key',
                'key': '${{ secrets.API_KEY }}'
            }
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_missing_required_field_id(self):
        """Test missing required field 'id'"""
        mcp_servers = [{
            'description': 'Service without ID',
            'type': 'http',
            'endpoint': 'https://api.example.com/mcp'
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('missing required field: id' in error for error in result.errors)

    def test_missing_required_field_description(self):
        """Test missing required field 'description'"""
        mcp_servers = [{
            'id': 'test_service',
            'type': 'http',
            'endpoint': 'https://api.example.com/mcp'
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('missing required field: description' in error for error in result.errors)

    def test_missing_required_field_type(self):
        """Test missing required field 'type'"""
        mcp_servers = [{
            'id': 'test_service',
            'description': 'Service without type',
            'endpoint': 'https://api.example.com/mcp'
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('missing required field: type' in error for error in result.errors)

    def test_duplicate_server_ids(self):
        """Test duplicate MCP server IDs within an agent"""
        mcp_servers = [
            {
                'id': 'duplicate_service',
                'description': 'First service',
                'type': 'http',
                'endpoint': 'https://api1.example.com/mcp'
            },
            {
                'id': 'duplicate_service',
                'description': 'Second service with same ID',
                'type': 'http',
                'endpoint': 'https://api2.example.com/mcp'
            }
        ]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('duplicate MCP server id' in error for error in result.errors)

    def test_invalid_server_type(self):
        """Test invalid server type"""
        mcp_servers = [{
            'id': 'invalid_service',
            'description': 'Service with invalid type',
            'type': 'invalid_type',
            'endpoint': 'https://api.example.com/mcp'
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('invalid type' in error and 'Valid types are' in error for error in result.errors)

    def test_http_server_missing_endpoint(self):
        """Test HTTP server missing endpoint field"""
        mcp_servers = [{
            'id': 'http_service',
            'description': 'HTTP service without endpoint',
            'type': 'http'
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('must have \'endpoint\' field' in error for error in result.errors)

    def test_invalid_endpoint_format(self):
        """Test invalid endpoint format"""
        mcp_servers = [{
            'id': 'http_service',
            'description': 'HTTP service with invalid endpoint',
            'type': 'http',
            'endpoint': 'not-a-valid-url'
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('endpoint\' must start with http' in error for error in result.errors)

    def test_command_server_missing_command(self):
        """Test command server missing command field"""
        mcp_servers = [{
            'id': 'command_service',
            'description': 'Command service without command',
            'type': 'command'
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('must have \'command\' field' in error for error in result.errors)

    def test_invalid_command_type(self):
        """Test invalid command type (not string or list)"""
        mcp_servers = [{
            'id': 'command_service',
            'description': 'Command service with invalid command type',
            'type': 'command',
            'command': 123  # Should be string or list
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('command\' must be a string or list' in error for error in result.errors)

    def test_invalid_retry_attempts(self):
        """Test invalid retry_attempts value"""
        mcp_servers = [{
            'id': 'test_service',
            'description': 'Service with invalid retry attempts',
            'type': 'http',
            'endpoint': 'https://api.example.com/mcp',
            'retry_attempts': -1  # Should be non-negative
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('retry_attempts\' must be a non-negative integer' in error for error in result.errors)

    def test_invalid_timeout_seconds(self):
        """Test invalid timeout_seconds value"""
        mcp_servers = [{
            'id': 'test_service',
            'description': 'Service with invalid timeout',
            'type': 'http',
            'endpoint': 'https://api.example.com/mcp',
            'timeout_seconds': 0  # Should be positive
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('timeout_seconds\' must be a positive integer' in error for error in result.errors)

    def test_invalid_active_type(self):
        """Test invalid active field type"""
        mcp_servers = [{
            'id': 'test_service',
            'description': 'Service with invalid active type',
            'type': 'http',
            'endpoint': 'https://api.example.com/mcp',
            'active': 'true'  # Should be boolean
        }]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('active\' must be a boolean' in error for error in result.errors)

    def test_invalid_mcp_servers_type(self):
        """Test invalid mcp_servers type (not a list)"""
        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation for agent MCP validation',
            'agents': [{
                'schema': '1.0.0',
                'id': 'test-agent',
                'name': 'Test Agent',
                'description': 'Test agent with invalid MCP servers',
                'mcp_servers': 'not-a-list'  # Should be a list
            }]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('mcp_servers must be a list' in error for error in result.errors)

    def test_multiple_agent_mcp_servers(self):
        """Test multiple valid MCP servers for an agent"""
        mcp_servers = [
            {
                'id': 'weather_service',
                'description': 'Weather API service',
                'type': 'http',
                'endpoint': 'https://api.weather.com/mcp',
                'timeout_seconds': 30
            },
            {
                'id': 'local_tools',
                'description': 'Local development tools',
                'type': 'command',
                'command': 'python -m dev_tools',
                'retry_attempts': 2
            }
        ]

        formation = self._create_test_formation(mcp_servers)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
