#!/usr/bin/env python3
"""Simple test to verify MCP servers are loaded (without user credentials)"""

import sys
from pathlib import Path
import shutil
import tempfile

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


def test_mcp_loading():
    """Test that MCP servers are loaded from formation."""

    print("\nTEST: MCP Server Loading")
    print("=" * 50)

    # Create a temporary formation directory
    temp_dir = Path(tempfile.mkdtemp(prefix="test_mcp_"))

    try:
        # Copy the formation but remove the github server to avoid user credentials
        src_formation = Path("test-formations/formation-mcp")

        # Copy formation.yaml
        shutil.copy(src_formation / "formation.yaml", temp_dir / "formation.yaml")

        # Copy agents directory
        shutil.copytree(src_formation / "agents", temp_dir / "agents")

        # Copy MCP servers except github
        mcp_dir = temp_dir / "mcp"
        mcp_dir.mkdir()

        for mcp_file in ["filesystem.yaml", "system.yaml", "linear.yaml"]:
            shutil.copy(src_formation / "mcp" / mcp_file, mcp_dir / mcp_file)

        # Copy secrets if exists
        if (src_formation / "secrets.enc").exists():
            shutil.copy(src_formation / "secrets.enc", temp_dir / "secrets.enc")

        # Load formation
        formation = Formation()
        formation.load(str(temp_dir))

        print("✓ Formation loaded successfully")

        # Check MCP configuration
        if hasattr(formation, '_mcp_config'):
            print("\nMCP Configuration:")
            print(f"  Type: {type(formation._mcp_config)}")
            print(f"  Keys: {list(formation._mcp_config.keys())}")

            if 'servers' in formation._mcp_config:
                servers = formation._mcp_config['servers']
                print(f"\nMCP Servers found: {len(servers)}")
                for server in servers:
                    print(f"  - {server.get('id')}: {server.get('description', 'No description')}")
                    print(f"    Type: {server.get('type', 'command')}")
                    print(f"    Active: {server.get('active', True)}")
            else:
                print("  ❌ No 'servers' key in MCP config")
        else:
            print("❌ No _mcp_config attribute")

        # Check if MCP servers are passed to configured services
        if hasattr(formation, '_mcp_servers'):
            print(f"\nMCP servers stored for overlord: {len(formation._mcp_servers)}")
        else:
            print("\n❌ No _mcp_servers attribute")

        print("\n✅ Test completed successfully!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print(f"\nCleaned up temporary directory: {temp_dir}")


if __name__ == "__main__":
    success = test_mcp_loading()
    sys.exit(0 if success else 1)
