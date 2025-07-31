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
from pathlib import Path

# Import using relative imports to avoid sys.path manipulation
try:
    from ...formation import Formation
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

    from src.muxi.formation import Formation


async def run_formation(formation_path: str):
    """Load and run a formation with its API server."""
    formation = Formation()

    try:
        print(f"Loading formation from: {formation_path}")
        await formation.load(formation_path)

        print("Starting formation server...")
        # This will block until the server is stopped
        await formation.start_server(block=True)

    except KeyboardInterrupt:
        print("\nShutting down formation...")
        await formation.stop()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    """Main entry point for the module."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.muxi.utils.run_formation <formation.yaml>")
        print("\nFor auto-reload with nodemon:")
        print(
            '  nodemon --exec "python -m src.muxi.utils.run_formation formation.yaml" --ext py,yaml'
        )
        sys.exit(1)

    formation_path = sys.argv[1]

    # Run the formation - file existence will be checked during loading
    asyncio.run(run_formation(formation_path))


if __name__ == "__main__":
    main()
