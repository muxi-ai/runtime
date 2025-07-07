#!/usr/bin/env python3
"""Minimal test to verify MCP server discovery works"""

import os
import sys
from pathlib import Path
import tempfile
import yaml

sys.path.insert(0, ".")

# Temporarily set a dummy API key for testing
os.environ["OPENAI_API_KEY"] = "test-key-for-mcp-discovery"

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


def test_mcp_discovery():
    """Test that MCP servers are discovered from mcp/ directory."""

    print("\nTEST: MCP Server Discovery")
    print("=" * 50)

    # Create a temporary formation directory
    temp_dir = Path(tempfile.mkdtemp(prefix="test_mcp_"))

    try:
        # Create minimal formation.yaml
        formation_config = {
            "schema": "1.0.0",
            "id": "test_mcp_discovery",
            "description": "Test MCP discovery",
            "llm": {
                "api_keys": {
                    "openai": os.environ["OPENAI_API_KEY"]  # Use env var instead of secret
                },
                "models": [
                    {"text": "openai/gpt-4o-mini"}
                ]
            }
        }

        with open(temp_dir / "formation.yaml", "w") as f:
            yaml.dump(formation_config, f)

        # Create agents directory with a simple agent
        agents_dir = temp_dir / "agents"
        agents_dir.mkdir()

        agent_config = {
            "schema": "1.0.0",
            "id": "test_agent",
            "name": "Test Agent",
            "description": "Test agent",
            "system_message": "You are a test agent.",
            "role": "general"
        }

        with open(agents_dir / "test_agent.yaml", "w") as f:
            yaml.dump(agent_config, f)

        # Create MCP directory with test servers
        mcp_dir = temp_dir / "mcp"
        mcp_dir.mkdir()

        # Create filesystem MCP server
        filesystem_mcp = {
            "schema": "1.0.0",
            "id": "filesystem-test",
            "description": "Test filesystem MCP",
            "active": True,
            "type": "command",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "timeout_seconds": 60
        }

        with open(mcp_dir / "filesystem.yaml", "w") as f:
            yaml.dump(filesystem_mcp, f)

        # Create system MCP server
        system_mcp = {
            "schema": "1.0.0",
            "id": "system-test",
            "description": "Test system MCP",
            "active": True,
            "type": "command",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-system"],
            "timeout_seconds": 60
        }

        with open(mcp_dir / "system.yaml", "w") as f:
            yaml.dump(system_mcp, f)

        # Create an inactive MCP server (should be skipped)
        inactive_mcp = {
            "schema": "1.0.0",
            "id": "inactive-test",
            "description": "Inactive MCP server",
            "active": False,
            "type": "command",
            "command": "echo",
            "args": ["inactive"]
        }

        with open(mcp_dir / "inactive.yaml", "w") as f:
            yaml.dump(inactive_mcp, f)

        print(f"Created test formation at: {temp_dir}")
        print("  - formation.yaml")
        print("  - agents/test_agent.yaml")
        print("  - mcp/filesystem.yaml")
        print("  - mcp/system.yaml")
        print("  - mcp/inactive.yaml")

        # Load formation
        formation = Formation()
        formation.load(str(temp_dir))

        print("\n✓ Formation loaded successfully")

        # Check MCP configuration
        if hasattr(formation, '_mcp_config'):
            print("\nMCP Configuration:")
            print(f"  Type: {type(formation._mcp_config)}")
            print(f"  Keys: {list(formation._mcp_config.keys())}")

            if 'servers' in formation._mcp_config:
                servers = formation._mcp_config['servers']
                print(f"\nMCP Servers discovered: {len(servers)}")
                for i, server in enumerate(servers):
                    print(f"\n  Server {i + 1}:")
                    print(f"    ID: {server.get('id')}")
                    print(f"    Description: {server.get('description', 'No description')}")
                    print(f"    Type: {server.get('type', 'unknown')}")
                    print(f"    Active: {server.get('active', True)}")
                    if server.get('type') == 'command':
                        print(f"    Command: {server.get('command')}")
                        print(f"    Args: {server.get('args', [])}")

                # Verify only active servers were loaded
                active_count = sum(1 for s in servers if s.get('active', True))
                print(f"\nActive servers: {active_count}")
                print("Expected active servers: 2")

                if active_count == 2:
                    print("✅ Correct number of active servers loaded")
                else:
                    print("❌ Incorrect number of active servers")

            else:
                print("  ❌ No 'servers' key in MCP config")
                return False
        else:
            print("❌ No _mcp_config attribute")
            return False

        # Check if MCP servers are stored for overlord
        if hasattr(formation, '_mcp_servers'):
            print(f"\n✓ MCP servers stored for overlord: {len(formation._mcp_servers)} servers")
        else:
            print("\n❌ No _mcp_servers attribute")
            return False

        print("\n✅ MCP discovery test passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print("\nCleaned up temporary directory")


if __name__ == "__main__":
    success = test_mcp_discovery()
    # Clean up env var
    if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] == "test-key-for-mcp-discovery":
        del os.environ["OPENAI_API_KEY"]
    sys.exit(0 if success else 1)
