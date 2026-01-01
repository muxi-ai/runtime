#!/usr/bin/env python3
"""Detailed debug script with step-by-step logging."""

import asyncio
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

# Patch the initialization functions to add logging
import muxi.runtime.formation.initialization as init_module

# Store original functions
original_init_mcp = init_module.initialize_mcp_services
original_load_agents = init_module.load_agents_from_configuration

async def patched_init_mcp(formation):
    """Patched MCP initialization with logging."""
    print("\n🔍 DEBUG: Starting MCP initialization...")
    result = await original_init_mcp(formation)
    print("🔍 DEBUG: MCP initialization complete!")
    return result

def patched_load_agents(formation):
    """Patched agent loading with logging."""
    print("\n🔍 DEBUG: Starting agent loading...")
    result = original_load_agents(formation)
    print("🔍 DEBUG: Agent loading complete!")
    return result

# Apply patches
init_module.initialize_mcp_services = patched_init_mcp
init_module.load_agents_from_configuration = patched_load_agents

from muxi.runtime.formation import Formation

async def debug_load():
    """Load formation with detailed logging."""
    print("="*60)
    print("DETAILED DEBUG: Formation Loading")
    print("="*60)

    try:
        print("\n[1] Creating Formation instance...")
        formation = Formation()
        print("✅ Formation instance created\n")

        print("[2] Starting formation.load()...")
        formation_path = Path(__file__).parent / "formation-api"
        print(f"   Path: {formation_path}\n")

        print("[3] Loading with 45s timeout...\n")
        try:
            await asyncio.wait_for(
                formation.load(str(formation_path)),
                timeout=45.0
            )
            print("\n" + "="*60)
            print("✅ SUCCESS: Formation loaded!")
            print("="*60)
            return True

        except asyncio.TimeoutError:
            print("\n" + "="*60)
            print("❌ TIMEOUT after 45s")
            print("="*60)
            print("\nLast successful step before timeout:")
            print("Check the output above to see where it stopped")
            return False

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\nStarting detailed debug session...\n")
    success = asyncio.run(debug_load())
    sys.exit(0 if success else 1)
