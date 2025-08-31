#!/usr/bin/env python3
"""
Run a MUXI formation for development with auto-reload support.

This module provides a simple way to run formations during development:
    python -m src.muxi.utils.run_formation path/to/formation.yaml

For auto-reload with nodemon:
    nodemon --exec "python -m src.muxi.utils.run_formation formation.yaml" --ext py,yaml
"""

import asyncio
import sys
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


async def run_formation(formation_path: str):
    """Load and run a formation with its API server."""
    formation = Formation()
    formation_loaded = False

    try:
        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "run_formation",
                "formation_path": formation_path,
            },
            description=f"Loading formation from: {formation_path}",
        )

        await formation.load(formation_path)
        formation_loaded = True

        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "run_formation",
                "formation_id": formation.config.get("id", "unknown"),
            },
            description="Starting formation server...",
        )

        # This will block until the server is stopped
        await formation.start_server(block=True)

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
    if len(sys.argv) < 2:
        # For usage messages, we still use print since this is user-facing CLI output
        print("Usage: python -m src.muxi.utils.run_formation <formation.yaml>")
        print("\nFor auto-reload with nodemon:")
        print(
            '  nodemon --exec "python -m src.muxi.utils.run_formation formation.yaml" --ext py,yaml'
        )
        sys.exit(1)

    formation_path = sys.argv[1]

    # Initialize observability system
    observability.observe(
        event_type=observability.SystemEvents.INITIALIZING,
        level=observability.EventLevel.INFO,
        data={
            "service": "run_formation",
            "formation_path": formation_path,
        },
        description=f"Starting formation runner with path: {formation_path}",
    )

    # Run the formation - file existence will be checked during loading
    asyncio.run(run_formation(formation_path))


if __name__ == "__main__":
    main()
