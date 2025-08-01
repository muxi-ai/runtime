"""
Test secret placeholder restoration functionality.

Tests ensure that secret values are properly replaced with their original
placeholder strings in API responses.
"""

import pytest
from copy import deepcopy

from muxi.formation.server.secrets import restore_secret_placeholders, mask_hardcoded_secrets
from muxi.formation.config.loader import ConfigLoader


class TestSecretPlaceholderRestoration:
    """Test suite for secret placeholder restoration."""
    
    @pytest.mark.asyncio
    async def test_process_secrets_returns_registry(self):
        """Test that process_secrets returns placeholder registry."""
        config = {
            "llm": {
                "api_keys": {
                    "openai": "${{ secrets.OPENAI_API_KEY }}",
                    "anthropic": "direct-key-value"
                }
            },
            "server": {
                "api_keys": {
                    "admin": "${{ secrets.ADMIN_KEY }}"
                }
            }
        }
        
        # Mock secrets manager
        class MockSecretsManager:
            async def get_secret(self, key):
                return f"actual-{key.lower()}"
        
        loader = ConfigLoader()
        processed, secrets_in_use, registry = await loader.process_secrets(
            config, MockSecretsManager()
        )
        
        # Check that secrets were replaced
        assert processed["llm"]["api_keys"]["openai"] == "actual-openai_api_key"
        assert processed["server"]["api_keys"]["admin"] == "actual-admin_key"
        
        # Check that registry was populated
        assert "llm.api_keys.openai" in registry
        assert registry["llm.api_keys.openai"] == "${{ secrets.OPENAI_API_KEY }}"
        assert "server.api_keys.admin" in registry
        assert registry["server.api_keys.admin"] == "${{ secrets.ADMIN_KEY }}"
        
        # Direct values should not be in registry
        assert "llm.api_keys.anthropic" not in registry
    
    def test_restore_simple_secrets(self):
        """Test restoration of simple secret placeholders."""
        config = {
            "llm": {
                "api_keys": {
                    "openai": "actual-openai-key",
                    "anthropic": "actual-anthropic-key"
                }
            }
        }
        
        registry = {
            "llm.api_keys.openai": "${{ secrets.OPENAI_API_KEY }}",
            "llm.api_keys.anthropic": "${{ secrets.ANTHROPIC_KEY }}"
        }
        
        restored = restore_secret_placeholders(config, registry)
        
        # Check restoration
        assert restored["llm"]["api_keys"]["openai"] == "${{ secrets.OPENAI_API_KEY }}"
        assert restored["llm"]["api_keys"]["anthropic"] == "${{ secrets.ANTHROPIC_KEY }}"
        
        # Original config should not be modified
        assert config["llm"]["api_keys"]["openai"] == "actual-openai-key"
    
    def test_restore_nested_secrets(self):
        """Test restoration of secrets in nested structures."""
        config = {
            "agents": [
                {
                    "id": "agent1",
                    "model": {
                        "api_key": "actual-key-1"
                    }
                },
                {
                    "id": "agent2", 
                    "model": {
                        "api_key": "actual-key-2"
                    }
                }
            ]
        }
        
        registry = {
            "agents[0].model.api_key": "${{ secrets.AGENT1_KEY }}",
            "agents[1].model.api_key": "${{ secrets.AGENT2_KEY }}"
        }
        
        restored = restore_secret_placeholders(config, registry)
        
        assert restored["agents"][0]["model"]["api_key"] == "${{ secrets.AGENT1_KEY }}"
        assert restored["agents"][1]["model"]["api_key"] == "${{ secrets.AGENT2_KEY }}"
    
    def test_restore_mcp_server_secrets(self):
        """Test restoration of MCP server secrets."""
        config = {
            "mcp": {
                "servers": [
                    {
                        "id": "server1",
                        "env": {
                            "API_KEY": "actual-mcp-key-1",
                            "NORMAL_VAR": "not-a-secret"
                        }
                    }
                ]
            }
        }
        
        registry = {
            "mcp.servers[0].env.API_KEY": "${{ secrets.MCP_API_KEY }}"
        }
        
        restored = restore_secret_placeholders(config, registry)
        
        assert restored["mcp"]["servers"][0]["env"]["API_KEY"] == "${{ secrets.MCP_API_KEY }}"
        assert restored["mcp"]["servers"][0]["env"]["NORMAL_VAR"] == "not-a-secret"
    
    def test_restore_with_missing_paths(self):
        """Test restoration handles missing paths gracefully."""
        config = {
            "llm": {
                "api_keys": {
                    "openai": "actual-key"
                }
            }
        }
        
        registry = {
            "llm.api_keys.openai": "${{ secrets.OPENAI_KEY }}",
            "llm.api_keys.missing": "${{ secrets.MISSING_KEY }}",  # Path doesn't exist
            "missing.path.entirely": "${{ secrets.ANOTHER_KEY }}"  # Path doesn't exist
        }
        
        restored = restore_secret_placeholders(config, registry)
        
        # Existing path should be restored
        assert restored["llm"]["api_keys"]["openai"] == "${{ secrets.OPENAI_KEY }}"
        
        # Missing paths should not cause errors
        assert "missing" not in restored["llm"]["api_keys"]
        assert "missing" not in restored
    
    def test_restore_user_credentials(self):
        """Test restoration of user credential placeholders."""
        config = {
            "mcp": {
                "servers": [
                    {
                        "id": "linear",
                        "env": {
                            "LINEAR_API_KEY": "actual-user-key"
                        }
                    }
                ]
            }
        }
        
        registry = {
            "mcp.servers[0].env.LINEAR_API_KEY": "${{ user.credentials.LINEAR_KEY }}"
        }
        
        restored = restore_secret_placeholders(config, registry)
        
        assert restored["mcp"]["servers"][0]["env"]["LINEAR_API_KEY"] == "${{ user.credentials.LINEAR_KEY }}"
    
    def test_empty_registry(self):
        """Test restoration with empty registry masks hardcoded secrets."""
        config = {
            "llm": {
                "api_keys": {
                    "openai": "actual-key"
                }
            },
            "non_secret": {
                "data": "some normal data"
            }
        }
        
        restored = restore_secret_placeholders(config, {})
        
        # Hardcoded secret should be masked (too short for pattern, so gets generic mask)
        assert restored["llm"]["api_keys"]["openai"] == "••••••••"
        # Non-secret data should remain unchanged
        assert restored["non_secret"]["data"] == "some normal data"
        assert restored is not config  # Should be a copy
    
    def test_complex_path_parsing(self):
        """Test parsing of complex paths with multiple array indices."""
        config = {
            "agents": [
                {
                    "tools": [
                        {"api_key": "key1"},
                        {"api_key": "key2"}
                    ]
                }
            ]
        }
        
        registry = {
            "agents[0].tools[1].api_key": "${{ secrets.TOOL_KEY }}"
        }
        
        restored = restore_secret_placeholders(config, registry)
        
        assert restored["agents"][0]["tools"][0]["api_key"] == "key1"
        assert restored["agents"][0]["tools"][1]["api_key"] == "${{ secrets.TOOL_KEY }}"


class TestHardcodedSecretMasking:
    """Test suite for hardcoded secret masking functionality."""
    
    def test_mask_hardcoded_api_keys(self):
        """Test masking of hardcoded API keys at known paths."""
        config = {
            "llm": {
                "api_keys": {
                    "openai": "sk-proj-1234567890abcdefghijklmnop",  # OpenAI format
                    "anthropic": "sk-ant-api03-1234567890abcdefghijklmnopqrstuvwxyz",  # Anthropic format
                    "google": "AIzaSyD-1234567890abcdefghijklmnopqrstuv",  # Google format
                    "placeholder": "${{ secrets.API_KEY }}"  # Should not be masked
                }
            },
            "server": {
                "api_keys": {
                    "admin_key": "sk_muxi_admin_1234567890",  # Muxi format
                    "client_key": "abcdef1234567890abcdef1234567890"  # Hex key
                }
            }
        }
        
        # Make a copy to verify original is modified
        config_copy = deepcopy(config)
        mask_hardcoded_secrets(config_copy)
        
        # Check OpenAI key masking (shows first 3 and last 3 for keys without underscore)
        assert config_copy["llm"]["api_keys"]["openai"] == "sk-••••••••nop"
        
        # Check Anthropic key masking (shows first 3 and last 3 for keys without underscore)
        assert config_copy["llm"]["api_keys"]["anthropic"] == "sk-••••••••xyz"
        
        # Check Google key masking
        assert config_copy["llm"]["api_keys"]["google"] == "AIz••••••••tuv"
        
        # Check placeholder is NOT masked
        assert config_copy["llm"]["api_keys"]["placeholder"] == "${{ secrets.API_KEY }}"
        
        # Check Muxi admin key masking (shows prefix up to first underscore)
        assert config_copy["server"]["api_keys"]["admin_key"] == "sk_••••••••7890"
        
        # Check hex key masking
        assert config_copy["server"]["api_keys"]["client_key"] == "abc••••••••890"
    
    def test_mask_agent_api_keys(self):
        """Test masking of API keys in agent configurations."""
        config = {
            "agents": [
                {
                    "id": "agent1",
                    "model": {
                        "api_key": "sk-1234567890abcdefghijklmnopqrstuvwxyz"
                    }
                },
                {
                    "id": "agent2",
                    "model": {
                        "api_key": "${{ secrets.AGENT_KEY }}"  # Placeholder
                    }
                },
                {
                    "id": "agent3",
                    "model": {
                        "api_key": "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"  # All caps key
                    }
                }
            ]
        }
        
        mask_hardcoded_secrets(config)
        
        # First agent key should be masked (shows first 3 and last 3)
        assert config["agents"][0]["model"]["api_key"] == "sk-••••••••xyz"
        
        # Second agent placeholder should NOT be masked
        assert config["agents"][1]["model"]["api_key"] == "${{ secrets.AGENT_KEY }}"
        
        # Third agent all-caps key should be masked
        assert config["agents"][2]["model"]["api_key"] == "ABC••••••••456"
    
    def test_mask_mcp_environment_secrets(self):
        """Test masking of secrets in MCP server environment variables."""
        config = {
            "mcp": {
                "servers": [
                    {
                        "id": "server1",
                        "env": {
                            "API_KEY": "sk_stripe_test_1234567890abcdef",
                            "API_TOKEN": "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
                            "SECRET_KEY": "super_secret_key_123456789",
                            "ACCESS_TOKEN": "${{ secrets.ACCESS_TOKEN }}",
                            "NORMAL_VAR": "not-a-secret",
                            "SHORT": "abc123"  # Too short to mask
                        }
                    }
                ]
            }
        }
        
        mask_hardcoded_secrets(config)
        
        # Check API_KEY is masked (shows prefix up to first underscore)
        assert config["mcp"]["servers"][0]["env"]["API_KEY"] == "sk_••••••••cdef"
        
        # Check API_TOKEN is masked
        assert config["mcp"]["servers"][0]["env"]["API_TOKEN"] == "ghp••••••••xyz"
        
        # Check SECRET_KEY is masked
        assert config["mcp"]["servers"][0]["env"]["SECRET_KEY"] == "sup••••••••789"
        
        # Check placeholder is NOT masked
        assert config["mcp"]["servers"][0]["env"]["ACCESS_TOKEN"] == "${{ secrets.ACCESS_TOKEN }}"
        
        # Check normal var is not masked
        assert config["mcp"]["servers"][0]["env"]["NORMAL_VAR"] == "not-a-secret"
        
        # Check short value is not masked
        assert config["mcp"]["servers"][0]["env"]["SHORT"] == "abc123"
    
    def test_mask_database_connection_strings(self):
        """Test masking of database connection strings."""
        config = {
            "database": {
                "connection_string": "postgresql://user:password123456@localhost:5432/db"
            },
            "memory": {
                "database": {
                    "url": "${{ secrets.DATABASE_URL }}"  # Placeholder
                }
            }
        }
        
        mask_hardcoded_secrets(config)
        
        # Connection string should be masked (contains password-like pattern)
        assert "••••••••" in config["database"]["connection_string"]
        
        # Placeholder should NOT be masked
        assert config["memory"]["database"]["url"] == "${{ secrets.DATABASE_URL }}"
    
    def test_already_masked_values_not_remasked(self):
        """Test that already masked values are not masked again."""
        config = {
            "llm": {
                "api_keys": {
                    "openai": "sk-••••••••xyz",  # Already masked
                    "anthropic": "***REDACTED***"  # Already masked differently
                }
            }
        }
        
        config_before = deepcopy(config)
        mask_hardcoded_secrets(config)
        
        # Values should remain unchanged
        assert config == config_before
    
    def test_scan_and_mask_unknown_locations(self):
        """Test general scanning for API key patterns in unknown locations."""
        config = {
            "custom": {
                "nested": {
                    "secret_key": "sk_test_1234567890abcdefghijklmnop",
                    "api_key": "1234567890abcdef1234567890abcdef",  # 32-char hex
                    "normal": "this is just normal text"
                }
            },
            "webhook": {
                "secret": "sk_webhook_1234567890abcdefghijklmnopqrstuvwxyz"  # Webhook secret with sk_ prefix
            }
        }
        
        mask_hardcoded_secrets(config)
        
        # Check that API key patterns are detected and masked
        assert config["custom"]["nested"]["secret_key"] == "sk_••••••••mnop"
        assert config["custom"]["nested"]["api_key"] == "123••••••••def"
        assert config["custom"]["nested"]["normal"] == "this is just normal text"
        assert config["webhook"]["secret"] == "sk_••••••••wxyz"
    
    def test_overlord_api_key_masking(self):
        """Test masking of overlord API key."""
        config = {
            "overlord": {
                "api_key": "olrd_1234567890abcdefghijklmnopqrstuvwxyz",
                "persona": "You are a helpful assistant."  # Should not be masked
            }
        }
        
        mask_hardcoded_secrets(config)
        
        # API key should be masked
        assert "••••••••" in config["overlord"]["api_key"]
        
        # Persona should not be masked
        assert config["overlord"]["persona"] == "You are a helpful assistant."
    
    def test_integration_with_placeholder_restoration(self):
        """Test that hardcoded secret masking works with placeholder restoration."""
        config = {
            "llm": {
                "api_keys": {
                    "openai": "sk-actual-openai-key-1234567890",  # Will be restored to placeholder
                    "anthropic": "sk-ant-hardcoded-key-1234567890",  # No placeholder, should be masked
                    "google": "${{ secrets.GOOGLE_KEY }}"  # Already a placeholder
                }
            }
        }
        
        registry = {
            "llm.api_keys.openai": "${{ secrets.OPENAI_API_KEY }}"
        }
        
        # Restore placeholders (which also masks hardcoded secrets)
        restored = restore_secret_placeholders(config, registry)
        
        # OpenAI key should be restored to placeholder
        assert restored["llm"]["api_keys"]["openai"] == "${{ secrets.OPENAI_API_KEY }}"
        
        # Anthropic key should be masked (no placeholder for it, shows first 3 and last 3)
        assert restored["llm"]["api_keys"]["anthropic"] == "sk-••••••••890"
        
        # Google key should remain as placeholder
        assert restored["llm"]["api_keys"]["google"] == "${{ secrets.GOOGLE_KEY }}"
    
    def test_empty_config_handling(self):
        """Test that empty or minimal configs don't cause errors."""
        # Empty config
        config1 = {}
        mask_hardcoded_secrets(config1)
        assert config1 == {}
        
        # Config without secret paths
        config2 = {
            "name": "test",
            "version": "1.0",
            "features": ["a", "b", "c"]
        }
        config2_copy = deepcopy(config2)
        mask_hardcoded_secrets(config2_copy)
        assert config2_copy == config2
    
    def test_wildcard_path_patterns(self):
        """Test that wildcard patterns in known paths work correctly."""
        config = {
            "agents": [
                {"id": "a1", "model": {"api_key": "sk-agent1-key-12345678"}},
                {"id": "a2", "model": {"api_key": "sk-agent2-key-87654321"}},
                {"id": "a3", "model": {"other": "value"}}  # No api_key
            ],
            "mcp": {
                "servers": [
                    {
                        "id": "s1",
                        "env": {
                            "API_KEY": "server1-api-key-secret123",
                            "AUTH_TOKEN": "auth-token-secret456"
                        }
                    },
                    {
                        "id": "s2",
                        "env": {
                            "NORMAL": "not-secret"
                        }
                    }
                ]
            }
        }
        
        mask_hardcoded_secrets(config)
        
        # Check agents[*].model.api_key pattern (shows first 3 and last 3)
        assert config["agents"][0]["model"]["api_key"] == "sk-••••••••678"
        assert config["agents"][1]["model"]["api_key"] == "sk-••••••••321"
        
        # Check MCP environment patterns
        assert "••••••••" in config["mcp"]["servers"][0]["env"]["API_KEY"]
        assert "••••••••" in config["mcp"]["servers"][0]["env"]["AUTH_TOKEN"]
        assert config["mcp"]["servers"][1]["env"]["NORMAL"] == "not-secret"