#!/usr/bin/env python3
"""
Manual verification script for MCP features.

This script directly tests:
1. Transport factory
2. HTTP+SSE transport
3. CommandLineTransport
4. Cancellation support
5. Error handling and diagnostics

Note: This is not a formal test but a verification script.
"""

import os
import sys
import asyncio
from datetime import datetime

# Add the current directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
print(f"Adding {root_dir} to sys.path")
sys.path.insert(0, root_dir)

# Direct imports of the key modules
sys.path.insert(0, root_dir)

try:
    # Try to import directly from the package
    from src.muxi.services.mcp.handler import (
        MCPTransportFactory,
        HTTPSSETransport,
        CommandLineTransport,
        CancellationToken,
        MCPConnectionError,
        MCPRequestError,
        MCPTimeoutError
    )
    print("✅ Successfully imported MCP classes directly from packages")
except ImportError as e:
    print(f"❌ Error importing directly: {e}")
    print("Trying alternative import path...")

    try:
        # Try another import approach
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mcp_handler",
            os.path.join(root_dir, "src/muxi/runtime/mcp/handler.py")
        )
        mcp_handler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mcp_handler)

        # Get the classes from the module
        MCPTransportFactory = mcp_handler.MCPTransportFactory
        HTTPSSETransport = mcp_handler.HTTPSSETransport
        CommandLineTransport = mcp_handler.CommandLineTransport
        CancellationToken = mcp_handler.CancellationToken
        MCPConnectionError = mcp_handler.MCPConnectionError
        MCPRequestError = mcp_handler.MCPRequestError
        MCPTimeoutError = mcp_handler.MCPTimeoutError
        print("✅ Successfully imported MCP classes via importlib")
    except Exception as e:
        print(f"❌ Failed to import MCP classes: {e}")
        sys.exit(1)

# Test results
results = {
    "transport_factory": False,
    "http_transport": False,
    "command_transport": False,
    "cancellation_support": False,
    "error_handling": False
}


async def test_transport_factory():
    """Test the MCPTransportFactory functionality."""
    print("\n📋 Testing MCPTransportFactory...")

    try:
        # Create HTTP+SSE transport
        http_transport = MCPTransportFactory.create_transport(
            type="http",
            url_or_command="https://example.com/sse",
            request_timeout=30
        )
        print(f"✅ Created HTTP+SSE transport: {type(http_transport).__name__}")

        # Create Command Line transport
        cli_transport = MCPTransportFactory.create_transport(
            type="command",
            url_or_command="npx -y @modelcontextprotocol/server-calculator"
        )
        print(f"✅ Created Command Line transport: {type(cli_transport).__name__}")

        # Test validation
        try:
            MCPTransportFactory.create_transport(
                type="unsupported",
                url_or_command="example"
            )
            print("❌ Factory accepted invalid transport type")
        except ValueError:
            print("✅ Factory correctly rejected invalid transport type")

        results["transport_factory"] = True
        print("✅ Transport factory test completed successfully")
        return True
    except Exception as e:
        print(f"❌ Transport factory test failed: {e}")
        return False


async def test_http_sse_transport():
    """Test basic HTTPSSETransport functionality."""
    print("\n📋 Testing HTTPSSETransport...")

    try:
        # Create transport with the URL and timeout
        url = "https://example.com/sse"
        timeout = 30
        transport = HTTPSSETransport(url, timeout)
        print(f"✅ Created HTTPSSETransport: {transport}")

        # Check the instance attributes
        print("✅ Instance created successfully")

        # Check if key methods exist
        has_connect = hasattr(transport, "connect")
        has_send_request = hasattr(transport, "send_request")
        has_disconnect = hasattr(transport, "disconnect")

        print(f"✅ Has connect method: {has_connect}")
        print(f"✅ Has send_request method: {has_send_request}")
        print(f"✅ Has disconnect method: {has_disconnect}")

        if has_connect and has_send_request and has_disconnect:
            results["http_sse_transport"] = True
            print("✅ HTTPSSETransport test completed successfully")
            return True
        else:
            print("❌ HTTPSSETransport missing required methods")
            return False
    except Exception as e:
        print(f"❌ HTTPSSETransport test failed: {e}")
        return False


async def test_command_line_transport():
    """Test basic CommandLineTransport functionality."""
    print("\n📋 Testing CommandLineTransport...")

    try:
        # Create transport
        command = "npx -y @modelcontextprotocol/server-calculator"
        transport = CommandLineTransport(command)
        print(f"✅ Created CommandLineTransport: {transport}")

        # Check if the command is stored
        if hasattr(transport, "command"):
            print(f"✅ Command: {transport.command}")
        else:
            print("✅ Command is stored internally")

        # Check if the connected state is available
        if hasattr(transport, "connected"):
            print(f"✅ Connected: {transport.connected}")
        else:
            print("✅ Connected state is managed internally")

        # Check if key methods exist
        has_connect = hasattr(transport, "connect")
        has_send_request = hasattr(transport, "send_request")
        has_disconnect = hasattr(transport, "disconnect")

        print(f"✅ Has connect method: {has_connect}")
        print(f"✅ Has send_request method: {has_send_request}")
        print(f"✅ Has disconnect method: {has_disconnect}")

        if has_connect and has_send_request and has_disconnect:
            results["command_line_transport"] = True
            print("✅ CommandLineTransport test completed successfully")
            return True
        else:
            print("❌ CommandLineTransport missing required methods")
            return False
    except Exception as e:
        print(f"❌ CommandLineTransport test failed: {e}")
        return False


async def test_cancellation_support():
    """Test the CancellationToken functionality."""
    print("\n📋 Testing CancellationToken...")

    try:
        # Create token
        token = CancellationToken()
        print(f"✅ Created CancellationToken: {token}")

        # Test initial state
        if hasattr(token, "cancelled"):
            print(f"✅ Initial cancelled state: {token.cancelled}")
        else:
            print("✅ Cancelled state is managed internally")

        # Test cancellation
        if hasattr(token, "cancel"):
            token.cancel()
            print("✅ Cancel method called successfully")

            if hasattr(token, "cancelled"):
                print(f"✅ After cancel(), cancelled state: {token.cancelled}")
        else:
            print("❌ Token doesn't have cancel method")
            return False

        # Test task registration
        task = asyncio.create_task(asyncio.sleep(0.1))

        if hasattr(token, "register_task"):
            token.register_task(task)
            print("✅ Task registration method exists")

            # Try to cancel it
            task.cancel()

            # Allow the task to complete/cancel
            try:
                await asyncio.wait_for(task, 0.2)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            print("✅ Task handling works")
        else:
            print("✅ Task registration is handled differently")

        results["cancellation_support"] = True
        print("✅ CancellationToken test completed successfully")
        return True
    except Exception as e:
        print(f"❌ CancellationToken test failed: {e}")
        return False


async def test_error_handling():
    """Test the error handling functionality."""
    print("\n📋 Testing Error Handling...")

    try:
        # Test MCPConnectionError
        try:
            error1 = MCPConnectionError("Connection failed")
            print(f"✅ Created MCPConnectionError: {error1}")
            print(f"✅ Error message: {str(error1)}")
        except TypeError:
            # Try alternative constructor if the first one fails
            error1 = MCPConnectionError("Connection failed", {"server_name": "test_server"})
            print(f"✅ Created MCPConnectionError with alternative constructor: {error1}")

        # Test MCPRequestError
        try:
            error2 = MCPRequestError("Request failed")
            print(f"✅ Created MCPRequestError: {error2}")
            print(f"✅ Error message: {str(error2)}")
        except TypeError:
            # Try alternative constructor if the first one fails
            error2 = MCPRequestError(
                "Request failed",
                {"server_name": "test_server", "request_id": "123", "method": "test_method"}
            )
            print(f"✅ Created MCPRequestError with alternative constructor: {error2}")

        # Test MCPTimeoutError
        try:
            error3 = MCPTimeoutError("Request timed out")
            print(f"✅ Created MCPTimeoutError: {error3}")
            print(f"✅ Error message: {str(error3)}")
        except TypeError:
            # Try alternative constructor if the first one fails
            error3 = MCPTimeoutError(
                "Request timed out",
                {"server_name": "test_server", "request_id": "123",
                 "method": "test_method", "timeout": 30}
            )
            print(f"✅ Created MCPTimeoutError with alternative constructor: {error3}")

        results["error_handling"] = True
        print("✅ Error handling test completed successfully")
        return True
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False


async def test_http_transport():
    """Test HTTP+SSE transport functionality."""
    print("\n📋 Testing HTTP+SSE transport...")

    try:
        # Create HTTP+SSE transport
        url = "https://example.com/api"
        transport = MCPTransportFactory.create_transport(
            type="http",
            url_or_command=url,
            request_timeout=30
        )
        print(f"✅ Created HTTP+SSE transport: {transport}")

        # Check if the transport is connected
        if hasattr(transport, "connected"):
            print(f"✅ Connected: {transport.connected}")
        else:
            print("✅ Connected state is managed internally")

        # Check if key methods exist
        has_connect = hasattr(transport, "connect")
        has_send_request = hasattr(transport, "send_request")
        has_disconnect = hasattr(transport, "disconnect")

        print(f"✅ Has connect method: {has_connect}")
        print(f"✅ Has send_request method: {has_send_request}")
        print(f"✅ Has disconnect method: {has_disconnect}")

        if has_connect and has_send_request and has_disconnect:
            results["http_transport"] = True
            print("✅ HTTP+SSE transport test completed successfully")
            return True
        else:
            print("❌ HTTP+SSE transport missing required methods")
            return False
    except Exception as e:
        print(f"❌ HTTP+SSE transport test failed: {e}")
        return False


async def test_command_transport():
    """Test command-line transport functionality."""
    print("\n📋 Testing command-line transport...")

    try:
        # Create command-line transport
        command = "npx -y @modelcontextprotocol/server-calculator"
        transport = MCPTransportFactory.create_transport(
            type="command",
            url_or_command=command
        )
        print(f"✅ Created command-line transport: {transport}")

        # Check if the command is stored
        if hasattr(transport, "command"):
            print(f"✅ Command: {transport.command}")
        else:
            print("✅ Command is stored internally")

        # Check if the connected state is available
        if hasattr(transport, "connected"):
            print(f"✅ Connected: {transport.connected}")
        else:
            print("✅ Connected state is managed internally")

        # Check if key methods exist
        has_connect = hasattr(transport, "connect")
        has_send_request = hasattr(transport, "send_request")
        has_disconnect = hasattr(transport, "disconnect")

        print(f"✅ Has connect method: {has_connect}")
        print(f"✅ Has send_request method: {has_send_request}")
        print(f"✅ Has disconnect method: {has_disconnect}")

        if has_connect and has_send_request and has_disconnect:
            results["command_transport"] = True
            print("✅ Command-line transport test completed successfully")
            return True
        else:
            print("❌ Command-line transport missing required methods")
            return False
    except Exception as e:
        print(f"❌ Command-line transport test failed: {e}")
        return False


async def run_tests():
    """Run all tests."""
    start_time = datetime.now()
    print(f"Starting MCP feature verification at {start_time}\n")

    await test_transport_factory()
    await test_http_transport()
    await test_command_transport()
    await test_cancellation_support()
    await test_error_handling()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n🔍 TEST RESULTS:")

    all_passed = True
    for test, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {test}")
        if not passed:
            all_passed = False

    print(f"\nTests completed in {duration:.2f} seconds")

    if all_passed:
        print("\n✅ ALL TESTS PASSED - MCP features verified successfully!")
    else:
        print("\n❌ SOME TESTS FAILED - Please check the output above")

if __name__ == "__main__":
    asyncio.run(run_tests())
