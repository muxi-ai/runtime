#!/usr/bin/env python3
"""Test GitHub Copilot MCP server connection."""

import asyncio
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.muxi.runtime.services.mcp.transports.factory import MCPTransportFactory  # noqa: E402


async def test_github_copilot():
    """Test GitHub Copilot MCP connection."""
    print("=" * 80)
    print("TESTING GITHUB COPILOT MCP SERVER")
    print("=" * 80)

    # GitHub Copilot MCP endpoint
    github_url = "https://api.githubcopilot.com/mcp/"
    github_token = "<redacted>"

    auth = {
        "type": "bearer",
        "token": github_token
    }

    transport = None

    try:
        print("\n1. Creating transport with auto-fallback...")
        print(f"   URL: {github_url}")
        print("   Auth: Bearer token (PAT)")

        transport = await MCPTransportFactory.create_transport_with_fallback(
            url=github_url,
            auth=auth,
            request_timeout=60
        )

        print(f"\n✅ Transport created: {type(transport).__name__}")

        # Check if already connected
        if not transport.connected:
            print("\n2. Connecting to GitHub Copilot MCP...")
            await transport.connect()
        else:
            print("\n2. Already connected from factory test")

        print("\n✅ Successfully connected!")

        # List tools
        print("\n3. Listing available tools...")
        request = {
            "method": "tools/list",
            "params": {}
        }

        response = await transport.send_request(request, timeout=30)

        if response.get("status") == "success":
            tools = response.get("result", {}).get("tools", [])
            print(f"\n✅ Found {len(tools)} tools:")

            # Group tools by category
            issue_tools = []
            pr_tools = []
            repo_tools = []
            copilot_tools = []
            other_tools = []

            for tool in tools:
                name = tool.get("name", "").lower()
                if "issue" in name:
                    issue_tools.append(tool)
                elif "pull_request" in name or "_pr_" in name:
                    pr_tools.append(tool)
                elif "repo" in name:
                    repo_tools.append(tool)
                elif "copilot" in name:
                    copilot_tools.append(tool)
                else:
                    other_tools.append(tool)

            if issue_tools:
                print(f"\n   Issue Tools ({len(issue_tools)}):")
                for tool in issue_tools[:3]:
                    print(f"   - {tool.get('name')}")

            if pr_tools:
                print(f"\n   Pull Request Tools ({len(pr_tools)}):")
                for tool in pr_tools[:3]:
                    print(f"   - {tool.get('name')}")

            if repo_tools:
                print(f"\n   Repository Tools ({len(repo_tools)}):")
                for tool in repo_tools[:3]:
                    print(f"   - {tool.get('name')}")

            if copilot_tools:
                print(f"\n   Copilot Tools ({len(copilot_tools)}):")
                for tool in copilot_tools[:3]:
                    print(f"   - {tool.get('name')}")

            if other_tools:
                print(f"\n   Other Tools ({len(other_tools)}):")
                for tool in other_tools[:3]:
                    print(f"   - {tool.get('name')}")

        else:
            print(f"\n❌ Error listing tools: {response}")

        # Test connection stability
        print("\n4. Testing connection stability...")
        print("   Monitoring connection for 10 seconds...")

        start_time = time.time()
        check_count = 0

        while time.time() - start_time < 10:
            await asyncio.sleep(2)
            check_count += 1

            # Check if still connected
            if transport.is_connected:
                print(f"   ✅ Check {check_count}: Still connected")
            else:
                print(f"   ❌ Check {check_count}: Connection lost!")
                break

        # Get final stats
        stats = transport.get_connection_stats()
        print("\n5. Connection Statistics:")
        print(f"   - Transport Type: {stats.get('transport_type')}")
        print(f"   - Still Connected: {stats.get('connected')}")
        print(f"   - Total Duration: {time.time() - start_time:.1f} seconds")

        if transport.is_connected:
            print("\n✅ Connection remained stable!")
        else:
            print("\n❌ Connection was lost during testing")

        print("\n6. Disconnecting...")
        await transport.disconnect()

        print("\n" + "=" * 80)
        print("Test completed!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if transport and transport.connected:
            try:
                await transport.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    print("Testing GitHub Copilot MCP server...\n")
    asyncio.run(test_github_copilot())
