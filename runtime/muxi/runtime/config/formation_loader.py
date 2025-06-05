# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Formation Loader - Modular and Flattened Support
# Description:  Loader for both modular formation directories and flattened files
# Role:         Provides unified loading for formation configurations
# Usage:        Used to load formation configs from files or directories
# Author:       Muxi Framework Team
#
# The Formation Loader provides support for two formation configuration formats:
#
# 1. Flattened Formation Files
#    - Single YAML file with all configuration inline
#    - Traditional approach for simple formations
#    - Quick setup and prototyping
#
# 2. Modular Formation Directories
#    - Directory structure with separate files for each component
#    - Better organization for complex formations
#    - Team collaboration and version control friendly
#
# Key features include:
#
# 1. Auto-Detection
#    - Detects whether input is a file or directory
#    - Automatically chooses appropriate loading strategy
#    - Fallback handling for edge cases
#
# 2. Modular Directory Support
#    - Auto-discovery of agents/, mcp/, a2a/ subdirectories
#    - Merges individual YAML files into unified configuration
#    - Knowledge path resolution relative to formation directory
#
# 3. Secrets Integration
#    - Processes GitHub Actions-style secrets syntax
#    - Formation-level secrets management
#    - Consistent secrets handling across both formats
#
# Example usage:
#
#   # Load flattened formation
#   loader = FormationLoader()
#   config = await loader.load("formation.yaml", secrets_manager)
#
#   # Load modular formation
#   config = await loader.load("./formation-template/", secrets_manager)
# =============================================================================

import os
import glob
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from .loader import ConfigLoader


class FormationLoader:
    """
    Unified loader for both flattened and modular formation configurations.

    This class provides a single interface for loading formation configurations
    regardless of whether they are stored as a single YAML file or as a modular
    directory structure with separate files for different components.
    """

    def __init__(self):
        """Initialize the formation loader."""
        self.config_loader = ConfigLoader()

    async def load(
        self,
        path: str,
        secrets_manager: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Load formation configuration from either a file or directory.

        Args:
            path: Path to formation file or directory
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Dict[str, Any]: The processed formation configuration

        Raises:
            ValueError: If the path doesn't exist or configuration is invalid
            FileNotFoundError: If the specified path doesn't exist
        """
        path_obj = Path(path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Formation path not found: {path}")

        if path_obj.is_file():
            # Flattened formation file
            logger.info(f"Loading flattened formation from file: {path}")
            return await self._load_flattened_formation(path, secrets_manager)
        elif path_obj.is_dir():
            # Modular formation directory
            logger.info(f"Loading modular formation from directory: {path}")
            return await self._load_modular_formation(path, secrets_manager)
        else:
            raise ValueError(f"Invalid formation path: {path} (not a file or directory)")

    async def _load_flattened_formation(
        self,
        file_path: str,
        secrets_manager: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Load a flattened formation file.

        Args:
            file_path: Path to the formation YAML file
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Dict[str, Any]: The processed formation configuration
        """
        # Use existing ConfigLoader to load and process the file
        config = self.config_loader.load(file_path)
        config = await self.config_loader.process_secrets(config, secrets_manager)

        # Resolve knowledge paths relative to formation file directory
        formation_dir = os.path.dirname(os.path.abspath(file_path))
        config = self._resolve_knowledge_paths(config, formation_dir)

        logger.info(f"✅ Loaded flattened formation: {config.get('name', 'unnamed')}")
        return config

    async def _load_modular_formation(
        self,
        directory_path: str,
        secrets_manager: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Load a modular formation from a directory structure.

        Expected directory structure:
        formation-directory/
        ├── formation.yaml         # Main formation configuration
        ├── agents/               # Agent configurations
        │   ├── agent1.yaml
        │   └── agent2.yaml
        ├── mcp/                  # MCP server configurations
        │   ├── tool1.yaml
        │   └── tool2.yaml
        ├── a2a/                  # A2A service configurations
        │   ├── service1.yaml
        │   └── service2.yaml
        ├── knowledge/            # Knowledge base files
        │   ├── docs/
        │   └── guides/
        └── secrets.enc           # Encrypted secrets (optional)

        Args:
            directory_path: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Dict[str, Any]: The processed formation configuration
        """
        formation_dir = Path(directory_path)

        # Load main formation.yaml file
        main_config_path = formation_dir / "formation.yaml"
        if not main_config_path.exists():
            raise FileNotFoundError(
                f"Main formation.yaml not found in directory: {directory_path}"
            )

        # Load the main configuration
        main_config = self.config_loader.load(str(main_config_path))
        main_config = await self.config_loader.process_secrets(main_config, secrets_manager)

        # Auto-discover and merge component configurations
        await self._discover_and_merge_agents(main_config, formation_dir, secrets_manager)
        await self._discover_and_merge_mcp_servers(main_config, formation_dir, secrets_manager)
        await self._discover_and_merge_a2a_services(main_config, formation_dir, secrets_manager)

        # Resolve knowledge paths relative to formation directory
        main_config = self._resolve_knowledge_paths(main_config, str(formation_dir))

        logger.info(f"✅ Loaded modular formation: {main_config.get('name', 'unnamed')}")
        return main_config

    async def _discover_and_merge_agents(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None
    ) -> None:
        """
        Discover agent configurations in the agents/ directory and merge them.

        Args:
            config: Main formation configuration to merge into
            formation_dir: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation
        """
        agents_dir = formation_dir / "agents"
        if not agents_dir.exists():
            logger.debug("No agents/ directory found, skipping agent discovery")
            return

        # Find all YAML files in agents directory
        agent_files = []
        for pattern in ["*.yaml", "*.yml"]:
            agent_files.extend(agents_dir.glob(pattern))

        if not agent_files:
            logger.debug("No agent configuration files found in agents/ directory")
            return

        # Initialize agents list if not present
        if "agents" not in config:
            config["agents"] = []

        # Load and merge each agent configuration
        for agent_file in sorted(agent_files):
            try:
                logger.debug(f"Loading agent config: {agent_file}")
                agent_config = self.config_loader.load(str(agent_file))
                agent_config = await self.config_loader.process_secrets(agent_config, secrets_manager)

                # Ensure agent has an ID (use filename if not specified)
                if "id" not in agent_config:
                    agent_config["id"] = agent_file.stem

                config["agents"].append(agent_config)
                logger.info(f"✅ Discovered agent: {agent_config.get('id', agent_file.stem)}")

            except Exception as e:
                logger.error(f"Failed to load agent config from {agent_file}: {e}")
                continue

        logger.info(f"✅ Discovered {len(config['agents'])} agents from agents/ directory")

    async def _discover_and_merge_mcp_servers(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None
    ) -> None:
        """
        Discover MCP server configurations in the mcp/ directory and merge them.

        Args:
            config: Main formation configuration to merge into
            formation_dir: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation
        """
        mcp_dir = formation_dir / "mcp"
        if not mcp_dir.exists():
            logger.debug("No mcp/ directory found, skipping MCP server discovery")
            return

        # Find all YAML files in mcp directory
        mcp_files = []
        for pattern in ["*.yaml", "*.yml"]:
            mcp_files.extend(mcp_dir.glob(pattern))

        if not mcp_files:
            logger.debug("No MCP server configuration files found in mcp/ directory")
            return

        # Initialize MCP servers structure if not present
        if "mcp" not in config:
            config["mcp"] = {}
        if "servers" not in config["mcp"]:
            config["mcp"]["servers"] = []

        # Load and merge each MCP server configuration
        for mcp_file in sorted(mcp_files):
            try:
                logger.debug(f"Loading MCP server config: {mcp_file}")
                mcp_config = self.config_loader.load(str(mcp_file))
                mcp_config = await self.config_loader.process_secrets(mcp_config, secrets_manager)

                # Ensure MCP server has an ID (use filename if not specified)
                if "id" not in mcp_config:
                    mcp_config["id"] = mcp_file.stem

                config["mcp"]["servers"].append(mcp_config)
                logger.info(f"✅ Discovered MCP server: {mcp_config.get('id', mcp_file.stem)}")

            except Exception as e:
                logger.error(f"Failed to load MCP server config from {mcp_file}: {e}")
                continue

        logger.info(f"✅ Discovered {len(config['mcp']['servers'])} MCP servers from mcp/ directory")

    async def _discover_and_merge_a2a_services(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None
    ) -> None:
        """
        Discover A2A service configurations in the a2a/ directory and merge them.

        Args:
            config: Main formation configuration to merge into
            formation_dir: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation
        """
        a2a_dir = formation_dir / "a2a"
        if not a2a_dir.exists():
            logger.debug("No a2a/ directory found, skipping A2A service discovery")
            return

        # Find all YAML files in a2a directory
        a2a_files = []
        for pattern in ["*.yaml", "*.yml"]:
            a2a_files.extend(a2a_dir.glob(pattern))

        if not a2a_files:
            logger.debug("No A2A service configuration files found in a2a/ directory")
            return

        # Initialize A2A outbound services structure if not present
        if "a2a" not in config:
            config["a2a"] = {}
        if "outbound" not in config["a2a"]:
            config["a2a"]["outbound"] = {}
        if "services" not in config["a2a"]["outbound"]:
            config["a2a"]["outbound"]["services"] = []

        # Load and merge each A2A service configuration
        for a2a_file in sorted(a2a_files):
            try:
                logger.debug(f"Loading A2A service config: {a2a_file}")
                a2a_config = self.config_loader.load(str(a2a_file))
                a2a_config = await self.config_loader.process_secrets(a2a_config, secrets_manager)

                # Ensure A2A service has an ID (use filename if not specified)
                if "id" not in a2a_config:
                    a2a_config["id"] = a2a_file.stem

                config["a2a"]["outbound"]["services"].append(a2a_config)
                logger.info(f"✅ Discovered A2A service: {a2a_config.get('id', a2a_file.stem)}")

            except Exception as e:
                logger.error(f"Failed to load A2A service config from {a2a_file}: {e}")
                continue

        logger.info(f"✅ Discovered {len(config['a2a']['outbound']['services'])} A2A services from a2a/ directory")

    def _resolve_knowledge_paths(
        self,
        config: Dict[str, Any],
        formation_dir: str
    ) -> Dict[str, Any]:
        """
        Resolve knowledge paths to be relative to formation directory.

        This method processes knowledge configuration paths and resolves them relative
        to the formation directory. Absolute paths (starting with '/') are preserved.

        Args:
            config: Formation configuration
            formation_dir: Path to the formation directory

        Returns:
            Dict[str, Any]: Configuration with resolved knowledge paths
        """
        # Process overlord knowledge configuration
        if "overlord" in config and "knowledge" in config["overlord"]:
            knowledge_config = config["overlord"]["knowledge"]
            if knowledge_config.get("enabled", False):
                sources = knowledge_config.get("sources", [])
                for source in sources:
                    if "path" in source:
                        source["path"] = self._resolve_single_path(source["path"], formation_dir)

        # Process agent knowledge configurations
        if "agents" in config:
            for agent in config["agents"]:
                if "knowledge" in agent:
                    knowledge_config = agent["knowledge"]
                    if knowledge_config.get("enabled", False):
                        sources = knowledge_config.get("sources", [])
                        for source in sources:
                            if "path" in source:
                                source["path"] = self._resolve_single_path(source["path"], formation_dir)

        return config

    def _resolve_single_path(self, path: str, formation_dir: str) -> str:
        """
        Resolve a single path relative to formation directory.

        Args:
            path: Original path from configuration
            formation_dir: Formation directory path

        Returns:
            str: Resolved absolute path
        """
        if os.path.isabs(path):
            # Absolute path - return as-is
            return path
        else:
            # Relative path - resolve relative to formation_dir/knowledge/
            knowledge_base_dir = os.path.join(formation_dir, "knowledge")
            resolved_path = os.path.join(knowledge_base_dir, path)
            return os.path.abspath(resolved_path)

    def detect_formation_type(self, path: str) -> str:
        """
        Detect whether a path contains a flattened or modular formation.

        Args:
            path: Path to examine

        Returns:
            str: "flattened", "modular", or "unknown"
        """
        path_obj = Path(path)

        if not path_obj.exists():
            return "unknown"

        if path_obj.is_file() and path_obj.suffix in [".yaml", ".yml"]:
            return "flattened"
        elif path_obj.is_dir():
            # Check if it has formation.yaml and component directories
            main_config = path_obj / "formation.yaml"
            if main_config.exists():
                # Look for component directories
                has_agents = (path_obj / "agents").exists()
                has_mcp = (path_obj / "mcp").exists()
                has_a2a = (path_obj / "a2a").exists()

                if has_agents or has_mcp or has_a2a:
                    return "modular"
                else:
                    return "simple_directory"  # Directory with just formation.yaml
            else:
                return "unknown"
        else:
            return "unknown"
