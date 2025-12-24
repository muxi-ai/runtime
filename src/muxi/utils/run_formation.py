#!/usr/bin/env python3
"""
Run a MUXI formation for development with auto-reload support.

This module provides a simple way to run formations during development:
    python -m src.muxi.utils.run_formation path/to/formation.afs

For auto-reload with nodemon:
    nodemon --exec "python -m src.muxi.utils.run_formation formation.afs" --ext py,yaml
"""

import sys

# Print banner immediately before heavy imports
def _print_banner():
    from ..utils.version import get_version
    version = get_version()
    print("\n" + "="*68)
    print(" __  __ _    ___   _______   ____             _   _")
    print("|  \\/  | |  | \\ \\ / /_   _| |    \\_   _ _ __ | | (_)_ __ ___   ___")
    print("| \\  / | |  | |\\ V /  | |   | [ ] || | | '_ \\| __| | '_ ` _ \\ / _ \\")
    print("| |\\/| | |__| |/ . \\ _| |_  |  _ / |_| | | | | |_| | | | | | |  __/")
    print("|_|  |_|\\____//_/ \\_\\_____| |_| \\_\\__/_| |_|\\__|_|_| |_| |_|\\___|")
    print(" ")
    print(f"Starting MUXI Runtime v{version}...")
    print("="*68 + "\n")
    sys.stdout.flush()

# Only print banner when running as main script
if __name__ == "__main__" or "run_formation" in sys.argv[0]:
    _print_banner()

import asyncio
import traceback
from pathlib import Path

# Import using relative imports to avoid sys.path manipulation
try:
    from ...formation import Formation  # noqa: E402
    from ...services import observability
    from ...datatypes.exceptions import (
        ConfigurationLoadError,
        ConfigurationNotFoundError,
        ConfigurationValidationError,
        DependencyValidationError,
        ServiceStartupError,
        OverlordError,
        OverlordStartupError,
        MCPConnectionError,
    )
except ImportError:
    # Fallback for development environments where package isn't installed
    # Find project root by looking for pyproject.toml or setup.py
    current_dir = Path(__file__).parent
    project_root = current_dir
    while project_root.parent != project_root:
        if (project_root / "pyproject.toml").exists() or (project_root / "setup.py").exists():
            break
        project_root = project_root.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.muxi.formation import Formation  # noqa: E402
    from src.muxi.services import observability
    from src.muxi.datatypes.exceptions import (
        ConfigurationLoadError,
        ConfigurationNotFoundError,
        ConfigurationValidationError,
        DependencyValidationError,
        ServiceStartupError,
        OverlordError,
        OverlordStartupError,
        MCPConnectionError,
    )


async def run_formation(formation_path: str, port: int = None, host: str = None):
    """Load and run a formation with its API server."""
    formation = Formation()
    formation_loaded = False

    try:
        # REMOVE - line 64 (redundant with InitEventFormatter section 1: Formation banner)

        await formation.load(formation_path)
        formation_loaded = True

        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "run_formation",
                "formation_id": formation.config.get("id", "unknown"),
                "port_override": port,
                "host_override": host,
            },
            description="Starting formation server...",
        )

        # This will block until the server is stopped
        # Port and host overrides from CLI take precedence over formation.afs
        await formation.start_server(host=host, port=port, block=True)

    except KeyboardInterrupt:
        observability.observe(
            event_type=observability.SystemEvents.CLEANUP,
            level=observability.EventLevel.INFO,
            data={
                "service": "run_formation",
                "reason": "keyboard_interrupt",
            },
            description="Shutting down formation due to keyboard interrupt...",
        )

    except ConfigurationNotFoundError as e:
        observability.observe(
            event_type=observability.ErrorEvents.RESOURCE_NOT_FOUND,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "ConfigurationNotFoundError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Formation configuration not found: {e}",
        )
        sys.exit(1)

    except ConfigurationValidationError as e:
        observability.observe(
            event_type=observability.ErrorEvents.VALIDATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "ConfigurationValidationError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Formation configuration validation failed: {e}",
        )
        sys.exit(1)

    except DependencyValidationError as e:
        observability.observe(
            event_type=observability.ErrorEvents.DEPENDENCY_ERROR,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "DependencyValidationError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Formation dependency validation failed: {e}",
        )
        sys.exit(1)

    except MCPConnectionError as e:
        observability.observe(
            event_type=observability.ErrorEvents.NETWORK_ERROR,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "MCPConnectionError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"MCP connection error while loading formation: {e}",
        )
        sys.exit(1)

    except ServiceStartupError as e:
        observability.observe(
            event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "ServiceStartupError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Service startup error: {e}",
        )
        sys.exit(1)

    except OverlordStartupError as e:
        observability.observe(
            event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "OverlordStartupError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Overlord startup error: {e}",
        )
        sys.exit(1)

    except OverlordError as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "OverlordError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Overlord error: {e}",
        )
        sys.exit(1)

    except ConfigurationLoadError as e:
        observability.observe(
            event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": "ConfigurationLoadError",
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Failed to load formation configuration: {e}",
        )
        sys.exit(1)

    except Exception as e:
        # Catch any unexpected errors
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={
                "service": "run_formation",
                "error_type": type(e).__name__,
                "formation_path": formation_path,
                "traceback": traceback.format_exc(),
            },
            description=f"Unexpected error: {e}",
        )
        sys.exit(1)

    finally:
        # Ensure formation is properly stopped to prevent resource leaks
        if formation_loaded:
            try:
                await formation.stop()
                observability.observe(
                    event_type=observability.SystemEvents.CLEANUP,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "run_formation",
                        "formation_path": formation_path,
                    },
                    description="Formation stopped successfully",
                )
            except Exception as e:
                # Log but don't raise - we're already in cleanup
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={
                        "service": "run_formation",
                        "error_type": type(e).__name__,
                        "error": str(e),
                        "formation_path": formation_path,
                    },
                    description=f"Error stopping formation during cleanup: {e}",
                )


def main():
    """Main entry point for the module."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a MUXI formation with its API server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings from formation.afs
  python -m muxi.utils.run_formation formation.afs

  # Override port and host
  python -m muxi.utils.run_formation formation.afs --port 8080 --host 0.0.0.0

  # Auto-reload with nodemon
  nodemon --exec "python -m muxi.utils.run_formation formation.afs" --ext py,yaml
        """
    )

    parser.add_argument(
        "formation_path",
        help="Path to formation.afs file"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to bind server (overrides formation.afs)"
    )
    parser.add_argument(
        "--host",
        help="Host to bind server (overrides formation.afs, default: 127.0.0.1)"
    )

    args = parser.parse_args()

    # Initialize observability system
    # REMOVE - line 271 (redundant with InitEventFormatter section 1: Formation banner)

    # Run the formation - file existence will be checked during loading
    asyncio.run(run_formation(args.formation_path, port=args.port, host=args.host))


if __name__ == "__main__":
    main()
