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

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.muxi.formation import Formation  # noqa: E402


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

    # Check if file exists
    if not Path(formation_path).exists():
        print(f"Error: Formation file not found: {formation_path}")
        sys.exit(1)

    # Run the formation
    asyncio.run(run_formation(formation_path))


if __name__ == "__main__":
    main()
