"""
Test secret deletion protection based on usage validation.
"""

import pytest
import tempfile
import os
from pathlib import Path
import yaml

from muxi.formation.formation import Formation
from muxi.services.secrets.secrets_manager import SecretsManager


@pytest.mark.asyncio
async def test_secret_in_use_detection():
    """Test that secrets in use are properly detected from formation config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a formation config that uses secrets
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for secret deletion protection",
            "overlord": {
                "model": {
                    "provider": "${{ secrets.MODEL_PROVIDER }}",
                    "model": "gpt-4",
                    "api_key": "${{ secrets.OPENAI_API_KEY }}"
                }
            },
            "agents": [
                {
                    "id": "agent1",
                    "name": "Test Agent",
                    "description": "Test agent for secret validation",
                    "model": {
                        "provider": "openai",
                        "model": "gpt-3.5-turbo",
                        "api_key": "${{ secrets.AGENT_API_KEY }}"
                    }
                }
            ],
            "mcp": {
                "servers": [
                    {
                        "id": "test-server",
                        "name": "Test Server",
                        "description": "Test MCP server",
                        "type": "command",
                        "command": "node",
                        "args": ["server.js"],
                        "env": {
                            "API_TOKEN": "${{ secrets.MCP_API_TOKEN }}"
                        }
                    }
                ]
            },
            "llm": {
                "api_keys": {
                    "openai": "${{ secrets.OPENAI_API_KEY }}"
                },
                "models": [
                    {
                        "name": "gpt-4",
                        "provider": "openai",
                        "capabilities": ["text"]
                    }
                ]
            }
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.yaml")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create secrets manager and store secrets
        secrets_manager = SecretsManager(tmpdir)
        await secrets_manager.initialize_encryption()
        await secrets_manager.store_secret("MODEL_PROVIDER", "openai")
        await secrets_manager.store_secret("OPENAI_API_KEY", "sk-test123")
        await secrets_manager.store_secret("AGENT_API_KEY", "sk-agent456")
        await secrets_manager.store_secret("MCP_API_TOKEN", "token789")
        await secrets_manager.store_secret("UNUSED_SECRET", "not-used")

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Test that secrets in use are detected
        assert formation.is_secret_in_use("MODEL_PROVIDER")
        assert formation.is_secret_in_use("OPENAI_API_KEY")
        assert formation.is_secret_in_use("AGENT_API_KEY")
        assert formation.is_secret_in_use("MCP_API_TOKEN")

        # Test that unused secret is not detected as in use
        assert not formation.is_secret_in_use("UNUSED_SECRET")

        # Test normalization works (different formats should still be detected)
        assert formation.is_secret_in_use("openai-api-key")  # lowercase with dashes
        assert formation.is_secret_in_use("OPENAI-API-KEY")  # uppercase with dashes
        assert formation.is_secret_in_use("openai_api_key")  # lowercase with underscores


@pytest.mark.asyncio
async def test_user_credentials_secret_tracking():
    """Test that user.credentials.X patterns are tracked as USER_CREDENTIALS_X."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a formation config that uses user credentials
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for user credentials tracking",
            "user": {
                "credentials": {
                    "github-token": "${{ user.credentials.github-token }}",
                    "slack_key": "${{ user.credentials.slack_key }}"
                }
            },
            "agents": [
                {
                    "id": "agent1",
                    "name": "Test Agent",
                    "description": "Test agent for user credentials",
                    "model": {
                        "provider": "openai",
                        "model": "gpt-3.5-turbo"
                    },
                    "tools": [
                        {
                            "name": "github",
                            "token": "${{ user.credentials.gh-pat }}"
                        }
                    ]
                }
            ],
            "llm": {
                "api_keys": {
                    "openai": "test-key"
                },
                "models": [
                    {
                        "name": "gpt-3.5-turbo",
                        "provider": "openai",
                        "capabilities": ["text"]
                    }
                ]
            }
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.yaml")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create secrets manager and store corresponding secrets
        secrets_manager = SecretsManager(tmpdir)
        await secrets_manager.initialize_encryption()
        await secrets_manager.store_secret("USER_CREDENTIALS_GITHUB_TOKEN", "ghp_123")
        await secrets_manager.store_secret("USER_CREDENTIALS_SLACK_KEY", "slack_456")
        await secrets_manager.store_secret("USER_CREDENTIALS_GH_PAT", "ghp_789")

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Test that user credentials are tracked with USER_CREDENTIALS_ prefix
        assert formation.is_secret_in_use("USER_CREDENTIALS_GITHUB_TOKEN")
        assert formation.is_secret_in_use("USER_CREDENTIALS_SLACK_KEY")
        assert formation.is_secret_in_use("USER_CREDENTIALS_GH_PAT")

        # Test normalization works for user credentials too
        assert formation.is_secret_in_use("user-credentials-github-token")
        assert formation.is_secret_in_use("USER_CREDENTIALS_SLACK_KEY")


@pytest.mark.asyncio
async def test_modular_formation_secret_tracking():
    """Test secret tracking in modular formation structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create modular formation structure
        formation_dir = Path(tmpdir)
        agents_dir = formation_dir / "agents"
        mcp_dir = formation_dir / "mcp"

        agents_dir.mkdir()
        mcp_dir.mkdir()

        # Main formation config
        main_config = {
            "id": "test-formation",
            "name": "Test Modular Formation",
            "schema": "1.0.0",
            "description": "Test modular formation for secret tracking",
            "overlord": {
                "model": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "${{ secrets.MAIN_API_KEY }}"
                }
            },
            "llm": {
                "api_keys": {
                    "openai": "${{ secrets.MAIN_API_KEY }}"
                },
                "models": [
                    {
                        "name": "gpt-4",
                        "provider": "openai",
                        "capabilities": ["text"]
                    }
                ]
            }
        }

        # Agent config with secrets
        agent_config = {
            "id": "agent1",
            "name": "Test Agent",
            "description": "Test agent in modular formation",
            "model": {
                "provider": "anthropic",
                "model": "claude-3",
                "api_key": "${{ secrets.AGENT_CLAUDE_KEY }}"
            }
        }

        # MCP server config with secrets
        mcp_config = {
            "id": "mcp1",
            "name": "Test MCP Server",
            "description": "Test MCP server in modular formation",
            "type": "command",
            "command": "node",
            "args": ["server.js"],
            "env": {
                "DATABASE_URL": "${{ secrets.DB_CONNECTION_STRING }}",
                "REDIS_URL": "${{ secrets.REDIS_URL }}"
            }
        }

        # Write configs
        with open(formation_dir / "formation.yaml", "w") as f:
            yaml.dump(main_config, f)
        with open(agents_dir / "agent1.yaml", "w") as f:
            yaml.dump(agent_config, f)
        with open(mcp_dir / "mcp1.yaml", "w") as f:
            yaml.dump(mcp_config, f)

        # Create secrets
        secrets_manager = SecretsManager(formation_dir)
        await secrets_manager.initialize_encryption()
        await secrets_manager.store_secret("MAIN_API_KEY", "sk-main")
        await secrets_manager.store_secret("AGENT_CLAUDE_KEY", "sk-claude")
        await secrets_manager.store_secret("DB_CONNECTION_STRING", "postgres://...")
        await secrets_manager.store_secret("REDIS_URL", "redis://...")
        await secrets_manager.store_secret("UNUSED_SECRET", "not-used")

        # Load modular formation
        formation = Formation()
        await formation.load(str(formation_dir))

        # Test that all secrets from all files are tracked
        assert formation.is_secret_in_use("MAIN_API_KEY")
        assert formation.is_secret_in_use("AGENT_CLAUDE_KEY")
        assert formation.is_secret_in_use("DB_CONNECTION_STRING")
        assert formation.is_secret_in_use("REDIS_URL")

        # Unused secret should not be tracked
        assert not formation.is_secret_in_use("UNUSED_SECRET")
