#!/usr/bin/env python3
"""Debug MCP configuration loading"""

import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


def debug_mcp_config():
    """Debug what's in the formation configuration."""
    
    print("\nDEBUG: MCP Configuration Loading")
    print("=" * 50)
    
    # Load formation
    formation_path = Path("test-formations/formation-mcp")
    formation = Formation()
    formation.load(str(formation_path))
    
    print("\n1. Checking formation._config:")
    if hasattr(formation, '_config'):
        config_keys = list(formation._config.keys())
        print(f"   Keys in _config: {config_keys}")
        
        # Check if 'mcp' key exists
        if 'mcp' in formation._config:
            print(f"   'mcp' found in _config")
            mcp_data = formation._config['mcp']
            print(f"   Type of mcp data: {type(mcp_data)}")
            if isinstance(mcp_data, dict):
                print(f"   Keys in mcp: {list(mcp_data.keys())}")
                if 'servers' in mcp_data:
                    servers = mcp_data['servers']
                    print(f"   Number of servers: {len(servers)}")
                    for i, server in enumerate(servers):
                        print(f"   Server {i}: {server.get('id', 'unknown')} - {server.get('description', 'no desc')}")
        else:
            print("   'mcp' NOT found in _config")
    else:
        print("   formation._config not found")
    
    print("\n2. Checking formation._mcp_config:")
    if hasattr(formation, '_mcp_config'):
        print(f"   _mcp_config exists")
        print(f"   Type: {type(formation._mcp_config)}")
        if isinstance(formation._mcp_config, dict):
            print(f"   Keys: {list(formation._mcp_config.keys())}")
            if 'servers' in formation._mcp_config:
                print(f"   Number of servers in _mcp_config: {len(formation._mcp_config['servers'])}")
            else:
                print("   'servers' NOT found in _mcp_config")
        else:
            print(f"   _mcp_config is not a dict: {formation._mcp_config}")
    else:
        print("   formation._mcp_config not found")
    
    print("\n3. Checking MCP directory:")
    mcp_dir = formation_path / "mcp"
    if mcp_dir.exists():
        print(f"   MCP directory exists: {mcp_dir}")
        yaml_files = list(mcp_dir.glob("*.yaml"))
        print(f"   YAML files found: {len(yaml_files)}")
        for yaml_file in yaml_files:
            print(f"     - {yaml_file.name}")
    else:
        print("   MCP directory NOT found")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    debug_mcp_config()