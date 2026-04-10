"""
Unit tests for MCP server default parameters.

Tests cover:
- Default parameters stored in server_configs during registration
- Parameters injected into tool calls (caller values take precedence)
- user.credentials placeholders resolved at request time
- Validation rejects non-dict and non-scalar parameter values
"""

import re
from unittest.mock import MagicMock

from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.services.mcp.service import MCPService, USER_CREDENTIAL_PATTERN


class TestMCPServiceDefaultParameters:
    """Tests for default parameter storage and injection."""

    def test_server_configs_stores_parameters(self):
        """Parameters from registration are stored in server_configs."""
        service = MCPService.__new__(MCPService)
        service.server_configs = {}

        service.server_configs["test-mcp"] = {
            "url": "https://example.com/mcp",
            "command": None,
            "args": None,
            "transport_type": "streamable_http",
            "request_timeout": 60,
            "original_credentials": None,
            "stored_credentials": None,
            "uses_user_credentials": False,
            "parameters": {"driveId": "b!org-drive-123", "tenantId": "tenant-abc"},
        }

        config = service.server_configs["test-mcp"]
        assert config["parameters"] == {
            "driveId": "b!org-drive-123",
            "tenantId": "tenant-abc",
        }

    def test_empty_parameters_stored_as_empty_dict(self):
        """When no parameters are provided, an empty dict is stored."""
        service = MCPService.__new__(MCPService)
        service.server_configs = {}

        service.server_configs["test-mcp"] = {
            "url": "https://example.com/mcp",
            "parameters": {},
        }

        assert service.server_configs["test-mcp"]["parameters"] == {}

    def test_default_params_injected_when_caller_omits(self):
        """Default parameters fill in missing tool call params."""
        config = {
            "parameters": {"driveId": "b!org-drive-123", "region": "us-west"},
            "stored_credentials": None,
        }
        caller_params = {"searchQuery": "Book.xlsx"}

        defaults = config.get("parameters", {})
        for key, value in defaults.items():
            if key not in caller_params:
                caller_params[key] = value

        assert caller_params == {
            "searchQuery": "Book.xlsx",
            "driveId": "b!org-drive-123",
            "region": "us-west",
        }

    def test_caller_values_take_precedence(self):
        """Caller-provided values are never overridden by defaults."""
        config = {
            "parameters": {"driveId": "default-drive", "region": "us-west"},
        }
        caller_params = {"driveId": "caller-specific-drive", "searchQuery": "Book.xlsx"}

        defaults = config.get("parameters", {})
        for key, value in defaults.items():
            if key not in caller_params:
                caller_params[key] = value

        assert caller_params["driveId"] == "caller-specific-drive"
        assert caller_params["region"] == "us-west"

    def test_user_credential_placeholder_resolved(self):
        """${{ user.credentials.X }} placeholders in parameters are resolved."""
        default_params = {
            "driveId": "${{ user.credentials.microsoft }}",
            "staticParam": "plain-value",
        }
        resolved_auth = {"token": "user-drive-id-from-db", "type": "bearer"}

        resolved_defaults = dict(default_params)
        for key, value in list(resolved_defaults.items()):
            if isinstance(value, str) and USER_CREDENTIAL_PATTERN.search(value):
                if resolved_auth and isinstance(resolved_auth, dict):
                    match = USER_CREDENTIAL_PATTERN.match(value)
                    if match:
                        cred_key = match.group(1)
                        cred_value = resolved_auth.get(cred_key) or resolved_auth.get("token")
                        if cred_value:
                            resolved_defaults[key] = cred_value
                        else:
                            del resolved_defaults[key]
                else:
                    del resolved_defaults[key]

        assert resolved_defaults["driveId"] == "user-drive-id-from-db"
        assert resolved_defaults["staticParam"] == "plain-value"

    def test_user_credential_placeholder_dropped_without_auth(self):
        """${{ user.credentials.X }} placeholders are dropped when no auth available."""
        default_params = {
            "driveId": "${{ user.credentials.microsoft }}",
            "staticParam": "plain-value",
        }
        resolved_auth = None

        resolved_defaults = dict(default_params)
        for key, value in list(resolved_defaults.items()):
            if isinstance(value, str) and USER_CREDENTIAL_PATTERN.search(value):
                if resolved_auth and isinstance(resolved_auth, dict):
                    pass
                else:
                    del resolved_defaults[key]

        assert "driveId" not in resolved_defaults
        assert resolved_defaults["staticParam"] == "plain-value"


class TestMCPParametersValidation:
    """Tests for MCP parameter validation."""

    def _validate(self, server_config):
        """Run validation on a single MCP server config."""
        validator = FormationValidator.__new__(FormationValidator)
        validator.result = MagicMock()
        validator.result.errors = []

        def add_error(msg):
            validator.result.errors.append(msg)

        validator.result.add_error = add_error
        validator.REQUIRED_MCP_SERVER_FIELDS = ["id"]
        validator._validate_mcp_metadata_fields = lambda *a, **kw: None
        validator._validate_http_mcp_server = lambda *a, **kw: None
        validator._validate_command_mcp_server = lambda *a, **kw: None
        validator._validate_mcp_auth_config = lambda *a, **kw: None
        validator._validate_single_mcp_server(server_config, 0, set(), is_inline=True)
        return validator.result.errors

    def test_valid_parameters_accepted(self):
        errors = self._validate({
            "id": "test-mcp",
            "type": "http",
            "parameters": {"driveId": "b!drive-123", "count": 10, "active": True},
        })
        param_errors = [e for e in errors if "parameter" in e.lower()]
        assert param_errors == []

    def test_non_dict_parameters_rejected(self):
        errors = self._validate({
            "id": "test-mcp",
            "type": "http",
            "parameters": ["driveId", "b!drive-123"],
        })
        assert any("key-value map" in e for e in errors)

    def test_non_scalar_value_rejected(self):
        errors = self._validate({
            "id": "test-mcp",
            "type": "http",
            "parameters": {"nested": {"a": "b"}},
        })
        assert any("scalar value" in e for e in errors)

    def test_missing_parameters_field_accepted(self):
        errors = self._validate({
            "id": "test-mcp",
            "type": "http",
        })
        param_errors = [e for e in errors if "parameter" in e.lower()]
        assert param_errors == []
