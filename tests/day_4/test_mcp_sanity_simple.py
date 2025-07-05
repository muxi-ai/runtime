#!/usr/bin/env python3
"""Simple MCP sanity test focused on connection."""

import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


def run_test():
    """Run the test in a thread to avoid event loop issues."""
    print("\nSIMPLE MCP SANITY CHECK")
    print("=" * 60)

    # Load formation
    formation_path = Path("test-formations/formation-mcp")
    formation = Formation()

    print(f"Loading formation from: {formation_path}")
    formation.load(str(formation_path))
    print("✓ Formation loaded")

    # Start overlord
    print("\nStarting overlord...")
    overlord = formation.start_overlord()
    print("✓ Overlord started")

    # Check MCP service
    if hasattr(overlord, 'mcp_service'):
        print("\n✓ MCP service found on overlord")
        mcp_service = overlord.mcp_service

        # Check tool registry
        if hasattr(mcp_service, 'tool_registry'):
            print("✓ Tool registry found")

            # Count tools per server
            total_tools = 0
            for server_id, tools in mcp_service.tool_registry.items():
                tool_count = len(tools) if isinstance(tools, dict) else 0
                total_tools += tool_count

                print(f"\nServer: {server_id}")
                print(f"  Tools: {tool_count}")

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

            # Expected tools for Linear
            if 'linear-mcp' in mcp_service.tool_registry:
                linear_tools = len(mcp_service.tool_registry['linear-mcp'])
                if linear_tools >= 20:
                    print(f"✅ Linear MCP loaded successfully with {linear_tools} tools!")
                else:
                    print(f"⚠️  Linear MCP has only {linear_tools} tools (expected ~22)")
            else:
                print("❌ Linear MCP not found in tool registry")

        else:
            print("❌ No tool_registry on MCP service")
    else:
        print("❌ No MCP service on overlord")

    # Check if Linear connection details are correct
    if hasattr(mcp_service, '_servers') and 'linear-mcp' in mcp_service._servers:
        server = mcp_service._servers['linear-mcp']
        if hasattr(server, 'handler') and hasattr(server.handler, 'transport'):
            transport = server.handler.transport
            print("\nLinear transport details:")
            print(f"  Type: {type(transport).__name__}")
            print(f"  Connected: {transport.connected if hasattr(transport, 'connected') else 'Unknown'}")
            print(f"  URL: {transport.url if hasattr(transport, 'url') else 'Unknown'}")

    # Stop overlord
    print("\nStopping overlord...")
    try:
        formation.stop_overlord(timeout=5.0)
        print("✓ Overlord stopped")
    except Exception as e:
        print(f"⚠️  Overlord stop warning: {e}")
        formation.kill_overlord()
        print("✓ Overlord killed")

    print("\n" + "=" * 60)
    print("Sanity check complete!")


def main():
    """Main entry point using thread executor."""
    print("Running simple MCP sanity check...")

    # Run in thread to avoid event loop conflicts
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)

        try:
            future.result(timeout=30)  # 30 second timeout
        except TimeoutError:
            print("\n❌ Test timed out after 30 seconds")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
