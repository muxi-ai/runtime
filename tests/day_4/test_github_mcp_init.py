#!/usr/bin/env python3
"""Simple test to verify GitHub MCP initialization"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""

    print("\nGITHUB MCP INITIALIZATION TEST")
    print("=" * 60)

    try:
        # Use the actual test formation
        formation_path = Path("test-formations/formation-mcp")

        # Load formation
        formation = Formation()

        # Use async API directly
        print(f"Loading formation from: {formation_path}")
        await formation.load(str(formation_path))
        print("✓ Formation loaded")

        print("\nStarting overlord...")
        overlord = await formation.start_overlord()
        print("✓ Overlord started")

        # Give MCP servers time to fully initialize
        print("Waiting for MCP servers to initialize...")
        await asyncio.sleep(3)

        # Check MCP service
        if hasattr(overlord, 'mcp_service'):
            print("\n✓ MCP service found on overlord")
            mcp_service = overlord.mcp_service

            # Check tool registry
            if hasattr(mcp_service, 'tool_registry'):
                print("✓ Tool registry found")

                # Count tools per server
                total_tools = 0
                github_tools = 0
                
                for server_id, tools in mcp_service.tool_registry.items():
                    tool_count = len(tools) if isinstance(tools, dict) else 0
                    total_tools += tool_count

                    print(f"\nServer: {server_id}")
                    print(f"  Tools: {tool_count}")
                    
                    if server_id == 'github-mcp':
                        github_tools = tool_count

                    # Show first few tools
                    if tool_count > 0 and isinstance(tools, dict):
                        for i, (tool_name, tool_def) in enumerate(list(tools.items())[:5]):
                            desc = tool_def.get('description', 'No description')
                            if len(desc) > 60:
                                desc = desc[:57] + "..."
                            print(f"    {i+1}. {tool_name}: {desc}")

                        if tool_count > 5:
                            print(f"    ... and {tool_count - 5} more tools")

                print(f"\n✓ Total tools across all servers: {total_tools}")
                
                if github_tools > 0:
                    print(f"✅ GitHub MCP loaded successfully with {github_tools} tools!")
                else:
                    print("❌ GitHub MCP failed to load tools")

            else:
                print("❌ No tool_registry on MCP service")
        else:
            print("❌ No MCP service on overlord")

        print("\n🔚 Stopping overlord...")
        await formation.stop_overlord(10.0)
        print("✅ Test complete!")

        # Clean shutdown to avoid async generator errors
        formation.shutdown(0)

    except Exception as e:
        print(f"\n❌ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    print("Starting GitHub MCP initialization test...")

    # Run everything in a single event loop that persists until completion
    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test PASSED")
        else:
            print("\n❌ Test FAILED")

        # Force exit to avoid MCP SDK cleanup hang
        import os
        os._exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        import os
        os._exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        import os
        os._exit(1)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)