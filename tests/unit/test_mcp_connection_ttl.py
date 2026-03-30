"""
Unit tests for MCP connection keep-alive with TTL.

Tests cover:
- LiveConnection dataclass (touch, idle tracking)
- Credential hashing for pool keys
- MCPService TTL configuration (global + per-server)
- Effective TTL resolution (per-server override > global default)
- Connection pool keying by (server_id, credentials)
- Reaper eligibility logic
- Validation of connection_ttl in formation config
"""

import time
from unittest.mock import MagicMock

from muxi.runtime.services.mcp.service import (
    DEFAULT_CONNECTION_TTL,
    LiveConnection,
    MCPService,
    _hash_credentials,
)


class TestLiveConnection:
    """Tests for the LiveConnection dataclass."""

    def test_touch_resets_last_used(self):
        conn = LiveConnection(handler=MagicMock(), server_name="srv")
        original = conn.last_used
        # Advance monotonic clock slightly
        time.sleep(0.01)
        conn.touch()
        assert conn.last_used > original

    def test_idle_seconds_increases(self):
        conn = LiveConnection(handler=MagicMock(), server_name="srv")
        time.sleep(0.05)
        assert conn.idle_seconds() >= 0.04

    def test_idle_seconds_resets_after_touch(self):
        conn = LiveConnection(handler=MagicMock(), server_name="srv")
        time.sleep(0.05)
        conn.touch()
        assert conn.idle_seconds() < 0.02

    def test_default_credentials_hash(self):
        conn = LiveConnection(handler=MagicMock(), server_name="srv")
        assert conn.credentials_hash == ""


class TestHashCredentials:
    """Tests for the _hash_credentials helper."""

    def test_none_returns_no_creds(self):
        assert _hash_credentials(None) == "no_creds"

    def test_empty_dict_returns_no_creds(self):
        assert _hash_credentials({}) == "no_creds"

    def test_same_input_same_hash(self):
        creds = {"type": "bearer", "token": "abc123"}
        assert _hash_credentials(creds) == _hash_credentials(creds)

    def test_different_input_different_hash(self):
        creds_a = {"type": "bearer", "token": "abc"}
        creds_b = {"type": "bearer", "token": "xyz"}
        assert _hash_credentials(creds_a) != _hash_credentials(creds_b)

    def test_key_order_does_not_matter(self):
        creds_a = {"token": "abc", "type": "bearer"}
        creds_b = {"type": "bearer", "token": "abc"}
        assert _hash_credentials(creds_a) == _hash_credentials(creds_b)

    def test_hash_length(self):
        creds = {"type": "bearer", "token": "secret"}
        h = _hash_credentials(creds)
        assert len(h) == 16


class TestMCPServiceTTLConfig:
    """Tests for TTL configuration on MCPService."""

    def _make_service(self):
        # Reset singleton so we get a fresh instance
        MCPService._instance = None
        return MCPService()

    def test_default_ttl(self):
        svc = self._make_service()
        assert svc._connection_ttl == DEFAULT_CONNECTION_TTL

    def test_configure_global_ttl(self):
        svc = self._make_service()
        svc.configure_connection_ttl(global_ttl=600)
        assert svc._connection_ttl == 600.0

    def test_configure_per_server_ttl(self):
        svc = self._make_service()
        svc.configure_connection_ttl(per_server={"ms365": 120, "github": 0})
        assert svc._per_server_ttl["ms365"] == 120.0
        assert svc._per_server_ttl["github"] == 0.0

    def test_effective_ttl_uses_per_server_override(self):
        svc = self._make_service()
        svc.configure_connection_ttl(global_ttl=300, per_server={"ms365": 60})
        assert svc._effective_ttl("ms365") == 60.0

    def test_effective_ttl_falls_back_to_global(self):
        svc = self._make_service()
        svc.configure_connection_ttl(global_ttl=300, per_server={"ms365": 60})
        assert svc._effective_ttl("some-other-server") == 300.0

    def test_configure_ttl_zero_means_ephemeral(self):
        svc = self._make_service()
        svc.configure_connection_ttl(global_ttl=0)
        assert svc._effective_ttl("any-server") == 0.0

    def test_live_connections_initially_empty(self):
        svc = self._make_service()
        assert svc._live_connections == {}

    def test_reaper_not_started_initially(self):
        svc = self._make_service()
        assert svc._reaper_task is None


class TestConnectionPoolKeying:
    """Tests for connection pool key generation."""

    def test_no_creds_key(self):
        key = f"server-a:{_hash_credentials(None)}"
        assert key == "server-a:no_creds"

    def test_different_users_different_keys(self):
        creds_alice = {"type": "bearer", "token": "alice-token"}
        creds_bob = {"type": "bearer", "token": "bob-token"}
        key_alice = f"ms365:{_hash_credentials(creds_alice)}"
        key_bob = f"ms365:{_hash_credentials(creds_bob)}"
        assert key_alice != key_bob

    def test_same_creds_same_key(self):
        creds = {"type": "bearer", "token": "shared"}
        key_a = f"ms365:{_hash_credentials(creds)}"
        key_b = f"ms365:{_hash_credentials(creds)}"
        assert key_a == key_b

    def test_different_servers_different_keys(self):
        creds = {"type": "bearer", "token": "same"}
        key_a = f"server-a:{_hash_credentials(creds)}"
        key_b = f"server-b:{_hash_credentials(creds)}"
        assert key_a != key_b


class TestValidationConnectionTTL:
    """Tests for connection_ttl validation in formation config."""

    def _validate_mcp(self, mcp_config):
        from muxi.runtime.formation.config.validation import FormationValidator

        validator = FormationValidator()
        validator._validate_mcp_config(mcp_config)
        return validator.result

    def test_valid_global_ttl(self):
        result = self._validate_mcp({"connection_ttl": 300})
        assert result.is_valid, result.errors

    def test_valid_global_ttl_zero(self):
        result = self._validate_mcp({"connection_ttl": 0})
        assert result.is_valid, result.errors

    def test_valid_global_ttl_float(self):
        result = self._validate_mcp({"connection_ttl": 60.5})
        assert result.is_valid, result.errors

    def test_invalid_global_ttl_negative(self):
        result = self._validate_mcp({"connection_ttl": -1})
        assert not result.is_valid
        assert any("connection_ttl" in e for e in result.errors)

    def test_invalid_global_ttl_string(self):
        result = self._validate_mcp({"connection_ttl": "five"})
        assert not result.is_valid
        assert any("connection_ttl" in e for e in result.errors)

    def test_valid_per_server_ttl_http(self):
        result = self._validate_mcp({
            "servers": [{
                "schema": "1.0.0",
                "id": "my-mcp",
                "description": "test",
                "type": "http",
                "endpoint": "https://example.com/mcp",
                "connection_ttl": 600,
            }]
        })
        assert result.is_valid, result.errors

    def test_invalid_per_server_ttl_http(self):
        result = self._validate_mcp({
            "servers": [{
                "schema": "1.0.0",
                "id": "my-mcp",
                "description": "test",
                "type": "http",
                "endpoint": "https://example.com/mcp",
                "connection_ttl": -10,
            }]
        })
        assert not result.is_valid
        assert any("connection_ttl" in e for e in result.errors)

    def test_valid_per_server_ttl_command(self):
        result = self._validate_mcp({
            "servers": [{
                "schema": "1.0.0",
                "id": "local-tool",
                "description": "test",
                "type": "command",
                "command": "echo",
                "connection_ttl": 0,
            }]
        })
        assert result.is_valid, result.errors
