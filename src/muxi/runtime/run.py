# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Run - Server Startup Functionality
# Description:  Functions for starting and running Muxi servers
# Role:         Provides server initialization capabilities for the Muxi framework
# Usage:        Imported by facade.py and used to start API servers
# Author:       Muxi Framework Team
#
# The run.py file provides the functionality to start and run Muxi servers.
# It includes:
#
# 1. Server Initialization
#    - Starting API servers on specified host and port
#    - Checking port availability before startup
#    - Handling server configuration parameters
#
# 2. Error Handling
#    - Detecting and reporting port conflicts
#    - Managing server startup exceptions
#    - Providing detailed logging and user-friendly error messages
#
# This module is typically used via the Muxi facade:
#
#   app = muxi()
#   app.run(host="0.0.0.0", port=5050)
#
# Or it can be used directly in more advanced scenarios:
#
#   from .run import run_server
#   run_server(host="0.0.0.0", port=5050, reload=False, mcp=True)
#
# Note: The current implementation is a placeholder that will be replaced
# with a full server implementation according to the Muxi API specifications.
# =============================================================================

import socket

# Loguru import removed - add observability import

# Observability imports
from . import observability


def is_port_in_use(port):
    """
    Check if a port is in use.

    This function attempts to create a socket connection to the specified port
    on localhost to determine if the port is already being used by another process.
    It's used to prevent port conflicts before starting the server.

    Args:
        port (int): The port number to check. Must be a valid port number (1-65535).

    Returns:
        bool: True if the port is in use (unavailable), False if the port is free.
    """
    # Log port check attempt
    observability.emit_event(
        event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
        level=observability.EventLevel.DEBUG,
        description="Port availability check initiated",
        data={"port": port, "operation": "port_check"},
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # connect_ex returns 0 if the connection succeeds (port is in use)
        # and a non-zero value if it fails (port is available)
        result = s.connect_ex(("localhost", port)) == 0

        # Log port check result
        observability.emit_event(
            event_type=(
                observability.SystemEvents.RESOURCE_ALLOCATED
                if not result
                else observability.ErrorEvents.RETRY_ATTEMPTED
            ),
            level=observability.EventLevel.INFO if not result else observability.EventLevel.WARNING,
            description=f"Port {port} {'in use' if result else 'available'}",
            data={"port": port, "in_use": result, "operation": "port_check_result"},
        )

        return result


def run_server(host="0.0.0.0", port=5050, reload=True, mcp=False):
    """
    Start the MUXI server with all enabled components.

    This function initializes and starts the Muxi API server with the specified
    configuration. It checks for port availability before attempting to start
    and provides appropriate feedback.

    This is currently a placeholder implementation that only logs the attempt to start
    a server. In the future, this will be replaced with proper server implementations
    according to the Muxi API specifications.

    Args:
        host (str): Host address to bind the server to. Defaults to "0.0.0.0" which
            makes the server available on all network interfaces.
        port (int): Port number to bind the server to. Defaults to 5050.
        reload (bool): Whether to enable auto-reload for development mode, which
            automatically restarts the server when code changes. Defaults to True.
        mcp (bool): Whether to enable Model Context Protocol (MCP) support for
            tool calling and external integrations. Defaults to False.

    Returns:
        bool: True if server started successfully, False otherwise. Can be used
            to determine if startup succeeded in programmatic contexts.
    """
    # Log server startup attempt
    observability.emit_event(
        event_type=observability.SystemEvents.SESSION_CREATED,
        level=observability.EventLevel.INFO,
        description="Server startup initiated",
        data={
            "host": host,
            "port": port,
            "reload": reload,
            "mcp": mcp,
            "operation": "server_startup",
        },
    )

    try:
        # Check if port is already in use before attempting to start the server
        if is_port_in_use(port):
            # Construct error message for both logs and user output
            msg = f"Port {port} is already in use. MUXI server cannot start."

            # Log port conflict error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="Server startup failed due to port conflict",
                data={
                    "port": port,
                    "host": host,
                    "error": "port_in_use",
                    "operation": "server_startup_failed",
                },
            )

            # Log the error to the application logs
            #  Error - add observability event
            # Print user-friendly error messages to the console
            print(f"Error: {msg}")
            print(f"Please stop any other processes using port {port} and try again.")
            return False

        # For now, we'll just log that we would have started a server
        # This will be replaced with actual implementation later
        #  Info - add observability event
        #     f"[PLACEHOLDER] Starting MUXI server on {host}:{port} " f"(reload={reload}, mcp={mcp})"
        # )
        print(f"[PLACEHOLDER] MUXI server would start on {host}:{port}")
        print("This is a placeholder until the MUXI API server is implemented.")

        # Log successful server startup (placeholder)
        observability.emit_event(
            event_type=observability.SystemEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description="Server startup completed (placeholder)",
            data={
                "host": host,
                "port": port,
                "reload": reload,
                "mcp": mcp,
                "operation": "server_startup_success",
                "placeholder": True,
            },
        )

        return True
    except Exception as e:
        # Log server startup exception
        observability.emit_event(
            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
            level=observability.EventLevel.ERROR,
            description="Server startup failed with exception",
            data={
                "host": host,
                "port": port,
                "error": str(e),
                "error_type": type(e).__name__,
                "operation": "server_startup_exception",
            },
        )

        # Catch any unexpected exceptions during server startup
        # Log the error with detailed information for debugging
        #  Error - add observability event
        # Provide a simplified error message to the user
        print(f"Error: Failed to start MUXI server: {str(e)}")
        return False
