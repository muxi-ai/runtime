#!/usr/bin/env python3
"""
Generate requirements.txt from pyproject.toml

This script reads dependencies from pyproject.toml and generates a requirements.txt file.
Use this for Docker builds or environments that need requirements.txt.

Usage:
    python scripts/sync_requirements.py
"""

import sys
import os

# Add parent directory to path to import from setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: tomli/tomllib not available. Install with: pip install tomli")
        sys.exit(1)


def main():
    """Generate requirements.txt from pyproject.toml."""
    pyproject_path = "pyproject.toml"
    requirements_path = "requirements.txt"

    if not os.path.exists(pyproject_path):
        print(f"Error: {pyproject_path} not found")
        sys.exit(1)

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    dependencies = data.get("project", {}).get("dependencies", [])

    # Write requirements.txt
    with open(requirements_path, "w") as f:
        f.write("# Auto-generated from pyproject.toml\n")
        f.write("# DO NOT EDIT MANUALLY - Use: python scripts/sync_requirements.py\n")
        f.write("# Or edit pyproject.toml and regenerate\n\n")

        for dep in dependencies:
            # Skip the tomli dependency as it's only needed for building
            if "tomli" not in dep:
                f.write(f"{dep}\n")

        # Add dev dependencies as optional section
        dev_deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
        if dev_deps:
            f.write("\n# Development dependencies (install with pip install -e .[dev])\n")
            for dep in dev_deps:
                f.write(f"# {dep}\n")

    print(f"✓ Generated {requirements_path} from {pyproject_path}")
    print(f"  {len(dependencies)} dependencies written")


if __name__ == "__main__":
    main()
