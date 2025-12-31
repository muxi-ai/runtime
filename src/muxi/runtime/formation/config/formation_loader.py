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
#   config = await loader.load("formation.afs", secrets_manager)
#
#   # Load modular formation
#   config = await loader.load("./formation-template/", secrets_manager)
# =============================================================================

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


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

    def _validate_config_is_dict(self, config: Any, file_name: str, config_type: str) -> bool:
        """
        Validate that a loaded configuration is a dictionary.

        Args:
            config: The loaded configuration to validate
            file_name: Name of the file that was loaded
            config_type: Type of configuration (e.g., "Agent", "MCP", "A2A")

        Returns:
            bool: True if config is a dictionary, False otherwise
        """
        if not isinstance(config, dict):
            print(f"⚠️  Warning: {config_type} file '{file_name}' contains {type(config).__name__} instead of dict - skipping")  # noqa: E501
            return False
        return True

    async def load(
        self, path: str, secrets_manager: Optional[Any] = None
    ) -> tuple[Dict[str, Any], set[str], Dict[str, str]]:
        """
        Load formation configuration from either a file or directory.

        Args:
            path: Path to formation file or directory
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Tuple of:
            - Dict[str, Any]: The processed formation configuration
            - set[str]: Set of secret names that are in use
            - Dict[str, str]: Registry mapping paths to original placeholder values

        Raises:
            ValueError: If the path doesn't exist or configuration is invalid
            FileNotFoundError: If the specified path doesn't exist
        """
        path_obj = Path(path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Formation path not found: {path}")

        if path_obj.is_file():
            # Flattened formation file
            #  CONFIG_FORMATION_LOADED
            return await self._load_flattened_formation(path, secrets_manager)
        elif path_obj.is_dir():
            # Modular formation directory
            #  CONFIG_FORMATION_LOADED
            return await self._load_modular_formation(path, secrets_manager)
        else:
            raise ValueError(f"Invalid formation path: {path} (not a file or directory)")

    async def _load_flattened_formation(
        self, file_path: str, secrets_manager: Optional[Any] = None
    ) -> tuple[Dict[str, Any], set[str], Dict[str, str]]:
        """
        Load a flattened formation file.

        Args:
            file_path: Path to the formation YAML file
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Tuple of:
            - Dict[str, Any]: The processed formation configuration
            - set[str]: Set of secret names that are in use
            - Dict[str, str]: Registry mapping paths to original placeholder values
        """
        # Use existing ConfigLoader to load and process the file
        config = self.config_loader.load(file_path)
        config, secrets_in_use, placeholder_registry = await self.config_loader.process_secrets(
            config, secrets_manager
        )

        # Filter inline agents by active field
        self._filter_inline_agents_by_active(config)

        # Filter inline MCP servers by active field
        self._filter_inline_mcp_servers_by_active(config)

        # Resolve knowledge paths relative to formation file directory
        formation_dir = os.path.dirname(os.path.abspath(file_path))
        formation_dir_path = Path(formation_dir)

        # Auto-discover and merge component configurations if available
        # This allows flattened formations to also benefit from auto-discovery
        await self._discover_and_merge_agents(
            config, formation_dir_path, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._discover_and_merge_mcp_servers(
            config, formation_dir_path, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._discover_and_merge_a2a_services(
            config, formation_dir_path, secrets_manager, secrets_in_use, placeholder_registry
        )

        config = self._resolve_knowledge_paths(config, formation_dir)

        return config, secrets_in_use, placeholder_registry

    async def _load_modular_formation(
        self, directory_path: str, secrets_manager: Optional[Any] = None
    ) -> tuple[Dict[str, Any], set[str], Dict[str, str]]:
        """
        Load a modular formation from a directory structure.

        Expected directory structure:
        formation-directory/
        ├── formation.afs         # Main formation configuration
        ├── agents/               # Agent configurations
        │   ├── agent1.afs
        │   └── agent2.afs
        ├── mcp/                  # MCP server configurations
        │   ├── tool1.afs
        │   └── tool2.afs
        ├── a2a/                  # A2A service configurations
        │   ├── service1.afs
        │   └── service2.afs
        ├── knowledge/            # Knowledge base files
        │   ├── docs/
        │   └── guides/
        └── secrets.enc           # Encrypted secrets (optional)

        Args:
            directory_path: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Tuple of:
            - Dict[str, Any]: The processed formation configuration
            - set[str]: Set of secret names that are in use
            - Dict[str, str]: Registry mapping paths to original placeholder values
        """
        formation_dir = Path(directory_path)

        # Load main formation config file (priority: .afs > .yaml > .yml)
        main_config_path = formation_dir / "formation.afs"
        if not main_config_path.exists():
            main_config_path = formation_dir / "formation.yaml"
        if not main_config_path.exists():
            main_config_path = formation_dir / "formation.yml"
        if not main_config_path.exists():
            raise FileNotFoundError(f"Main formation config (formation.afs/yaml/yml) not found in directory: {directory_path}")

        # Load the main configuration
        main_config = self.config_loader.load(str(main_config_path))
        main_config, secrets_in_use, placeholder_registry = (
            await self.config_loader.process_secrets(main_config, secrets_manager)
        )

        # Filter inline agents by active field before merging external agents
        self._filter_inline_agents_by_active(main_config)

        # Filter inline MCP servers by active field before merging external servers
        self._filter_inline_mcp_servers_by_active(main_config)

        # Auto-discover and merge component configurations
        await self._discover_and_merge_agents(
            main_config, formation_dir, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._discover_and_merge_mcp_servers(
            main_config, formation_dir, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._discover_and_merge_a2a_services(
            main_config, formation_dir, secrets_manager, secrets_in_use, placeholder_registry
        )

        # Resolve knowledge paths relative to formation directory
        main_config = self._resolve_knowledge_paths(main_config, str(formation_dir))

        return main_config, secrets_in_use, placeholder_registry

    async def _discover_and_merge_agents(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None,
        secrets_in_use: Optional[set[str]] = None,
        placeholder_registry: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Discover agent configurations in the agents/ directory and merge them.

        Args:
            config: Main formation configuration to merge into
            formation_dir: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation
            secrets_in_use: Set to accumulate secret names in use
            placeholder_registry: Registry to accumulate placeholder mappings
        """
        agents_dir = formation_dir / "agents"
        if not agents_dir.exists():
            #  AGENT_MESSAGE_PROCESSING
            return

        # Find all config files in agents directory (support .afs, .yaml, .yml)
        agent_files = []
        for pattern in ["*.afs", "*.yaml", "*.yml"]:
            agent_files.extend(agents_dir.glob(pattern))

        if not agent_files:
            #  AGENT_MESSAGE_PROCESSING
            return

        # Initialize agents list if not present
        if "agents" not in config:
            config["agents"] = []

        # Load and merge each agent configuration
        for agent_file in sorted(agent_files):
            try:
                #  AGENT_MESSAGE_PROCESSING
                agent_config = self.config_loader.load(str(agent_file))

                # Validate that agent config is a dictionary
                if not self._validate_config_is_dict(agent_config, agent_file.name, "Agent"):
                    continue

                agent_config, agent_secrets, agent_placeholders = (
                    await self.config_loader.process_secrets(agent_config, secrets_manager)
                )

                # Accumulate secrets from this agent
                if secrets_in_use is not None:
                    secrets_in_use.update(agent_secrets)

                # Accumulate placeholders with adjusted paths for agent array
                if placeholder_registry is not None:
                    agent_index = len(config["agents"])
                    for path, placeholder in agent_placeholders.items():
                        # Adjust path to include agent array index
                        adjusted_path = (
                            f"agents[{agent_index}].{path}" if path else f"agents[{agent_index}]"
                        )
                        placeholder_registry[adjusted_path] = placeholder

                # Ensure agent has an ID (use filename if not specified)
                if "id" not in agent_config:
                    agent_config["id"] = agent_file.stem

                # Check if agent is active (default to True)
                is_active = agent_config.get("active", True)

                if is_active:
                    agent_config["source"] = "formation"
                    config["agents"].append(agent_config)

            except Exception as e:
                print(
                    f"⚠️  Warning: Failed to load agent file '{agent_file.name}': {type(e).__name__}: {str(e)}"
                )
                continue
        #  AGENT_MESSAGE_PROCESSING

    def _filter_inline_agents_by_active(self, config: Dict[str, Any]) -> None:
        """
        Filter inline agents based on the active field.

        Args:
            config: Formation configuration to filter inline agents in
        """
        if "agents" not in config:
            return

        agents = config["agents"]
        if not isinstance(agents, list):
            return

        filtered_agents = []
        for agent_config in agents:
            if not isinstance(agent_config, dict):
                continue

            is_active = agent_config.get("active", True)

            if is_active:
                agent_config["source"] = "formation"
                filtered_agents.append(agent_config)

        config["agents"] = filtered_agents

    def _filter_inline_mcp_servers_by_active(self, config: Dict[str, Any]) -> None:
        """
        Filter inline MCP servers based on the active field.

        Args:
            config: Formation configuration to filter inline MCP servers in
        """
        if "mcp" not in config or "servers" not in config.get("mcp", {}):
            return

        servers = config["mcp"]["servers"]
        if not isinstance(servers, list):
            return

        filtered_servers = []
        for server_config in servers:
            if not isinstance(server_config, dict):
                continue

            is_active = server_config.get("active", True)

            if is_active:
                server_config["source"] = "formation"
                filtered_servers.append(server_config)

        config["mcp"]["servers"] = filtered_servers

    async def _discover_and_merge_mcp_servers(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None,
        secrets_in_use: Optional[set[str]] = None,
        placeholder_registry: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Discover MCP server configurations in the mcp/ or mcps/ directory and merge them.

        Args:
            config: Main formation configuration to merge into
            formation_dir: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation
            secrets_in_use: Set to accumulate secret names in use
            placeholder_registry: Registry to accumulate placeholder mappings
        """
        # Support both mcp/ and mcps/ directory names
        mcp_dir = formation_dir / "mcps"
        if not mcp_dir.exists():
            mcp_dir = formation_dir / "mcp"
        if not mcp_dir.exists():
            #  MCP_SERVER_CONNECTING
            return

        # Find all config files in mcp directory (support .afs, .yaml, .yml)
        mcp_files = []
        for pattern in ["*.afs", "*.yaml", "*.yml"]:
            mcp_files.extend(mcp_dir.glob(pattern))

        if not mcp_files:
            #  MCP_SERVER_CONNECTING
            return

        # Initialize MCP servers structure if not present
        if "mcp" not in config:
            config["mcp"] = {}
        if "servers" not in config["mcp"]:
            config["mcp"]["servers"] = []

        # Load and merge each MCP server configuration
        for mcp_file in sorted(mcp_files):
            try:
                #  MCP_SERVER_CONNECTING
                mcp_config = self.config_loader.load(str(mcp_file))

                # Validate that MCP config is a dictionary
                if not self._validate_config_is_dict(mcp_config, mcp_file.name, "MCP"):
                    continue

                mcp_config, mcp_secrets, mcp_placeholders = (
                    await self.config_loader.process_secrets(mcp_config, secrets_manager)
                )

                # Accumulate secrets from this MCP server
                if secrets_in_use is not None:
                    secrets_in_use.update(mcp_secrets)

                # Accumulate placeholders with adjusted paths for MCP server array
                if placeholder_registry is not None:
                    server_index = len(config["mcp"]["servers"])
                    for path, placeholder in mcp_placeholders.items():
                        # Adjust path to include MCP server array index
                        adjusted_path = (
                            f"mcp.servers[{server_index}].{path}"
                            if path
                            else f"mcp.servers[{server_index}]"
                        )
                        placeholder_registry[adjusted_path] = placeholder

                # Ensure MCP server has an ID (use filename if not specified)
                if "id" not in mcp_config:
                    mcp_config["id"] = mcp_file.stem

                # Check if MCP server is active (default to True)
                is_active = mcp_config.get("active", True)

                if is_active:
                    mcp_config["source"] = "formation"
                    config["mcp"]["servers"].append(mcp_config)

            except Exception as e:
                print(
                    f"⚠️  Warning: Failed to load MCP file '{mcp_file.name}': {type(e).__name__}: {str(e)}"
                )
                continue

        #  MCP_SERVER_CONNECTING
        #     f"✅ Discovered {len(config['mcp']['servers'])} MCP servers from mcp/ directory"
        # )

    async def _discover_and_merge_a2a_services(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None,
        secrets_in_use: Optional[set[str]] = None,
        placeholder_registry: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Discover A2A service configurations in the a2a/ directory and merge them.

        Args:
            config: Main formation configuration to merge into
            formation_dir: Path to the formation directory
            secrets_manager: SecretsManager instance for secret interpolation
            secrets_in_use: Set to accumulate secret names in use
            placeholder_registry: Registry to accumulate placeholder mappings
        """
        a2a_dir = formation_dir / "a2a"
        if not a2a_dir.exists():
            #  A2A_MESSAGE_SENT
            return

        # Find all config files in a2a directory (support .afs, .yaml, .yml)
        a2a_files = []
        for pattern in ["*.afs", "*.yaml", "*.yml"]:
            a2a_files.extend(a2a_dir.glob(pattern))

        if not a2a_files:
            #  A2A_MESSAGE_SENT
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
                #  A2A_MESSAGE_SENT
                a2a_config = self.config_loader.load(str(a2a_file))

                # Validate that A2A config is a dictionary
                if not self._validate_config_is_dict(a2a_config, a2a_file.name, "A2A"):
                    continue

                a2a_config, a2a_secrets, a2a_placeholders = (
                    await self.config_loader.process_secrets(a2a_config, secrets_manager)
                )

                # Accumulate secrets from this A2A service
                if secrets_in_use is not None:
                    secrets_in_use.update(a2a_secrets)

                # Accumulate placeholders with adjusted paths for A2A service array
                if placeholder_registry is not None:
                    service_index = len(config["a2a"]["outbound"]["services"])
                    for path, placeholder in a2a_placeholders.items():
                        # Adjust path to include A2A service array index
                        adjusted_path = (
                            f"a2a.outbound.services[{service_index}].{path}"
                            if path
                            else f"a2a.outbound.services[{service_index}]"
                        )
                        placeholder_registry[adjusted_path] = placeholder

                # Ensure A2A service has an ID (use filename if not specified)
                if "id" not in a2a_config:
                    a2a_config["id"] = a2a_file.stem

                config["a2a"]["outbound"]["services"].append(a2a_config)

            except Exception as e:
                print(
                    f"⚠️  Warning: Failed to load A2A file '{a2a_file.name}': {type(e).__name__}: {str(e)}"
                )
                continue

        #  A2A_MESSAGE_SENT
        #     f"✅ Discovered {len(config['a2a']['outbound']['services'])} "
        #     "A2A services from a2a/ directory"
        # )

    def _resolve_knowledge_paths(
        self, config: Dict[str, Any], formation_dir: str
    ) -> Dict[str, Any]:
        """
        Resolve and validate knowledge paths relative to formation directory.

        This method processes knowledge configuration paths and resolves them relative
        to the formation directory root. Absolute paths and parent directory traversal
        are rejected for security. Supports both sources as list of dicts with
        path/description and sources as list of strings.

        Args:
            config: Formation configuration
            formation_dir: Path to the formation directory

        Returns:
            Dict[str, Any]: Configuration with resolved knowledge paths

        Raises:
            ValueError: If any knowledge path is absolute or escapes formation directory
        """
        # Process overlord knowledge configuration
        if "overlord" in config and "knowledge" in config["overlord"]:
            knowledge_config = config["overlord"]["knowledge"]
            # Handle both dict format (enabled, sources) and list format (direct sources)
            if isinstance(knowledge_config, dict):
                if knowledge_config.get("enabled", False):
                    sources = knowledge_config.get("sources", [])
                    self._resolve_sources_paths(sources, formation_dir)
            elif isinstance(knowledge_config, list) and knowledge_config:
                # List format: treat as enabled sources directly
                self._resolve_sources_paths(knowledge_config, formation_dir)

        # Process agent knowledge configurations
        if "agents" in config:
            for agent in config["agents"]:
                if "knowledge" in agent:
                    knowledge_config = agent["knowledge"]
                    # Handle both dict format (enabled, sources) and list format (direct sources)
                    if isinstance(knowledge_config, dict):
                        if knowledge_config.get("enabled", False):
                            sources = knowledge_config.get("sources", [])
                            self._resolve_sources_paths(sources, formation_dir)
                    elif isinstance(knowledge_config, list) and knowledge_config:
                        # List format: treat as enabled sources directly
                        self._resolve_sources_paths(knowledge_config, formation_dir)

        return config

    def _resolve_sources_paths(self, sources: List[Any], formation_dir: str) -> None:
        """
        Resolve paths in knowledge sources list.

        Supports both sources as list of dicts with path/description
        and sources as list of strings.

        Args:
            sources: List of knowledge sources to resolve paths for
            formation_dir: Formation directory path
        """
        for source in sources:
            if isinstance(source, dict):
                if "path" in source:
                    source["path"] = self._resolve_single_path(source["path"], formation_dir)

    def _resolve_single_path(self, path: str, formation_dir: str) -> str:
        """
        Resolve and validate a knowledge path relative to formation directory.

        Security: All paths must be relative to formation root.
        Absolute paths and parent directory traversal are rejected.

        Args:
            path: Original path from configuration
            formation_dir: Formation directory path

        Returns:
            str: Resolved absolute path within formation directory

        Raises:
            ValueError: If path is absolute or escapes formation directory
        """
        # Reject absolute paths
        if os.path.isabs(path):
            from ...datatypes.observability import InitEventFormatter
            error_msg = (
                f"Absolute paths not allowed for knowledge sources: {path}\n"
                f"Use paths relative to formation directory root.\n"
                f"Example: 'knowledge/faq/' instead of '{path}'"
            )
            print(InitEventFormatter.format_fail(
                "Invalid knowledge path",
                error_msg
            ))
            raise ValueError(error_msg)

        # Reject parent directory traversal
        if '..' in path.split(os.sep):
            from ...datatypes.observability import InitEventFormatter
            error_msg = (
                f"Parent directory traversal not allowed: {path}\n"
                f"Keep knowledge within formation directory.\n"
                f"Recommended: Place files in knowledge/ subdirectory"
            )
            print(InitEventFormatter.format_fail(
                "Invalid knowledge path",
                error_msg
            ))
            raise ValueError(error_msg)

        # Resolve relative to formation root (not formation_dir/knowledge/)
        resolved_path = os.path.join(formation_dir, path)
        resolved_path = os.path.abspath(resolved_path)

        # Ensure resolved path is within formation directory
        formation_dir_abs = os.path.abspath(formation_dir)
        try:
            # Check if resolved path is within formation directory
            os.path.commonpath([resolved_path, formation_dir_abs])
            if not resolved_path.startswith(formation_dir_abs + os.sep) and resolved_path != formation_dir_abs:
                raise ValueError("Path escapes formation directory")
        except ValueError:
            from ...datatypes.observability import InitEventFormatter
            error_msg = (
                f"Knowledge path escapes formation directory: {path}\n"
                f"Resolved to: {resolved_path}\n"
                f"Must be within: {formation_dir_abs}\n"
                f"Keep all knowledge files within the formation directory."
            )
            print(InitEventFormatter.format_fail(
                "Invalid knowledge path",
                error_msg
            ))
            raise ValueError(error_msg)

        return resolved_path

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

        if path_obj.is_file() and path_obj.suffix in [".afs", ".yaml", ".yml"]:
            return "flattened"
        elif path_obj.is_dir():
            # Check if it has formation config and component directories
            # Priority: .afs > .yaml > .yml
            main_config = path_obj / "formation.afs"
            if not main_config.exists():
                main_config = path_obj / "formation.yaml"
            if not main_config.exists():
                main_config = path_obj / "formation.yml"
            if main_config.exists():
                # Look for component directories (support both mcp/ and mcps/)
                has_agents = (path_obj / "agents").exists()
                has_mcp = (path_obj / "mcp").exists() or (path_obj / "mcps").exists()
                has_a2a = (path_obj / "a2a").exists()

                if has_agents or has_mcp or has_a2a:
                    return "modular"
                else:
                    return "simple_directory"  # Directory with just formation.afs
            else:
                return "unknown"
        else:
            return "unknown"
