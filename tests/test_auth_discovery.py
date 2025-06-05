#!/usr/bin/env python3
"""
Test script to check what authentication information is available from registry discovery
"""

import asyncio
import sys
from pathlib import Path

# Add runtime to path
runtime_path = Path(__file__).parent.parent / "runtime"
sys.path.insert(0, str(runtime_path))

from runtime.muxi.runtime.a2a.registry_client import A2ARegistryClient  # noqa: E402


async def test_discovery():
    """Test what auth information is available from registry"""
    print("🔍 Testing Registry Discovery for Auth Info")
    print("=" * 50)

    # Use default local registry (running on 9090)
    client = A2ARegistryClient(registries=["http://localhost:9090"])

    try:
        agents = await client.discover_agents()
        print("✅ Discovery successful")

        if isinstance(agents, dict):
            # Multiple registries
            for registry_url, agent_list in agents.items():
                print(f"\n=== Registry: {registry_url} ===")
                for agent in agent_list:
                    print(f"\nAgent: {agent.name}")
                    print(f"  URL: {agent.url}")

                    # Check for authentication info
                    if hasattr(agent, "authentication"):
                        print(f"  🔐 Auth: {agent.authentication}")
                    else:
                        print("  ❌ No auth info found")

                    # Check all available attributes
                    print(
                        "📋 Available attrs: "
                        f"{[attr for attr in dir(agent) if not attr.startswith('_')]}"
                    )

        else:
            # Single registry
            print("\n=== Single Registry Response ===")
            for agent in agents:
                print(f"\nAgent: {agent.name}")
                print(f"  URL: {agent.url}")

                if hasattr(agent, "authentication"):
                    print(f"  🔐 Auth: {agent.authentication}")
                else:
                    print("  ❌ No auth info found")

                print(
                    "  📋 Available attrs: "
                    f"{[attr for attr in dir(agent) if not attr.startswith('_')]}"
                )

    except Exception as e:
        print(f"❌ Discovery failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_discovery())
