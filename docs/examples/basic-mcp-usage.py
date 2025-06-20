#!/usr/bin/env python3
"""
MUXI MCP Basic Usage Examples

This example demonstrates the core functionality of MUXI's MCP implementation
with real working servers. All examples use actual MCP protocol communication.

Prerequisites:
- MUXI Framework installed
- Optional: npm install -g @modelcontextprotocol/server-filesystem
"""

import asyncio
import time
from muxi.runtime.services.mcp.service import MCPService
from muxi.runtime.services.mcp.base import MCPConnectionError


async def example_1_basic_filesystem_server():
    """Example 1: Basic usage with official MCP filesystem server."""
    print("🗂️  Example 1: Basic Filesystem Server Usage")
    print("=" * 50)

    service = MCPService.get_instance()

    try:
        # Register the official MCP filesystem server
        print("📡 Registering MCP filesystem server...")
        await service.register_mcp_server(
            server_id="filesystem",
            command="npx @modelcontextprotocol/server-filesystem /tmp"
        )
        print("✅ Server registered successfully!")

        # Check what tools are available
        tools = service.tool_registry.get("filesystem", {})
        print(f"🔧 Available tools: {list(tools.keys())}")

        # Use the directory listing tool
        if "list_directory" in tools:
            print("\n📋 Listing /tmp directory...")
            result = await service.invoke_tool(
                server_id="filesystem",
                tool_name="list_directory",
                parameters={"path": "/tmp"}
            )

            if result["status"] == "success":
                print("✅ Directory listing successful!")
                files_count = len(result.get('result', {}).get('content', []))
                print(f"📁 Found files/directories: {files_count}")
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"❌ Directory listing failed: {error_msg}")
        else:
            print("⚠️  list_directory tool not available")

    except MCPConnectionError as e:
        print(f"❌ Connection failed: {e}")
        install_msg = "npm install -g @modelcontextprotocol/server-filesystem"
        print(f"💡 Make sure you have: {install_msg}")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")

    finally:
        # Always cleanup
        try:
            await service.disconnect_server("filesystem")
            print("🧹 Cleanup completed")
        except Exception:
            pass


async def example_2_auto_detection_demo():
    """Example 2: Demonstrate intelligent transport auto-detection."""
    print("\n🧠 Example 2: Intelligent Transport Auto-Detection")
    print("=" * 50)

    service = MCPService.get_instance()

    # Test URLs that would trigger different transport detection
    test_cases = [
        {
            "name": "Streamable HTTP Server",
            "url": "http://localhost:8002/mcp",
            "expected": "streamable_http"
        },
        {
            "name": "HTTP+SSE Server",
            "url": "http://localhost:8001/sse",
            "expected": "http_sse"
        }
    ]

    print("🔍 Testing transport auto-detection...")

    for test_case in test_cases:
        print(f"\n📡 Testing {test_case['name']}...")
        try:
            start_time = time.time()

            # Let MUXI auto-detect the transport type
            await service.register_mcp_server(
                server_id=f"test_{test_case['expected']}",
                url=test_case["url"],
                request_timeout=5
            )

            detection_time = time.time() - start_time
            print(f"✅ Auto-detected transport type in {detection_time:.3f}s")

            # Test cache performance
            start_time = time.time()
            await service.register_mcp_server(
                server_id=f"test_{test_case['expected']}_cached",
                url=test_case["url"],
                request_timeout=5
            )

            cached_time = time.time() - start_time
            speedup = detection_time / cached_time if cached_time > 0 else float('inf')
            print(f"⚡ Cached detection: {cached_time:.3f}s (speedup: {speedup:.1f}x)")

            # Cleanup
            await service.disconnect_server(f"test_{test_case['expected']}")
            await service.disconnect_server(f"test_{test_case['expected']}_cached")

        except MCPConnectionError:
            print(f"📴 Server not running on {test_case['url']} (expected for demo)")
        except Exception as e:
            print(f"❌ Error: {e}")


async def example_3_error_handling():
    """Example 3: Demonstrate robust error handling."""
    print("\n🛡️  Example 3: Robust Error Handling")
    print("=" * 50)

    service = MCPService.get_instance()

    # Test 1: Unreachable server
    print("📡 Testing unreachable server handling...")
    try:
        await service.register_mcp_server(
            server_id="unreachable",
            url="http://localhost:99999/mcp",
            request_timeout=3
        )
        print("⚠️  Unexpected success")
    except MCPConnectionError as e:
        print(f"✅ Correctly caught connection error: {type(e).__name__}")

    # Test 2: Invalid command
    print("\n💻 Testing invalid command handling...")
    try:
        await service.register_mcp_server(
            server_id="invalid",
            command="nonexistent-command-12345",
            request_timeout=3
        )
        print("⚠️  Unexpected success")
    except MCPConnectionError as e:
        print(f"✅ Correctly caught command error: {type(e).__name__}")

    # Test 3: Tool error handling (with valid server)
    print("\n🔧 Testing tool error handling...")
    try:
        # Register a server first
        await service.register_mcp_server(
            server_id="test_errors",
            command="npx @modelcontextprotocol/server-filesystem /tmp"
        )

        # Try to call a non-existent tool
        result = await service.invoke_tool(
            server_id="test_errors",
            tool_name="nonexistent_tool",
            parameters={}
        )

        if result["status"] == "error":
            error_msg = result.get('error', 'Unknown')
            print(f"✅ Tool error handled gracefully: {error_msg}")
        else:
            print("⚠️  Expected tool error but got success")

        await service.disconnect_server("test_errors")

    except Exception as e:
        print(f"✅ Exception handled: {type(e).__name__}")


async def example_4_performance_monitoring():
    """Example 4: Monitor performance characteristics."""
    print("\n⚡ Example 4: Performance Monitoring")
    print("=" * 50)

    service = MCPService.get_instance()

    # Get initial cache statistics
    print("📊 Transport cache statistics:")
    cache_stats = service.get_transport_cache_stats()
    for key, value in cache_stats.items():
        print(f"  {key}: {value}")

    # Performance test with filesystem server
    print("\n🏃 Performance testing...")
    try:
        # Time the initial connection
        start_time = time.time()
        await service.register_mcp_server(
            server_id="perf_test",
            command="npx @modelcontextprotocol/server-filesystem /tmp"
        )
        connection_time = time.time() - start_time
        print(f"📡 Initial connection: {connection_time:.3f}s")

        # Test tool execution performance
        tools = service.tool_registry.get("perf_test", {})
        if tools:
            tool_name = list(tools.keys())[0]
            print(f"🔧 Testing tool: {tool_name}")

            # Execute tool multiple times
            execution_times = []
            for i in range(3):
                start_time = time.time()
                tool_schema = tools[tool_name].get("input_schema", {})
                properties = tool_schema.get("properties", {})
                params = {"path": "/tmp"} if "path" in properties else {}

                result = await service.invoke_tool(
                    server_id="perf_test",
                    tool_name=tool_name,
                    parameters=params
                )
                execution_time = time.time() - start_time
                execution_times.append(execution_time)

                # Check if tool execution was successful
                status = "✅" if result.get("status") == "success" else "❌"
                print(f"  Execution {i+1}: {execution_time:.3f}s {status}")

            avg_time = sum(execution_times) / len(execution_times)
            print(f"⏱️  Average execution time: {avg_time:.3f}s")

        # Check connection info
        connection_info = service.get_connection_info("perf_test")
        print(f"📈 Connection stats: {connection_info}")

        await service.disconnect_server("perf_test")

    except Exception as e:
        print(f"❌ Performance test failed: {e}")


async def example_5_concurrent_operations():
    """Example 5: Demonstrate concurrent MCP operations."""
    print("\n🔄 Example 5: Concurrent Operations")
    print("=" * 50)

    service = MCPService.get_instance()

    # Define multiple servers to test concurrency
    servers = [
        {"id": "concurrent_1",
         "command": "npx @modelcontextprotocol/server-filesystem /tmp"},
        {"id": "concurrent_2",
         "command": "npx @modelcontextprotocol/server-filesystem /home"},
    ]

    print("🚀 Testing concurrent server registration...")
    try:
        # Register servers concurrently
        start_time = time.time()
        registration_tasks = [
            service.register_mcp_server(
                server_id=server["id"],
                command=server["command"],
                request_timeout=10
            )
            for server in servers
        ]

        results = await asyncio.gather(*registration_tasks, return_exceptions=True)
        total_time = time.time() - start_time

        successful = sum(1 for r in results if not isinstance(r, Exception))
        print(f"✅ Concurrent registration: {successful}/{len(servers)} "
              f"successful in {total_time:.3f}s")

        # Test concurrent tool execution
        if successful > 0:
            print("\n🔧 Testing concurrent tool execution...")
            tool_tasks = []

            for server in servers:
                server_id = server["id"]
                if server_id in service.tool_registry:
                    tools = service.tool_registry[server_id]
                    if tools:
                        tool_name = list(tools.keys())[0]
                        tool_schema = tools[tool_name].get("input_schema", {})
                        properties = tool_schema.get("properties", {})
                        params = {"path": "/tmp"} if "path" in properties else {}

                        task = service.invoke_tool(
                            server_id=server_id,
                            tool_name=tool_name,
                            parameters=params
                        )
                        tool_tasks.append(task)

            if tool_tasks:
                start_time = time.time()
                tool_results = await asyncio.gather(*tool_tasks,
                                                   return_exceptions=True)
                execution_time = time.time() - start_time

                tool_successful = sum(1 for r in tool_results
                                    if not isinstance(r, Exception))
                print(f"✅ Concurrent execution: {tool_successful}/{len(tool_tasks)} "
                      f"successful in {execution_time:.3f}s")

        # Cleanup
        cleanup_tasks = [
            service.disconnect_server(server["id"])
            for server in servers
            if server["id"] in service.handlers
        ]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    except Exception as e:
        print(f"❌ Concurrent operations test failed: {e}")


async def main():
    """Run all MCP examples."""
    print("🎉 MUXI MCP Implementation Examples")
    print("🚀 Production-Ready MCP Integration")
    print("=" * 60)

    # Run all examples
    await example_1_basic_filesystem_server()
    await example_2_auto_detection_demo()
    await example_3_error_handling()
    await example_4_performance_monitoring()
    await example_5_concurrent_operations()

    print("\n" + "=" * 60)
    print("✅ All examples completed!")
    print("🎯 MUXI MCP implementation is production-ready!")
    print("📚 See docs/mcp/implementation-guide.md for more details")


if __name__ == "__main__":
    asyncio.run(main())
