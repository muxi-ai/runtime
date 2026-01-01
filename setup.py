"""
Setup script for MUXI Runtime.

This setup.py exists primarily to handle the post-install hook for downloading
spaCy models. All package metadata and dependencies are defined in pyproject.toml.
"""

from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop
from setuptools.command.egg_info import egg_info
import subprocess
import sys
import os

# For reading pyproject.toml
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Python 3.10 with tomli installed
    except ImportError:
        print("ERROR: tomli is required for Python < 3.11")
        print("Install it with: pip install tomli")
        sys.exit(1)


def download_spacy_model():
    """Download the spaCy English model."""
    try:
        print("Downloading spaCy English model (en_core_web_sm)...")
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
        print("✓ Successfully downloaded spaCy English model")
    except subprocess.CalledProcessError as e:
        print(f"⚠ Warning: Failed to download spaCy model: {e}")
        print("  Please run manually: python -m spacy download en_core_web_sm")
    except Exception as e:
        print(f"⚠ Warning: Unexpected error downloading spaCy model: {e}")
        print("  Please run manually: python -m spacy download en_core_web_sm")


def install_muxi_cli():
    """Install the MUXI CLI (Go binary)."""
    # TODO: When the Go CLI is ready, implement installation here
    # This should:
    # 1. Detect the platform (Linux/macOS/Windows, AMD64/ARM64)
    # 2. Download the appropriate binary from GitHub releases
    # 3. Install it to a location in PATH (e.g., /usr/local/bin/muxi)
    # 4. Make it executable (chmod +x on Unix systems)
    #
    # Example implementation:
    # platform = detect_platform()
    # binary_url = f"https://github.com/muxi-ai/cli/releases/latest/download/muxi_{platform}"
    # install_location = get_install_location()  # /usr/local/bin/muxi or ~/.local/bin/muxi
    # download_binary(binary_url, install_location)
    # make_executable(install_location)
    pass


class PostInstallCommand(install):
    """Post-installation for development install."""
    def run(self):
        install.run(self)
        download_spacy_model()
        install_muxi_cli()  # TODO: Enable when Go CLI is ready


class PostDevelopCommand(develop):
    """Post-installation for editable install."""
    def run(self):
        develop.run(self)
        download_spacy_model()
        # Skip CLI installation for development mode


class PostEggInfoCommand(egg_info):
    """Post-installation for egg info."""
    def run(self):
        egg_info.run(self)
        # Don't download on egg_info as it's called frequently


# Read configuration from pyproject.toml - SINGLE SOURCE OF TRUTH
if not os.path.exists("pyproject.toml"):
    print("ERROR: pyproject.toml not found")
    print("This file is required for installation")
    sys.exit(1)

try:
    with open("pyproject.toml", "rb") as f:
        pyproject = tomllib.load(f)
except Exception as e:
    print(f"ERROR: Failed to parse pyproject.toml: {e}")
    sys.exit(1)

# Extract configuration
project_config = pyproject.get("project", {})
if not project_config:
    print("ERROR: No [project] section found in pyproject.toml")
    sys.exit(1)

# Required fields
name = project_config.get("name")
if not name:
    print("ERROR: 'name' is required in pyproject.toml")
    sys.exit(1)

# Version from .version file (for CI/CD)
version_file = os.path.join("src", "muxi", "runtime", ".version")
try:
    with open(version_file, "r") as f:
        version = f.read().strip()
except FileNotFoundError:
    print(f"ERROR: Version file not found: {version_file}")
    sys.exit(1)

# Optional fields with defaults
description = project_config.get("description", "")
authors = project_config.get("authors", [])
author = authors[0]["name"] if authors else ""
author_email = authors[0]["email"] if authors else ""
install_requires = project_config.get("dependencies", [])
extras_require = project_config.get("optional-dependencies", {})
python_requires = project_config.get("requires-python", ">=3.10")
classifiers = project_config.get("classifiers", [])
urls = project_config.get("urls", {})

# Read long description from README
try:
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()
except FileNotFoundError:
    long_description = description

# Run setup with configuration from pyproject.toml
setup(
    name=name,
    version=version,
    author=author,
    author_email=author_email,
    description=description,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=urls.get("Homepage", "https://github.com/muxi-ai/runtime"),
    project_urls=urls,
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={
        "muxi.runtime": [
            ".version",
            "**/*.md",
            "**/*.yaml",
            "**/*.yml",
            "**/*.json",
            "**/*.txt",
            "extensions/loadable/**/*.so",
            "extensions/loadable/**/*.dylib",
            "extensions/loadable/**/*.dll",
        ]
    },
    include_package_data=True,
    classifiers=classifiers,
    python_requires=python_requires,
    install_requires=install_requires,
    extras_require=extras_require,
    # CLI will be installed as Go binary in post-install
    cmdclass={
        'install': PostInstallCommand,
        'develop': PostDevelopCommand,
        'egg_info': PostEggInfoCommand,
    },
    zip_safe=False,
)
