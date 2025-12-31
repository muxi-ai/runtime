"""
Test hardcoded secret masking in API responses.

This test verifies that hardcoded secrets (non-placeholder values) are masked
in API responses for security.
"""

import pytest
from muxi.runtime.formation.server.secrets import restore_secret_placeholders


def test_hardcoded_secret_masking_in_api_response():
    """Test that hardcoded secrets are masked in API responses."""
    # Simulate a config that would be returned from an API endpoint
    config = {
        "llm": {
            "api_keys": {
                "openai": "sk-proj-actual-openai-key-12345",  # Hardcoded, should be masked
                "anthropic": "${{ secrets.ANTHROPIC_KEY }}",  # Placeholder, should not be masked
                "google": "AIzaSyD-actual-google-key-67890"  # Hardcoded, should be masked
            }
        },
        "server": {
            "api_keys": {
                "admin_key": "sk_muxi_admin_actual_key",  # Hardcoded, should be masked
                "client_key": "${{ secrets.CLIENT_KEY }}"  # Placeholder, should not be masked
            }
        },
        "agents": [
            {
                "id": "agent1",
                "model": {
                    "api_key": "sk-agent-actual-key-abcdef"  # Hardcoded, should be masked
                }
            }
        ],
        "mcp": {
            "servers": [
                {
                    "id": "server1",
                    "env": {
                        "API_TOKEN": "actual-mcp-token-123456",  # Hardcoded, should be masked
                        "NORMAL_VAR": "just-a-normal-value"  # Not a secret
                    }
                }
            ]
        }
    }

    # Simulate placeholder registry (some values have placeholders)
    placeholder_registry = {
        "llm.api_keys.anthropic": "${{ secrets.ANTHROPIC_KEY }}",
        "server.api_keys.client_key": "${{ secrets.CLIENT_KEY }}"
    }

    # Apply restoration (which includes hardcoded secret masking)
    safe_config = restore_secret_placeholders(config, placeholder_registry)

    # Verify placeholders are restored
    assert safe_config["llm"]["api_keys"]["anthropic"] == "${{ secrets.ANTHROPIC_KEY }}"
    assert safe_config["server"]["api_keys"]["client_key"] == "${{ secrets.CLIENT_KEY }}"

    # Verify hardcoded secrets are masked (shows first 3 and last 3 chars)
    assert safe_config["llm"]["api_keys"]["openai"] == "sk-••••••••345"
    assert safe_config["llm"]["api_keys"]["google"] == "AIz••••••••890"
    assert safe_config["server"]["api_keys"]["admin_key"] == "sk_••••••••_key"
    assert safe_config["agents"][0]["model"]["api_key"] == "sk-••••••••def"

    # Verify MCP environment variables are handled
    assert "••••••••" in safe_config["mcp"]["servers"][0]["env"]["API_TOKEN"]
    assert safe_config["mcp"]["servers"][0]["env"]["NORMAL_VAR"] == "just-a-normal-value"


def test_masking_with_empty_placeholder_registry():
    """Test that hardcoded secrets are masked even with no placeholders."""
    config = {
        "llm": {
            "api_keys": {
                "openai": "sk-actual-key-12345"
            }
        }
    }

    # Apply restoration with empty registry
    safe_config = restore_secret_placeholders(config, {})

    # Hardcoded secret should still be masked (shows first 3 and last 3 chars)
    assert safe_config["llm"]["api_keys"]["openai"] == "sk-••••••••345"


def test_already_masked_values_preserved():
    """Test that already masked values are not re-masked."""
    config = {
        "llm": {
            "api_keys": {
                "openai": "sk-••••••••xyz",  # Already masked
                "google": "***REDACTED***"  # Already masked differently
            }
        }
    }

    safe_config = restore_secret_placeholders(config, {})

    # Already masked values should remain unchanged
    assert safe_config["llm"]["api_keys"]["openai"] == "sk-••••••••xyz"
    assert safe_config["llm"]["api_keys"]["google"] == "***REDACTED***"


def test_short_values_masked_generically():
    """Test that short values get generic masking at known secret paths."""
    config = {
        "server": {
            "api_keys": {
                "admin_key": "short",  # Too short for masking
                "client_key": "12345678"  # 8 chars, minimum for masking
            }
        },
        "llm": {
            "api_keys": {
                "openai": "tiny"  # Too short
            }
        }
    }

    safe_config = restore_secret_placeholders(config, {})

    # Short values should not be masked (less than 8 chars)
    assert safe_config["server"]["api_keys"]["admin_key"] == "short"
    assert safe_config["llm"]["api_keys"]["openai"] == "tiny"

    # 8-char value at known secret path should be masked generically
    assert safe_config["server"]["api_keys"]["client_key"] == "••••••••"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
