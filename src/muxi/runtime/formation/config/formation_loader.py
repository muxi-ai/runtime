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
# 2. Explicit Component Declaration
#    - Components (agents, MCPs, A2A) must be declared in the formation file
#    - Files in subdirectories are definitions, the formation file is the manifest
#    - String entries reference files by ID, dict entries are inline definitions
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
            print(
                f"⚠️  Warning: {config_type} file '{file_name}' contains {type(config).__name__} instead of dict - skipping"
            )  # noqa: E501
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
        config = self.config_loader.load(file_path)
        config, secrets_in_use, placeholder_registry = await self.config_loader.process_secrets(
            config, secrets_manager
        )

        # Resolve knowledge paths relative to formation file directory
        formation_dir = os.path.dirname(os.path.abspath(file_path))
        formation_dir_path = Path(formation_dir)

        # Resolve declared component references against subdirectory files
        await self._resolve_agents(
            config, formation_dir_path, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._resolve_mcp_servers(
            config, formation_dir_path, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._resolve_a2a_services(
            config, formation_dir_path, secrets_manager, secrets_in_use, placeholder_registry
        )

        # Resolve agent-level MCP references against formation-level MCP registry
        self._resolve_agent_mcp_references(config)

        config = self._resolve_knowledge_paths(config, formation_dir)

        return config, secrets_in_use, placeholder_registry

    async def _load_modular_formation(
        self, directory_path: str, secrets_manager: Optional[Any] = None
    ) -> tuple[Dict[str, Any], set[str], Dict[str, str]]:
        """
        Load a modular formation from a directory structure.

        Expected directory structure:
        formation-directory/
        ├── formation.afs         # Main formation configuration (the manifest)
        ├── agents/               # Agent definitions (loaded only if declared)
        │   ├── agent1.afs
        │   └── agent2.afs
        ├── mcp/                  # MCP server definitions (loaded only if declared)
        │   ├── tool1.afs
        │   └── tool2.afs
        ├── a2a/                  # A2A service definitions (loaded only if declared)
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
            raise FileNotFoundError(
                f"Main formation config (formation.afs/yaml/yml) not found in directory: {directory_path}"
            )

        main_config = self.config_loader.load(str(main_config_path))
        main_config, secrets_in_use, placeholder_registry = (
            await self.config_loader.process_secrets(main_config, secrets_manager)
        )

        # Resolve declared component references against subdirectory files
        await self._resolve_agents(
            main_config, formation_dir, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._resolve_mcp_servers(
            main_config, formation_dir, secrets_manager, secrets_in_use, placeholder_registry
        )
        await self._resolve_a2a_services(
            main_config, formation_dir, secrets_manager, secrets_in_use, placeholder_registry
        )

        # Resolve agent-level MCP references against formation-level MCP registry
        self._resolve_agent_mcp_references(main_config)

        # Resolve knowledge paths relative to formation directory
        main_config = self._resolve_knowledge_paths(main_config, str(formation_dir))

        return main_config, secrets_in_use, placeholder_registry

    async def _build_id_registry(
        self,
        component_dir: Path,
        component_type: str,
        secrets_manager: Optional[Any] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Scan a component directory and build an {id: config} registry.

        Reads all .afs/.yaml/.yml files, processes secrets, assigns IDs (filename
        stem as fallback), and returns the registry without loading anything into
        the formation config.

        Secrets and placeholder accumulation is deferred to _resolve_declared_list
        so only declared (actually loaded) components contribute.

        Args:
            component_dir: Path to the component directory (agents/, mcp/, a2a/)
            component_type: Human-readable type for warnings ("Agent", "MCP", "A2A")
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Dict mapping component ID to its full processed configuration
        """
        registry: Dict[str, Dict[str, Any]] = {}

        if not component_dir.exists():
            return registry

        files = []
        for pattern in ["*.afs", "*.yaml", "*.yml"]:
            files.extend(component_dir.glob(pattern))

        for config_file in sorted(files):
            try:
                file_config = self.config_loader.load(str(config_file))

                if not self._validate_config_is_dict(file_config, config_file.name, component_type):
                    continue

                file_config, file_secrets, file_placeholders = (
                    await self.config_loader.process_secrets(file_config, secrets_manager)
                )

                # Defer secrets_in_use and placeholder accumulation to resolution
                # time so only declared (actually loaded) components contribute.
                if file_secrets:
                    file_config["_raw_secrets"] = file_secrets
                if file_placeholders:
                    file_config["_raw_placeholders"] = file_placeholders

                if "id" not in file_config:
                    file_config["id"] = config_file.stem

                component_id = file_config["id"]
                if component_id in registry:
                    existing_file = registry[component_id].get("_source_file", "unknown")
                    raise ValueError(
                        f"Duplicate {component_type} ID '{component_id}' found in "
                        f"'{config_file.name}' (already defined in '{existing_file}')"
                    )
                file_config["_source_file"] = config_file.name
                registry[component_id] = file_config

            except Exception as e:
                print(
                    f"Warning: Failed to load {component_type} file "
                    f"'{config_file.name}': {type(e).__name__}: {str(e)}"
                )
                continue

        return registry

    def _resolve_declared_list(
        self,
        declared: List[Any],
        registry: Dict[str, Dict[str, Any]],
        component_type: str,
        dir_name: str,
        placeholder_registry: Optional[Dict[str, str]] = None,
        placeholder_prefix: str = "",
        existing_count: int = 0,
        secrets_in_use: Optional[set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Resolve a list of declared component references (string IDs or inline dicts).

        Args:
            declared: List of string IDs and/or inline dict definitions
            registry: ID -> config map built from directory scan
            component_type: Human-readable type for error messages
            dir_name: Directory name for error messages (e.g., "agents/")
            placeholder_registry: Registry to accumulate placeholder mappings
            placeholder_prefix: Prefix for placeholder paths (e.g., "agents", "mcp.servers")
            existing_count: Number of already-resolved items (for placeholder indexing)
            secrets_in_use: Set to accumulate secret names (only for declared items)

        Returns:
            List of resolved component configurations

        Raises:
            ValueError: If a string ID is not found in the registry
        """
        resolved: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        for item in declared:
            if isinstance(item, str):
                if item in seen_ids:
                    raise ValueError(
                        f"Duplicate {component_type} ID '{item}' in formation manifest."
                    )
                seen_ids.add(item)
                if item not in registry:
                    raise ValueError(
                        f"{component_type} '{item}' declared in formation but not found "
                        f"in {dir_name}/ directory. Available: {list(registry.keys())}"
                    )
                config = registry[item].copy()
                config["source"] = "formation"
                config.pop("_source_file", None)

                # Accumulate secrets only for declared (resolved) components
                raw_secrets = config.pop("_raw_secrets", None)
                if secrets_in_use is not None and raw_secrets:
                    secrets_in_use.update(raw_secrets)

                # Adjust placeholder paths now that we know the final index
                raw_placeholders = config.pop("_raw_placeholders", None)
                if placeholder_registry is not None and raw_placeholders:
                    idx = existing_count + len(resolved)
                    for path, placeholder in raw_placeholders.items():
                        adjusted_path = (
                            f"{placeholder_prefix}[{idx}].{path}"
                            if path
                            else f"{placeholder_prefix}[{idx}]"
                        )
                        placeholder_registry[adjusted_path] = placeholder

                resolved.append(config)

            elif isinstance(item, dict):
                item["source"] = "formation"
                resolved.append(item)

            else:
                raise ValueError(
                    f"Invalid entry in {dir_name}/ declaration: expected string ID or "
                    f"inline dict, got {type(item).__name__} ({item!r})"
                )

        return resolved

    async def _resolve_agents(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None,
        secrets_in_use: Optional[set[str]] = None,
        placeholder_registry: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Resolve declared agent references against agent files in agents/ directory.

        String entries in config["agents"] are resolved by ID against files in agents/.
        Dict entries (inline definitions) are kept as-is.
        If config["agents"] is not present, no agents are loaded.
        """
        if "agents" not in config:
            return

        agents = config["agents"]
        if not isinstance(agents, list):
            return

        # Separate inline dicts (already in config) from string references
        has_string_refs = any(isinstance(item, str) for item in agents)

        if has_string_refs:
            agents_dir = formation_dir / "agents"
            registry = await self._build_id_registry(
                agents_dir, "Agent", secrets_manager
            )
        else:
            registry = {}

        resolved = self._resolve_declared_list(
            agents,
            registry,
            "Agent",
            "agents",
            placeholder_registry,
            "agents",
            secrets_in_use=secrets_in_use,
        )
        config["agents"] = resolved

    async def _resolve_mcp_servers(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None,
        secrets_in_use: Optional[set[str]] = None,
        placeholder_registry: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Resolve declared MCP server references against files in mcp/ or mcps/ directory.

        String entries in config["mcp"]["servers"] are resolved by ID.
        Dict entries (inline definitions) are kept as-is.
        """
        if "mcp" not in config or "servers" not in config.get("mcp", {}):
            return

        servers = config["mcp"]["servers"]
        if not isinstance(servers, list):
            return

        has_string_refs = any(isinstance(item, str) for item in servers)

        if has_string_refs:
            # Support both mcp/ and mcps/ directory names
            mcp_dir = formation_dir / "mcps"
            if not mcp_dir.exists():
                mcp_dir = formation_dir / "mcp"
            registry = await self._build_id_registry(
                mcp_dir, "MCP", secrets_manager
            )
        else:
            registry = {}

        resolved = self._resolve_declared_list(
            servers,
            registry,
            "MCP server",
            "mcp",
            placeholder_registry,
            "mcp.servers",
            secrets_in_use=secrets_in_use,
        )
        config["mcp"]["servers"] = resolved

    async def _resolve_a2a_services(
        self,
        config: Dict[str, Any],
        formation_dir: Path,
        secrets_manager: Optional[Any] = None,
        secrets_in_use: Optional[set[str]] = None,
        placeholder_registry: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Resolve declared A2A service references against files in a2a/ directory.

        String entries in config["a2a"]["outbound"]["services"] are resolved by ID.
        Dict entries (inline definitions) are kept as-is.
        """
        a2a_config = config.get("a2a", {})
        outbound = a2a_config.get("outbound", {})
        if "services" not in outbound:
            return

        services = outbound["services"]
        if not isinstance(services, list):
            return

        has_string_refs = any(isinstance(item, str) for item in services)

        if has_string_refs:
            a2a_dir = formation_dir / "a2a"
            registry = await self._build_id_registry(
                a2a_dir, "A2A", secrets_manager
            )
        else:
            registry = {}

        resolved = self._resolve_declared_list(
            services,
            registry,
            "A2A service",
            "a2a",
            placeholder_registry,
            "a2a.outbound.services",
            secrets_in_use=secrets_in_use,
        )
        config["a2a"]["outbound"]["services"] = resolved

    def _resolve_agent_mcp_references(self, config: Dict[str, Any]) -> None:
        """
        Resolve agent-level mcp_servers string references against formation-level MCPs.

        After formation-level MCP servers are resolved, this method iterates through
        each agent's mcp_servers list and replaces string IDs with the full MCP config
        from the formation-level registry.
        """
        if "agents" not in config:
            return

        # Build formation-level MCP registry
        formation_mcps: Dict[str, Dict[str, Any]] = {}
        mcp_servers = config.get("mcp", {}).get("servers", [])
        for server in mcp_servers:
            if isinstance(server, dict) and "id" in server:
                formation_mcps[server["id"]] = server

        for agent in config["agents"]:
            if not isinstance(agent, dict):
                continue

            agent_mcps = agent.get("mcp_servers")
            if not agent_mcps or not isinstance(agent_mcps, list):
                continue

            resolved = []
            for item in agent_mcps:
                if isinstance(item, str):
                    if item not in formation_mcps:
                        agent_id = agent.get("id", "unknown")
                        raise ValueError(
                            f"Agent '{agent_id}' references MCP server '{item}' "
                            f"but it is not declared in formation mcp.servers. "
                            f"Available: {list(formation_mcps.keys())}"
                        )
                    resolved.append(formation_mcps[item].copy())
                elif isinstance(item, dict):
                    resolved.append(item)
                else:
                    agent_id = agent.get("id", "unknown")
                    raise ValueError(
                        f"Agent '{agent_id}' mcp_servers: expected string ID or "
                        f"inline dict, got {type(item).__name__} ({item!r})"
                    )

            agent["mcp_servers"] = resolved

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
            print(InitEventFormatter.format_fail("Invalid knowledge path", error_msg))
            raise ValueError(error_msg)

        # Reject parent directory traversal
        if ".." in path.split(os.sep):
            from ...datatypes.observability import InitEventFormatter

            error_msg = (
                f"Parent directory traversal not allowed: {path}\n"
                f"Keep knowledge within formation directory.\n"
                f"Recommended: Place files in knowledge/ subdirectory"
            )
            print(InitEventFormatter.format_fail("Invalid knowledge path", error_msg))
            raise ValueError(error_msg)

        # Resolve relative to formation root (not formation_dir/knowledge/)
        resolved_path = os.path.join(formation_dir, path)
        resolved_path = os.path.abspath(resolved_path)

        # Ensure resolved path is within formation directory
        formation_dir_abs = os.path.abspath(formation_dir)
        try:
            # Check if resolved path is within formation directory
            os.path.commonpath([resolved_path, formation_dir_abs])
            if (
                not resolved_path.startswith(formation_dir_abs + os.sep)
                and resolved_path != formation_dir_abs
            ):
                raise ValueError("Path escapes formation directory")
        except ValueError:
            from ...datatypes.observability import InitEventFormatter

            error_msg = (
                f"Knowledge path escapes formation directory: {path}\n"
                f"Resolved to: {resolved_path}\n"
                f"Must be within: {formation_dir_abs}\n"
                f"Keep all knowledge files within the formation directory."
            )
            print(InitEventFormatter.format_fail("Invalid knowledge path", error_msg))
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
