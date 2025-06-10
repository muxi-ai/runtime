"""
Formation configuration validation utilities.

This module provides tools for validating formation configurations,
detecting common issues, and ensuring configurations are well-formed.
"""

import logging
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import yaml
import json

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when formation validation fails."""

    pass


class ValidationResult:
    """
    Result of formation validation.

    Contains information about validation status, errors, warnings,
    and suggestions for fixing issues.
    """

    def __init__(self):
        self.is_valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.suggestions: List[str] = []
        self.context: Dict[str, Any] = {}

    def add_error(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Add a validation error."""
        self.is_valid = False
        self.errors.append(message)
        if context:
            self.context.update(context)

    def add_warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Add a validation warning."""
        self.warnings.append(message)
        if context:
            self.context.update(context)

    def add_suggestion(self, message: str):
        """Add a suggestion for improvement."""
        self.suggestions.append(message)

    def summary(self) -> str:
        """Get a summary of validation results."""
        if self.is_valid and not self.warnings:
            return "✅ Formation configuration is valid"

        parts = []
        if not self.is_valid:
            parts.append(f"❌ {len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"⚠️  {len(self.warnings)} warning(s)")
        if self.suggestions:
            parts.append(f"💡 {len(self.suggestions)} suggestion(s)")

        return " | ".join(parts)

    def detailed_report(self) -> str:
        """Get a detailed validation report."""
        lines = [self.summary(), ""]

        if self.errors:
            lines.append("ERRORS:")
            for i, error in enumerate(self.errors, 1):
                lines.append(f"  {i}. {error}")
            lines.append("")

        if self.warnings:
            lines.append("WARNINGS:")
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"  {i}. {warning}")
            lines.append("")

        if self.suggestions:
            lines.append("SUGGESTIONS:")
            for i, suggestion in enumerate(self.suggestions, 1):
                lines.append(f"  {i}. {suggestion}")
            lines.append("")

        return "\n".join(lines)


class FormationValidator:
    """
    Comprehensive formation configuration validator.

    Validates both flattened formation files and modular formation directories,
    checking for structural issues, missing required fields, invalid references,
    and providing suggestions for improvements.
    """

    REQUIRED_FORMATION_FIELDS = ["schema", "id", "description"]
    REQUIRED_AGENT_FIELDS = ["schema", "id", "name", "description"]
    REQUIRED_MODEL_FIELDS = ["provider"]
    REQUIRED_MCP_SERVER_FIELDS = ["schema", "id", "description", "type"]
    REQUIRED_A2A_SERVICE_FIELDS = ["schema", "id", "name", "description", "url"]

    def __init__(self):
        self.result = ValidationResult()

    def validate(
        self, formation_path: Union[str, Path], secrets_manager: Optional[Any] = None
    ) -> ValidationResult:
        """
        Validate a formation configuration.

        Args:
            formation_path: Path to formation file or directory
            secrets_manager: Optional secrets manager for credential validation

        Returns:
            ValidationResult: Comprehensive validation results
        """
        self.result = ValidationResult()
        formation_path = Path(formation_path)

        try:
            # Check if path exists
            if not formation_path.exists():
                self.result.add_error(f"Formation path does not exist: {formation_path}")
                return self.result

            # Determine formation type and validate accordingly
            if formation_path.is_file():
                # Check if this is an agent file based on content
                if self._is_agent_file(formation_path):
                    self._validate_agent_file(formation_path)
                else:
                    self._validate_flattened_formation(formation_path, secrets_manager)
            elif formation_path.is_dir():
                self._validate_modular_formation(formation_path, secrets_manager)
            else:
                self.result.add_error(
                    f"Formation path is neither file nor directory: {formation_path}"
                )

        except Exception as e:
            self.result.add_error(f"Validation failed with exception: {str(e)}")

        return self.result

    def _validate_flattened_formation(
        self, file_path: Path, secrets_manager: Optional[Any]
    ) -> None:
        """Validate a flattened formation file."""
        try:
            # Load and parse the file
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix.lower() in [".yaml", ".yml"]:
                    config = yaml.safe_load(f)
                elif file_path.suffix.lower() == ".json":
                    config = json.load(f)
                else:
                    self.result.add_error(f"Unsupported file format: {file_path.suffix}")
                    return

            if not isinstance(config, dict):
                self.result.add_error("Formation configuration must be a dictionary")
                return

            # Validate basic structure
            self._validate_formation_structure(config)

            # Validate agents
            if "agents" in config:
                self._validate_agents(config["agents"])

            # Validate MCP servers
            if "mcp" in config:
                self._validate_mcp_config(config["mcp"])

            # Validate A2A configuration
            if "a2a" in config:
                self._validate_a2a_config(config["a2a"])

            # Validate knowledge configuration
            if "knowledge" in config:
                self._validate_knowledge_config(config["knowledge"], file_path.parent)

        except yaml.YAMLError as e:
            self.result.add_error(f"YAML parsing error: {str(e)}")
        except json.JSONDecodeError as e:
            self.result.add_error(f"JSON parsing error: {str(e)}")
        except Exception as e:
            self.result.add_error(f"Error validating flattened formation: {str(e)}")

    def _validate_modular_formation(self, dir_path: Path, secrets_manager: Optional[Any]) -> None:
        """Validate a modular formation directory."""
        try:
            # Check for formation.yaml
            formation_file = dir_path / "formation.yaml"
            if not formation_file.exists():
                formation_file = dir_path / "formation.yml"

            if not formation_file.exists():
                self.result.add_error("Missing formation.yaml file in modular formation")
                return

            # Load main formation config
            with open(formation_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                self.result.add_error("Formation configuration must be a dictionary")
                return

            # Validate basic structure
            self._validate_formation_structure(config)

            # Validate component directories
            self._validate_agents_directory(dir_path / "agents")
            self._validate_mcp_directory(dir_path / "mcp")
            self._validate_a2a_directory(dir_path / "a2a")
            self._validate_knowledge_directory(dir_path / "knowledge")

        except Exception as e:
            self.result.add_error(f"Error validating modular formation: {str(e)}")

    def _is_agent_file(self, file_path: Path) -> bool:
        """Check if a file is an agent configuration file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix.lower() in [".yaml", ".yml"]:
                    config = yaml.safe_load(f)
                elif file_path.suffix.lower() == ".json":
                    config = json.load(f)
                else:
                    return False

            if not isinstance(config, dict):
                return False

            # Check for formation-specific indicators first
            formation_fields = ["agents", "overlord", "mcp", "memory", "logging", "auth"]
            has_formation_fields = any(field in config for field in formation_fields)

            # If it has formation fields, it's definitely a formation
            if has_formation_fields:
                return False

            # Check for agent-specific fields that are NOT also formation fields
            # Note: 'system_message' can be used in both formations and agents
            agent_fields = ["name", "llm_models", "role", "specialties"]
            has_agent_specific_fields = any(field in config for field in agent_fields)

            # Must have agent-specific fields to be considered an agent file
            return has_agent_specific_fields

        except Exception:
            return False

    def _validate_agent_file(self, file_path: Path) -> None:
        """Validate a standalone agent configuration file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix.lower() in [".yaml", ".yml"]:
                    config = yaml.safe_load(f)
                elif file_path.suffix.lower() == ".json":
                    config = json.load(f)
                else:
                    self.result.add_error(f"Unsupported file format: {file_path.suffix}")
                    return

            if not isinstance(config, dict):
                self.result.add_error("Agent configuration must be a dictionary")
                return

            # Validate as a single agent
            self._validate_agents([config])

        except yaml.YAMLError as e:
            self.result.add_error(f"YAML parsing error: {str(e)}")
        except json.JSONDecodeError as e:
            self.result.add_error(f"JSON parsing error: {str(e)}")
        except Exception as e:
            self.result.add_error(f"Error validating agent file: {str(e)}")

    def _validate_formation_structure(self, config: Dict[str, Any]) -> None:
        """Validate basic formation structure."""
        # Check required fields
        for field in self.REQUIRED_FORMATION_FIELDS:
            if field not in config:
                self.result.add_error(f"Missing required formation field: {field}")

        # Validate schema
        if "schema" in config:
            schema = config["schema"]
            if not isinstance(schema, str) or not schema.strip():
                self.result.add_error("Formation schema must be a non-empty string")

        # Validate id
        if "id" in config:
            formation_id = config["id"]
            if not isinstance(formation_id, str) or not formation_id.strip():
                self.result.add_error("Formation id must be a non-empty string")

        # Validate description
        if "description" in config:
            description = config["description"]
            if not isinstance(description, str) or not description.strip():
                self.result.add_error("Formation description must be a non-empty string")

        # Validate version
        if "version" in config:
            version = config["version"]
            if not isinstance(version, str) or not version.strip():
                self.result.add_error("Formation version must be a non-empty string")

        # Allow any additional fields users might want to add for their own purposes

        # Validate LLM configuration
        if "llm" in config:
            self._validate_llm_config(config["llm"])

        # Validate memory configuration
        if "memory" in config:
            self._validate_memory_config(config["memory"])

        # Validate logging configuration
        if "logging" in config:
            self._validate_logging_config(config["logging"])

        # Validate overlord configuration
        if "overlord" in config:
            self._validate_overlord_config(config["overlord"])

        # Validate async configuration
        if "async" in config:
            self._validate_async_config(config["async"])

    def _validate_agents(self, agents_config: List[Dict[str, Any]]) -> None:
        """Validate agents configuration."""
        if not isinstance(agents_config, list):
            self.result.add_error("Agents configuration must be a list")
            return

        agent_ids = set()
        for i, agent_config in enumerate(agents_config):
            if not isinstance(agent_config, dict):
                self.result.add_error(f"Agent {i} configuration must be a dictionary")
                continue

            # Check required fields
            for field in self.REQUIRED_AGENT_FIELDS:
                if field not in agent_config:
                    self.result.add_error(f"Agent {i} missing required field: {field}")

            # Validate agent id uniqueness
            agent_id = agent_config.get("id")
            if agent_id:
                if agent_id in agent_ids:
                    self.result.add_error(f"Duplicate agent id: {agent_id}")
                agent_ids.add(agent_id)

            # Allow any additional fields users might want to add for their own purposes

            # Validate LLM models configuration (new schema)
            if "llm_models" in agent_config:
                self._validate_llm_models(agent_config["llm_models"])

            # Legacy model validation (for backward compatibility)
            if "model" in agent_config:
                # Legacy 'model' field is still supported for compatibility
                pass

            # Validate knowledge configuration
            if "knowledge" in agent_config:
                self._validate_agent_knowledge_config(agent_config["knowledge"])

            # Validate agent-level MCP servers
            if "mcp_servers" in agent_config:
                self._validate_agent_mcp_servers(agent_config["mcp_servers"], agent_id or i)

    def _validate_model_config(self, model_config: Dict[str, Any], context: str) -> None:
        """Validate model configuration."""
        if not isinstance(model_config, dict):
            self.result.add_error(f"{context} model configuration must be a dictionary")
            return

        # Check required fields
        for field in self.REQUIRED_MODEL_FIELDS:
            if field not in model_config:
                self.result.add_error(f"{context} model missing required field: {field}")

        # Allow any provider users want to use

    def _validate_mcp_config(self, mcp_config: Dict[str, Any]) -> None:
        """Validate MCP configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(mcp_config, dict):
            self.result.add_error("MCP configuration must be a dictionary")
            return

        # Validate servers
        if "servers" in mcp_config:
            servers = mcp_config["servers"]
            if not isinstance(servers, list):
                self.result.add_error("MCP servers must be a list")
                return

            server_ids = set()
            for i, server_config in enumerate(servers):
                if not isinstance(server_config, dict):
                    self.result.add_error(f"MCP server {i} configuration must be a dictionary")
                    continue

                self._validate_single_mcp_server(server_config, i, server_ids)

    def _validate_single_mcp_server(
        self, server_config: Dict[str, Any], index: int, server_ids: set
    ) -> None:
        """Validate a single MCP server configuration according to SCHEMA_GUIDE.md."""
        # Check required fields
        for field in self.REQUIRED_MCP_SERVER_FIELDS:
            if field not in server_config:
                self.result.add_error(f"MCP server {index} missing required field: {field}")

        # Validate server_id uniqueness
        server_id = server_config.get("id")
        if server_id:
            if server_id in server_ids:
                self.result.add_error(f"Duplicate MCP server id: {server_id}")
            server_ids.add(server_id)

        # Validate optional metadata fields
        self._validate_mcp_metadata_fields(server_config, server_id or index)

        # Validate type-specific configuration
        server_type = server_config.get("type")
        if server_type == "http":
            self._validate_http_mcp_server(server_config, server_id or index)
        elif server_type == "command":
            self._validate_command_mcp_server(server_config, server_id or index)
        elif server_type:
            self.result.add_error(
                f"MCP server {server_id or index} has invalid type '{server_type}'. "
                "Valid types are: 'http', 'command'"
            )

        # Validate authentication configuration
        if "auth" in server_config:
            self._validate_mcp_auth_config(server_config["auth"], server_id or index)

        # Check for legacy fields
        if "url" in server_config:
            # Legacy 'url' field is still supported for compatibility
            pass

    def _validate_mcp_metadata_fields(
        self, server_config: Dict[str, Any], server_identifier: Union[str, int]
    ) -> None:
        """Validate optional MCP server metadata fields."""
        # Validate active field
        if "active" in server_config:
            if not isinstance(server_config["active"], bool):
                self.result.add_error(
                    f"MCP server {server_identifier} 'active' field must be a boolean"
                )

        # Validate version field
        if "version" in server_config:
            if not isinstance(server_config["version"], str):
                self.result.add_error(
                    f"MCP server {server_identifier} 'version' field must be a string"
                )

        # Validate author field
        if "author" in server_config:
            if not isinstance(server_config["author"], str):
                self.result.add_error(
                    f"MCP server {server_identifier} 'author' field must be a string"
                )

        # Validate url field (different from endpoint)
        if "url" in server_config and server_config["url"] != server_config.get("endpoint"):
            if not isinstance(server_config["url"], str):
                self.result.add_error(
                    f"MCP server {server_identifier} 'url' field must be a string"
                )

        # Validate license field
        if "license" in server_config:
            if not isinstance(server_config["license"], str):
                self.result.add_error(
                    f"MCP server {server_identifier} 'license' field must be a string"
                )

    def _validate_http_mcp_server(
        self, server_config: Dict[str, Any], server_identifier: Union[str, int]
    ) -> None:
        """Validate HTTP MCP server specific configuration."""
        # Endpoint is required for HTTP servers
        if "endpoint" not in server_config:
            self.result.add_error(f"HTTP MCP server {server_identifier} must have 'endpoint' field")
        else:
            endpoint = server_config["endpoint"]
            if not isinstance(endpoint, str):
                self.result.add_error(
                    f"HTTP MCP server {server_identifier} 'endpoint' must be a string"
                )
            elif not (endpoint.startswith("http://") or endpoint.startswith("https://")):
                self.result.add_error(
                    f"HTTP MCP server {server_identifier} 'endpoint' must start with "
                    "http:// or https://"
                )

        # Validate optional timeout and retry settings
        if "timeout_seconds" in server_config:
            timeout = server_config["timeout_seconds"]
            if not isinstance(timeout, int) or timeout <= 0:
                self.result.add_error(
                    f"HTTP MCP server {server_identifier} 'timeout_seconds' "
                    "must be a positive integer"
                )

        if "retry_attempts" in server_config:
            retries = server_config["retry_attempts"]
            if not isinstance(retries, int) or retries < 0:
                self.result.add_error(
                    f"HTTP MCP server {server_identifier} 'retry_attempts' "
                    "must be a non-negative integer"
                )

    def _validate_command_mcp_server(
        self, server_config: Dict[str, Any], server_identifier: Union[str, int]
    ) -> None:
        """Validate command MCP server specific configuration."""
        # Command is required for command servers
        if "command" not in server_config:
            self.result.add_error(
                f"Command MCP server {server_identifier} must have 'command' field"
            )
        else:
            command = server_config["command"]
            if not isinstance(command, str):
                self.result.add_error(
                    f"Command MCP server {server_identifier} 'command' must be a string"
                )

        # Validate optional command configuration
        if "args" in server_config:
            args = server_config["args"]
            if not isinstance(args, list):
                self.result.add_error(
                    f"Command MCP server {server_identifier} 'args' must be a list"
                )
            else:
                for i, arg in enumerate(args):
                    if not isinstance(arg, str):
                        self.result.add_error(
                            f"Command MCP server {server_identifier} arg {i} must be a string"
                        )

        if "working_directory" in server_config:
            wd = server_config["working_directory"]
            if not isinstance(wd, str):
                self.result.add_error(
                    f"Command MCP server {server_identifier} 'working_directory' "
                    "must be a string"
                )

        if "install" in server_config:
            install = server_config["install"]
            if not isinstance(install, str):
                self.result.add_error(
                    f"Command MCP server {server_identifier} 'install' must be a string"
                )

        if "timeout_seconds" in server_config:
            timeout = server_config["timeout_seconds"]
            if not isinstance(timeout, int) or timeout <= 0:
                self.result.add_error(
                    f"Command MCP server {server_identifier} 'timeout_seconds' "
                    "must be a positive integer"
                )

        if "max_retries" in server_config:
            retries = server_config["max_retries"]
            if not isinstance(retries, int) or retries < 0:
                self.result.add_error(
                    f"Command MCP server {server_identifier} 'max_retries' "
                    "must be a non-negative integer"
                )

        # Validate environment variables
        if "env" in server_config:
            env = server_config["env"]
            if not isinstance(env, dict):
                self.result.add_error(
                    f"Command MCP server {server_identifier} 'env' must be a dictionary"
                )
            else:
                for key, value in env.items():
                    if not isinstance(key, str):
                        self.result.add_error(
                            f"Command MCP server {server_identifier} env key must be a string"
                        )
                    if not isinstance(value, str):
                        self.result.add_error(
                            f"Command MCP server {server_identifier} env value must be a string"
                        )

    def _validate_mcp_auth_config(
        self, auth_config: Dict[str, Any], server_identifier: Union[str, int]
    ) -> None:
        """Validate MCP server authentication configuration."""
        if not isinstance(auth_config, dict):
            self.result.add_error(
                f"MCP server {server_identifier} auth configuration must be a dictionary"
            )
            return

        # Validate auth type
        auth_type = auth_config.get("type", "none")
        valid_auth_types = ["none", "api_key", "bearer", "basic"]
        if auth_type not in valid_auth_types:
            self.result.add_error(
                f"MCP server {server_identifier} invalid auth type '{auth_type}'. "
                f"Valid types: {', '.join(valid_auth_types)}"
            )
            return

        # Validate type-specific auth fields
        if auth_type == "api_key":
            if "key" not in auth_config:
                self.result.add_error(
                    f"MCP server {server_identifier} api_key auth requires 'key' field"
                )
            if "header" in auth_config and not isinstance(auth_config["header"], str):
                self.result.add_error(
                    f"MCP server {server_identifier} auth 'header' must be a string"
                )

        elif auth_type == "bearer":
            if "token" not in auth_config:
                self.result.add_error(
                    f"MCP server {server_identifier} bearer auth requires 'token' field"
                )

        elif auth_type == "basic":
            if "username" not in auth_config:
                self.result.add_error(
                    f"MCP server {server_identifier} basic auth requires 'username' field"
                )
            if "password" not in auth_config:
                self.result.add_error(
                    f"MCP server {server_identifier} basic auth requires 'password' field"
                )

    def _validate_a2a_config(self, a2a_config: Dict[str, Any]) -> None:
        """Validate A2A configuration."""
        if not isinstance(a2a_config, dict):
            self.result.add_error("A2A configuration must be a dictionary")
            return

        # Validate inbound configuration
        if "inbound" in a2a_config:
            inbound = a2a_config["inbound"]
            if not isinstance(inbound, dict):
                self.result.add_error("A2A inbound configuration must be a dictionary")

        # Validate outbound configuration
        if "outbound" in a2a_config:
            outbound = a2a_config["outbound"]
            if not isinstance(outbound, dict):
                self.result.add_error("A2A outbound configuration must be a dictionary")
                return

            # Validate services
            if "services" in outbound:
                services = outbound["services"]
                if not isinstance(services, list):
                    self.result.add_error("A2A outbound services must be a list")
                    return

                service_ids = set()
                for i, service_config in enumerate(services):
                    if not isinstance(service_config, dict):
                        self.result.add_error(f"A2A service {i} configuration must be a dictionary")
                        continue

                    # Check for service id and duplicates
                    service_id = service_config.get("id")
                    if service_id:
                        if service_id in service_ids:
                            self.result.add_error(f"Duplicate A2A service id: {service_id}")
                        service_ids.add(service_id)

                    # Validate outbound service auth configuration (simplified format)
                    service_identifier = f"formation a2a.outbound.services[{i}]"
                    self._validate_outbound_service_auth_config(service_config, service_identifier)

    def _validate_knowledge_config(self, knowledge_config: Dict[str, Any], base_path: Path) -> None:
        """Validate knowledge configuration."""
        if not isinstance(knowledge_config, dict):
            self.result.add_error("Knowledge configuration must be a dictionary")
            return

        # Validate sources
        if "sources" in knowledge_config:
            sources = knowledge_config["sources"]
            if not isinstance(sources, list):
                self.result.add_error("Knowledge sources must be a list")
                return

            for i, source in enumerate(sources):
                if not isinstance(source, dict):
                    self.result.add_error(f"Knowledge source {i} must be a dictionary")
                    continue

                # Check for path
                path = source.get("path")
                if not path:
                    self.result.add_error(f"Knowledge source {i} missing 'path' field")
                    continue

                # Validate path exists (resolve relative to base_path)
                if not Path(path).is_absolute():
                    full_path = base_path / path
                else:
                    full_path = Path(path)

                if not full_path.exists():
                    self.result.add_warning(f"Knowledge source path does not exist: {path}")

    def _validate_agent_knowledge_config(self, knowledge_config: Dict[str, Any]) -> None:
        """Validate agent-level knowledge configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(knowledge_config, dict):
            self.result.add_error("Agent knowledge configuration must be a dictionary")
            return

        # Validate enabled field
        if "enabled" in knowledge_config:
            enabled = knowledge_config["enabled"]
            if not isinstance(enabled, bool):
                self.result.add_error("Agent knowledge 'enabled' must be a boolean")

        # Validate sources array
        if "sources" in knowledge_config:
            sources = knowledge_config["sources"]
            if not isinstance(sources, list):
                self.result.add_error("Agent knowledge 'sources' must be a list")
                return

            for i, source in enumerate(sources):
                if not isinstance(source, dict):
                    self.result.add_error(f"Agent knowledge source {i} must be a dictionary")
                    continue

                # Validate required fields for each source
                if "path" not in source:
                    self.result.add_error(
                        f"Agent knowledge source {i} missing required field: 'path'"
                    )
                else:
                    path = source["path"]
                    if not isinstance(path, str):
                        self.result.add_error(f"Agent knowledge source {i} 'path' must be a string")
                    elif not path.strip():
                        self.result.add_error(f"Agent knowledge source {i} 'path' cannot be empty")

                if "description" not in source:
                    self.result.add_error(
                        f"Agent knowledge source {i} missing required field: 'description'"
                    )
                else:
                    description = source["description"]
                    if not isinstance(description, str):
                        self.result.add_error(
                            f"Agent knowledge source {i} 'description' must be a string"
                        )
                    elif not description.strip():
                        self.result.add_error(
                            f"Agent knowledge source {i} 'description' cannot be empty"
                        )

        # Allow any additional fields users might want to add for knowledge configuration

    def _validate_agent_mcp_servers(
        self, mcp_servers: List[Dict[str, Any]], agent_identifier: Union[str, int]
    ) -> None:
        """Validate agent-level MCP servers configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(mcp_servers, list):
            self.result.add_error(f"Agent {agent_identifier} mcp_servers must be a list")
            return

        server_ids = set()
        for i, server_config in enumerate(mcp_servers):
            if not isinstance(server_config, dict):
                self.result.add_error(
                    f"Agent {agent_identifier} MCP server {i} configuration must be a dictionary"
                )
                continue

            # Check required fields for agent-level MCP servers
            required_fields = ["id", "description", "type"]
            for field in required_fields:
                if field not in server_config:
                    self.result.add_error(
                        f"Agent {agent_identifier} MCP server {i} missing required field: {field}"
                    )

            # Validate server_id uniqueness within this agent
            server_id = server_config.get("id")
            if server_id:
                if server_id in server_ids:
                    self.result.add_error(
                        f"Agent {agent_identifier} has duplicate MCP server id: {server_id}"
                    )
                server_ids.add(server_id)

            # Validate type-specific configuration
            self._validate_agent_mcp_server_type(server_config, agent_identifier, server_id or i)

            # Validate optional agent-specific overrides
            self._validate_agent_mcp_overrides(server_config, agent_identifier, server_id or i)

    def _validate_agent_mcp_server_type(
        self,
        server_config: Dict[str, Any],
        agent_identifier: Union[str, int],
        server_identifier: Union[str, int],
    ) -> None:
        """Validate type-specific configuration for agent-level MCP servers."""
        server_type = server_config.get("type")

        if server_type == "http":
            # HTTP servers require endpoint
            if "endpoint" not in server_config:
                self.result.add_error(
                    f"Agent {agent_identifier} HTTP MCP server {server_identifier} "
                    "must have 'endpoint' field"
                )
            else:
                endpoint = server_config["endpoint"]
                if not isinstance(endpoint, str):
                    self.result.add_error(
                        f"Agent {agent_identifier} HTTP MCP server {server_identifier} "
                        "'endpoint' must be a string"
                    )
                elif not (endpoint.startswith("http://") or endpoint.startswith("https://")):
                    self.result.add_error(
                        f"Agent {agent_identifier} HTTP MCP server {server_identifier} "
                        "'endpoint' must start with http:// or https://"
                    )

        elif server_type == "command":
            # Command servers require command
            if "command" not in server_config:
                self.result.add_error(
                    f"Agent {agent_identifier} command MCP server {server_identifier} "
                    "must have 'command' field"
                )
            else:
                command = server_config["command"]
                if not isinstance(command, (str, list)):
                    self.result.add_error(
                        f"Agent {agent_identifier} command MCP server {server_identifier} "
                        "'command' must be a string or list of strings"
                    )

        elif server_type:
            self.result.add_error(
                f"Agent {agent_identifier} MCP server {server_identifier} has invalid type "
                f"'{server_type}'. Valid types are: 'http', 'command'"
            )

    def _validate_agent_mcp_overrides(
        self,
        server_config: Dict[str, Any],
        agent_identifier: Union[str, int],
        server_identifier: Union[str, int],
    ) -> None:
        """Validate agent-specific MCP server override fields."""
        # Validate retry_attempts override
        if "retry_attempts" in server_config:
            retry_attempts = server_config["retry_attempts"]
            if not isinstance(retry_attempts, int) or retry_attempts < 0:
                self.result.add_error(
                    f"Agent {agent_identifier} MCP server {server_identifier} "
                    "'retry_attempts' must be a non-negative integer"
                )

        # Validate timeout_seconds override
        if "timeout_seconds" in server_config:
            timeout_seconds = server_config["timeout_seconds"]
            if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
                self.result.add_error(
                    f"Agent {agent_identifier} MCP server {server_identifier} "
                    "'timeout_seconds' must be a positive integer"
                )

        # Validate active override
        if "active" in server_config:
            active = server_config["active"]
            if not isinstance(active, bool):
                self.result.add_error(
                    f"Agent {agent_identifier} MCP server {server_identifier} "
                    "'active' must be a boolean"
                )

        # Validate authentication configuration
        if "auth" in server_config:
            self._validate_mcp_auth_config(
                server_config["auth"], f"Agent {agent_identifier} MCP server {server_identifier}"
            )

    def _validate_agents_directory(self, agents_dir: Path) -> None:
        """Validate agents directory in modular formation."""
        if not agents_dir.exists():
            self.result.add_suggestion(
                "Consider adding 'agents/' directory for agent configurations"
            )
            return

        if not agents_dir.is_dir():
            self.result.add_error("'agents' must be a directory")
            return

        # Check for agent files
        agent_files = list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml"))
        if not agent_files:
            self.result.add_warning("No agent configuration files found in agents/ directory")

        # Validate each agent file
        for agent_file in agent_files:
            try:
                with open(agent_file, "r", encoding="utf-8") as f:
                    agent_config = yaml.safe_load(f)

                if isinstance(agent_config, dict):
                    # Set agent id from filename if not provided
                    if "id" not in agent_config:
                        agent_config["id"] = agent_file.stem

                    self._validate_agents([agent_config])
                else:
                    self.result.add_error(f"Agent file {agent_file.name} must contain a dictionary")

            except Exception as e:
                self.result.add_error(f"Error parsing agent file {agent_file.name}: {str(e)}")

    def _validate_mcp_directory(self, mcp_dir: Path) -> None:
        """Validate MCP directory in modular formation."""
        if not mcp_dir.exists():
            self.result.add_suggestion(
                "Consider adding 'mcp/' directory for MCP server configurations"
            )
            return

        if not mcp_dir.is_dir():
            self.result.add_error("'mcp' must be a directory")
            return

        # Check for MCP files
        mcp_files = list(mcp_dir.glob("*.yaml")) + list(mcp_dir.glob("*.yml"))
        if not mcp_files:
            self.result.add_warning("No MCP configuration files found in mcp/ directory")

        # Validate each MCP file
        for mcp_file in mcp_files:
            try:
                with open(mcp_file, "r", encoding="utf-8") as f:
                    mcp_config = yaml.safe_load(f)

                if isinstance(mcp_config, dict):
                    # Set id from filename if not provided
                    if "id" not in mcp_config:
                        mcp_config["id"] = mcp_file.stem

                    # Create servers list structure for validation
                    servers_config = {"servers": [mcp_config]}
                    self._validate_mcp_config(servers_config)
                else:
                    self.result.add_error(f"MCP file {mcp_file.name} must contain a dictionary")

            except Exception as e:
                self.result.add_error(f"Error parsing MCP file {mcp_file.name}: {str(e)}")

    def _validate_a2a_directory(self, a2a_dir: Path) -> None:
        """Validate A2A directory in modular formation."""
        if not a2a_dir.exists():
            self.result.add_suggestion("Consider adding 'a2a/' directory for A2A configurations")
            return

        if not a2a_dir.is_dir():
            self.result.add_error("'a2a' must be a directory")
            return

        # Check for A2A files
        a2a_files = list(a2a_dir.glob("*.yaml")) + list(a2a_dir.glob("*.yml"))
        if not a2a_files:
            self.result.add_warning("No A2A configuration files found in a2a/ directory")
            return

        # Validate each A2A service file
        service_ids = set()
        for a2a_file in a2a_files:
            try:
                with open(a2a_file, "r", encoding="utf-8") as f:
                    a2a_config = yaml.safe_load(f)

                if not isinstance(a2a_config, dict):
                    self.result.add_error(
                        f"A2A service file {a2a_file.name} must contain a dictionary"
                    )
                    continue

                # Validate A2A service configuration
                self._validate_a2a_service_config(a2a_config, a2a_file.name)

                # Check for duplicate service IDs
                service_id = a2a_config.get("id")
                if service_id:
                    if service_id in service_ids:
                        self.result.add_error(f"Duplicate A2A service id: {service_id}")
                    service_ids.add(service_id)

            except yaml.YAMLError as e:
                self.result.add_error(f"YAML parsing error in {a2a_file.name}: {str(e)}")
            except Exception as e:
                self.result.add_error(f"Error validating A2A service {a2a_file.name}: {str(e)}")

    def _validate_knowledge_directory(self, knowledge_dir: Path) -> None:
        """Validate knowledge directory in modular formation."""
        if not knowledge_dir.exists():
            self.result.add_suggestion("Consider adding 'knowledge/' directory for knowledge files")
            return

        if not knowledge_dir.is_dir():
            self.result.add_error("'knowledge' must be a directory")
            return

        # Check for knowledge files
        knowledge_files = (
            list(knowledge_dir.glob("*.txt"))
            + list(knowledge_dir.glob("*.md"))
            + list(knowledge_dir.glob("*.markdown"))
        )
        if not knowledge_files:
            self.result.add_warning("No knowledge files found in knowledge/ directory")

    def _validate_llm_config(self, llm_config: Dict[str, Any]) -> None:
        """Validate LLM configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(llm_config, dict):
            self.result.add_error("LLM configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for LLM configuration

        # Validate global settings
        if "settings" in llm_config:
            self._validate_llm_global_settings(llm_config["settings"])

        # Validate API keys
        if "api_keys" in llm_config:
            self._validate_llm_api_keys(llm_config["api_keys"])

        # Validate models
        if "models" in llm_config:
            self._validate_llm_models(llm_config["models"])

    def _validate_llm_global_settings(self, settings: Dict[str, Any]) -> None:
        """Validate LLM global settings."""
        if not isinstance(settings, dict):
            self.result.add_error("LLM settings must be a dictionary")
            return

        # Validate temperature
        if "temperature" in settings:
            temp = settings["temperature"]
            if not isinstance(temp, (int, float)) or not (0.0 <= temp <= 1.0):
                self.result.add_error("LLM temperature must be a number between 0.0 and 1.0")

        # Validate max_tokens
        if "max_tokens" in settings:
            max_tokens = settings["max_tokens"]
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                self.result.add_error("LLM max_tokens must be a positive integer")

        # Validate timeout_seconds
        if "timeout_seconds" in settings:
            timeout = settings["timeout_seconds"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                self.result.add_error("LLM timeout_seconds must be a positive number")

    def _validate_llm_api_keys(self, api_keys: Dict[str, Any]) -> None:
        """Validate LLM API keys configuration."""
        if not isinstance(api_keys, dict):
            self.result.add_error("LLM api_keys must be a dictionary")
            return

        for provider, key in api_keys.items():
            if not isinstance(key, str):
                self.result.add_error(f"API key for {provider} must be a string")

    def _validate_llm_models(self, models: List[Dict[str, Any]]) -> None:
        """Validate LLM models configuration."""
        if not isinstance(models, list):
            self.result.add_error("LLM models must be a list")
            return

        capabilities_seen = set()
        for i, model_config in enumerate(models):
            if not isinstance(model_config, dict):
                self.result.add_error(f"LLM model {i} must be a dictionary")
                continue

            # Find the capability (text, vision, audio, documents, embedding)
            known_capabilities = {"text", "vision", "audio", "documents", "embedding"}
            capability_fields = set(model_config.keys()) & known_capabilities

            if not capability_fields:
                self.result.add_error(
                    f"LLM model {i} must have at least one capability: {list(known_capabilities)}"
                )
                continue

            if len(capability_fields) > 1:
                self.result.add_error(
                    f"LLM model {i} can only specify one capability per model entry, "
                    f"found: {list(capability_fields)}"
                )
                continue

            capability = list(capability_fields)[0]
            model_name = model_config[capability]

            # Check for duplicate capabilities
            if capability in capabilities_seen:
                self.result.add_warning(
                    f"Multiple models defined for capability '{capability}' - "
                    f"last one will be used"
                )
            capabilities_seen.add(capability)

            # Validate model name
            if not isinstance(model_name, str) or not model_name.strip():
                self.result.add_error(f"LLM model name for {capability} must be a non-empty string")

            # Validate model-specific API key if provided
            if "api_key" in model_config:
                api_key = model_config["api_key"]
                if not isinstance(api_key, str):
                    self.result.add_error(f"API key for {capability} model must be a string")

            # Validate model-specific settings
            if "settings" in model_config:
                self._validate_model_capability_settings(model_config["settings"], capability)

    def _validate_model_capability_settings(
        self, settings: Dict[str, Any], capability: str
    ) -> None:
        """Validate model capability-specific settings."""
        if not isinstance(settings, dict):
            self.result.add_error(f"Settings for {capability} model must be a dictionary")
            return

        # Validate common settings
        if "temperature" in settings:
            temp = settings["temperature"]
            if not isinstance(temp, (int, float)) or not (0.0 <= temp <= 1.0):
                self.result.add_error(
                    f"Temperature for {capability} model must be between 0.0 and 1.0"
                )

        if "max_tokens" in settings:
            max_tokens = settings["max_tokens"]
            if not isinstance(max_tokens, int) or max_tokens <= 0:
                self.result.add_error(
                    f"max_tokens for {capability} model must be a positive integer"
                )

        if "timeout_seconds" in settings:
            timeout = settings["timeout_seconds"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                self.result.add_error(
                    f"timeout_seconds for {capability} model must be a positive number"
                )

        # Validate capability-specific settings
        if capability == "vision":
            self._validate_vision_settings(settings)
        elif capability == "audio":
            self._validate_audio_settings(settings)
        elif capability == "documents":
            self._validate_documents_settings(settings)

    def _validate_vision_settings(self, settings: Dict[str, Any]) -> None:
        """Validate vision model settings."""
        if "image" in settings:
            image_settings = settings["image"]
            if not isinstance(image_settings, dict):
                self.result.add_error("Vision image settings must be a dictionary")
                return

            # Validate max_size_mb
            if "max_size_mb" in image_settings:
                max_size = image_settings["max_size_mb"]
                if not isinstance(max_size, (int, float)) or max_size <= 0:
                    self.result.add_error("Vision max_size_mb must be a positive number")

            # Validate preprocessing settings
            if "preprocessing" in image_settings:
                preprocessing = image_settings["preprocessing"]
                if not isinstance(preprocessing, dict):
                    self.result.add_error("Vision preprocessing settings must be a dictionary")
                    return

                if "resize" in preprocessing:
                    resize = preprocessing["resize"]
                    if not isinstance(resize, bool):
                        self.result.add_error("Vision resize setting must be a boolean")

                if "max_width" in preprocessing:
                    width = preprocessing["max_width"]
                    if not isinstance(width, int) or width <= 0:
                        self.result.add_error("Vision max_width must be a positive integer")

                if "max_height" in preprocessing:
                    height = preprocessing["max_height"]
                    if not isinstance(height, int) or height <= 0:
                        self.result.add_error("Vision max_height must be a positive integer")

    def _validate_audio_settings(self, settings: Dict[str, Any]) -> None:
        """Validate audio model settings."""
        if "max_size_mb" in settings:
            max_size = settings["max_size_mb"]
            if not isinstance(max_size, (int, float)) or max_size <= 0:
                self.result.add_error("Audio max_size_mb must be a positive number")

        if "language" in settings:
            language = settings["language"]
            if not isinstance(language, str) or not language.strip():
                self.result.add_error("Audio language must be a non-empty string")

    def _validate_documents_settings(self, settings: Dict[str, Any]) -> None:
        """Validate documents model settings."""
        if "max_size_mb" in settings:
            max_size = settings["max_size_mb"]
            if not isinstance(max_size, (int, float)) or max_size <= 0:
                self.result.add_error("Documents max_size_mb must be a positive number")

        if "extraction" in settings:
            extraction = settings["extraction"]
            if not isinstance(extraction, dict):
                self.result.add_error("Documents extraction settings must be a dictionary")
                return

            if "chunk_size" in extraction:
                chunk_size = extraction["chunk_size"]
                if not isinstance(chunk_size, int) or chunk_size <= 0:
                    self.result.add_error("Documents chunk_size must be a positive integer")

            if "overlap" in extraction:
                overlap = extraction["overlap"]
                if not isinstance(overlap, int) or overlap < 0:
                    self.result.add_error("Documents overlap must be a non-negative integer")

    def _validate_memory_config(self, memory_config: Dict[str, Any]) -> None:
        """Validate memory configuration."""
        if not isinstance(memory_config, dict):
            self.result.add_error("Memory configuration must be a dictionary")
            return

        # Ensure short-term memory configuration exists (always required)
        if "short_term" not in memory_config:
            # Add default short-term configuration
            memory_config["short_term"] = self._get_default_short_term_config()

        # Validate short-term memory configuration
        short_term_config = memory_config["short_term"]
        if not isinstance(short_term_config, dict):
            self.result.add_error("Memory short_term configuration must be a dictionary")
        else:
            self._validate_short_term_memory_config(short_term_config)

        # Legacy buffer configuration is no longer supported
        if "buffer" in memory_config:
            self.result.add_error(
                "Legacy memory.short_term configuration is no longer supported. "
                "All buffer settings must be under memory.short_term.buffer."
            )

        # Validate long-term memory configuration
        if "long_term" in memory_config:
            long_term_config = memory_config["long_term"]
            if not isinstance(long_term_config, dict):
                self.result.add_error("Memory long_term configuration must be a dictionary")
            else:
                self._validate_long_term_memory_config(long_term_config)

    def _get_default_short_term_config(self) -> Dict[str, Any]:
        """Get default short-term memory configuration."""
        return {
            "max_memory_mb": "auto",
            "vector_dimension": 1536,
            "mode": "local",
            "fifo_interval_min": 5,
            "buffer": {
                "size": 10,
                "multiplier": 10,
                "vector_search": True
            }
        }

    def _validate_short_term_memory_config(self, short_term_config: Dict[str, Any]) -> None:
        """Validate short-term memory configuration."""
        # Set defaults for missing fields
        if "max_memory_mb" not in short_term_config:
            short_term_config["max_memory_mb"] = "auto"
        if "vector_dimension" not in short_term_config:
            short_term_config["vector_dimension"] = 1536
        if "mode" not in short_term_config:
            short_term_config["mode"] = "local"
        if "fifo_interval_min" not in short_term_config:
            short_term_config["fifo_interval_min"] = 5
        if "buffer" not in short_term_config:
            short_term_config["buffer"] = {
                "size": 10,
                "multiplier": 10,
                "vector_search": True
            }

        # Validate max_memory_mb
        max_memory = short_term_config["max_memory_mb"]
        if max_memory != "auto" and (not isinstance(max_memory, int) or max_memory <= 0):
            self.result.add_error(
                "Short-term memory max_memory_mb must be 'auto' or a positive integer"
            )

        # Validate mode
        mode = short_term_config.get("mode", "local")
        if mode not in ["local", "remote"]:
            self.result.add_error("Short-term memory mode must be 'local' or 'remote'")

        # Reject "auto" with remote mode - remote servers require explicit memory limits
        if mode == "remote" and max_memory == "auto":
            self.result.add_error(
                "Short-term memory max_memory_mb cannot be 'auto' with remote mode. "
                "Remote servers require explicit memory limits (e.g., max_memory_mb: 512)."
            )

        # Validate vector dimension
        if "vector_dimension" in short_term_config:
            dimension = short_term_config["vector_dimension"]
            if not isinstance(dimension, int) or dimension <= 0:
                self.result.add_error(
                    "Short-term memory vector_dimension must be a positive integer"
                )

        # Validate fifo_interval_min
        if "fifo_interval_min" in short_term_config:
            interval = short_term_config["fifo_interval_min"]
            if not isinstance(interval, int) or interval <= 0:
                self.result.add_error(
                    "Short-term memory fifo_interval_min must be a positive integer"
                )

        # Validate remote configuration if mode is remote
        if short_term_config.get("mode") == "remote" and "remote" in short_term_config:
            remote_config = short_term_config["remote"]
            if not isinstance(remote_config, dict):
                self.result.add_error("Short-term memory remote configuration must be a dictionary")
            elif "url" not in remote_config:
                self.result.add_error("Short-term memory remote configuration must include 'url'")

        # Validate buffer configuration if present
        if "buffer" in short_term_config:
            buffer_config = short_term_config["buffer"]
            if not isinstance(buffer_config, dict):
                self.result.add_error("Short-term memory buffer configuration must be a dictionary")
            else:
                self._validate_short_term_buffer_config(buffer_config)

    def _validate_short_term_buffer_config(self, buffer_config: Dict[str, Any]) -> None:
        """Validate short-term buffer memory configuration."""
        # Set defaults for missing fields
        if "size" not in buffer_config:
            buffer_config["size"] = 10
        if "multiplier" not in buffer_config:
            buffer_config["multiplier"] = 10
        if "vector_search" not in buffer_config:
            buffer_config["vector_search"] = True

        # Validate size and multiplier
        size = buffer_config["size"]
        if not isinstance(size, int) or size <= 0:
            self.result.add_error(
                "Short-term buffer memory size must be a positive integer"
            )

        multiplier = buffer_config["multiplier"]
        if not isinstance(multiplier, int) or multiplier <= 0:
            self.result.add_error(
                "Short-term buffer memory multiplier must be a positive integer"
            )

        # Validate vector search settings
        vector_search = buffer_config["vector_search"]
        if not isinstance(vector_search, bool):
            self.result.add_error("Short-term buffer memory vector_search must be a boolean")

    def _validate_long_term_memory_config(self, long_term_config: Dict[str, Any]) -> None:
        """Validate long-term memory configuration."""
        # Validate connection string
        if "connection_string" in long_term_config:
            connection_string = long_term_config["connection_string"]
            if not isinstance(connection_string, str) or not connection_string.strip():
                self.result.add_error(
                    "Long-term memory connection_string must be a non-empty string"
                )
            else:
                # Basic format validation
                valid_prefixes = ["postgresql://", "postgres://", "sqlite://"]
                valid_suffix = connection_string.endswith(".db")
                if (
                    not any(connection_string.startswith(prefix) for prefix in valid_prefixes)
                    and not valid_suffix
                ):
                    self.result.add_warning(
                        "Long-term memory connection_string should start with "
                        "postgresql://, postgres://, sqlite:// or end with .db"
                    )

        # Validate embedding model
        if "embedding_model" in long_term_config:
            embedding_model = long_term_config["embedding_model"]
            if not isinstance(embedding_model, str) or not embedding_model.strip():
                self.result.add_error("Long-term memory embedding_model must be a non-empty string")

    def _validate_logging_config(self, logging_config: Dict[str, Any]) -> None:
        """Validate logging configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(logging_config, dict):
            self.result.add_error("Logging configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for logging configuration

        # Validate level (enum: debug, info, warning, error)
        if "level" in logging_config:
            level = logging_config["level"]
            valid_levels = ["debug", "info", "warning", "error"]
            if level not in valid_levels:
                self.result.add_error(
                    f"Invalid logging level '{level}'. "
                    f"Valid levels are: {', '.join(valid_levels)}"
                )

        # Validate format (enum: jsonl, text)
        if "format" in logging_config:
            format_value = logging_config["format"]
            valid_formats = ["jsonl", "text"]
            if format_value not in valid_formats:
                self.result.add_error(
                    f"Invalid logging format '{format_value}'. "
                    f"Valid formats are: {', '.join(valid_formats)}"
                )

        # Validate output (enum: stdout, file, stream)
        output = logging_config.get("output", "stdout")
        valid_outputs = ["stdout", "file", "stream"]
        if output not in valid_outputs:
            self.result.add_error(
                f"Invalid logging output '{output}'. "
                f"Valid outputs are: {', '.join(valid_outputs)}"
            )

        # Validate path (required if output == "file")
        if output == "file":
            if "path" not in logging_config:
                self.result.add_error("Logging path is required when output is 'file'")
            else:
                path = logging_config["path"]
                if not isinstance(path, str) or not path.strip():
                    self.result.add_error("Logging path must be a non-empty string")

        # Validate stream_url (required if output == "stream")
        if output == "stream":
            if "stream_url" not in logging_config:
                self.result.add_error("Logging stream_url is required when output is 'stream'")
            else:
                stream_url = logging_config["stream_url"]
                if not isinstance(stream_url, str) or not stream_url.strip():
                    self.result.add_error("Logging stream_url must be a non-empty string")

        # Validate log categories (optional array)
        if "log" in logging_config:
            log_categories = logging_config["log"]
            if not isinstance(log_categories, list):
                self.result.add_error("Logging 'log' field must be an array")
            else:
                for category in log_categories:
                    if not isinstance(category, str):
                        self.result.add_error("Logging category must be a string")
                    # Allow any logging categories users want to define

        # Validate exclude categories (optional array, overrides log)
        if "exclude" in logging_config:
            exclude_categories = logging_config["exclude"]
            if not isinstance(exclude_categories, list):
                self.result.add_error("Logging 'exclude' field must be an array")
            else:
                for category in exclude_categories:
                    if not isinstance(category, str):
                        self.result.add_error("Logging exclude category must be a string")
                    # Allow any logging exclude categories users want to define

    def _validate_overlord_config(self, overlord_config: Dict[str, Any]) -> None:
        """Validate overlord configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(overlord_config, dict):
            self.result.add_error("Overlord configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for overlord configuration

        # Validate persona (new) and system_message (legacy support)
        if "persona" in overlord_config:
            if not isinstance(overlord_config["persona"], str):
                self.result.add_error("Overlord persona must be a string")

        # Legacy support for system_message (but warn about deprecation)
        if "system_message" in overlord_config:
            self.result.add_warning(
                "Overlord 'system_message' is deprecated. Use 'persona' instead."
            )
            if not isinstance(overlord_config["system_message"], str):
                self.result.add_error("Overlord system_message must be a string")

        # Validate overlord LLM configuration
        if "llm" in overlord_config:
            self._validate_overlord_llm_config(overlord_config["llm"])

        # Validate overlord behavior configuration
        if "config" in overlord_config:
            self._validate_overlord_behavior_config(overlord_config["config"])

    def _validate_overlord_llm_config(self, llm_config: Dict[str, Any]) -> None:
        """Validate overlord LLM configuration."""
        if not isinstance(llm_config, dict):
            self.result.add_error("Overlord LLM configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for overlord LLM configuration

        # Validate model
        if "model" in llm_config:
            if not isinstance(llm_config["model"], str):
                self.result.add_error("Overlord LLM model must be a string")

        # Validate api_key
        if "api_key" in llm_config:
            if not isinstance(llm_config["api_key"], str):
                self.result.add_error("Overlord LLM api_key must be a string")

        # Validate settings
        if "settings" in llm_config:
            self._validate_llm_global_settings(llm_config["settings"])

    def _validate_overlord_behavior_config(self, config: Dict[str, Any]) -> None:
        """Validate overlord behavior configuration."""
        if not isinstance(config, dict):
            self.result.add_error("Overlord behavior configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for overlord behavior configuration

        # Validate max_extraction_tokens
        if "max_extraction_tokens" in config:
            tokens = config["max_extraction_tokens"]
            if not isinstance(tokens, int) or tokens <= 0:
                self.result.add_error("max_extraction_tokens must be a positive integer")

        # Validate max_tool_calls
        if "max_tool_calls" in config:
            calls = config["max_tool_calls"]
            if not isinstance(calls, int) or (calls <= 0 and calls != -1):
                self.result.add_error("max_tool_calls must be positive integer or -1")

        # Validate response_format (no longer supported)
        if "response_format" in config:
            self.result.add_error(
                "Overlord 'response_format' is no longer supported. Use 'response.format' instead."
            )

        # Validate response configuration (required structure)
        if "response" in config:
            self._validate_overlord_response_config(config["response"])
        else:
            self.result.add_error("Overlord 'response' configuration is required")

        # Validate intelligence configuration
        if "learn_user_preference" in config:
            if not isinstance(config["learn_user_preference"], bool):
                self.result.add_error("learn_user_preference must be a boolean")

        if "adaptive_responses" in config:
            if not isinstance(config["adaptive_responses"], bool):
                self.result.add_error("adaptive_responses must be a boolean")

        # Validate resilience configuration
        if "circuit_breaker" in config:
            if not isinstance(config["circuit_breaker"], bool):
                self.result.add_error("circuit_breaker must be a boolean")

        if "error_recovery" in config:
            if not isinstance(config["error_recovery"], bool):
                self.result.add_error("error_recovery must be a boolean")

        # Validate workflow configuration
        if "auto_decomposition" in config:
            if not isinstance(config["auto_decomposition"], bool):
                self.result.add_error("auto_decomposition must be a boolean")

        if "plan_approval_threshold" in config:
            threshold = config["plan_approval_threshold"]
            if not isinstance(threshold, int) or threshold < 1 or threshold > 10:
                self.result.add_error("plan_approval_threshold must be an integer between 1 and 10")

        # Validate caching configuration
        if "caching" in config:
            self._validate_overlord_caching_config(config["caching"])

    def _validate_overlord_response_config(self, response_config: Dict[str, Any]) -> None:
        """Validate overlord response configuration."""
        if not isinstance(response_config, dict):
            self.result.add_error("Overlord response configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for overlord response configuration

        # Validate format
        if "format" in response_config:
            format_val = response_config["format"]
            if format_val not in ["markdown", "json", "text"]:
                self.result.add_error(
                    f"response.format '{format_val}' invalid. Valid: markdown, json, text"
                )

        # Validate interactive_elements
        if "interactive_elements" in response_config:
            if not isinstance(response_config["interactive_elements"], bool):
                self.result.add_error("response.interactive_elements must be a boolean")

    def _validate_overlord_caching_config(self, caching_config: Dict[str, Any]) -> None:
        """Validate overlord caching configuration."""
        if not isinstance(caching_config, dict):
            self.result.add_error("Overlord caching configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for overlord caching configuration

        # Validate enabled
        if "enabled" in caching_config:
            if not isinstance(caching_config["enabled"], bool):
                self.result.add_error("Caching enabled must be a boolean")

        # Validate ttl
        if "ttl" in caching_config:
            ttl = caching_config["ttl"]
            if not isinstance(ttl, int) or ttl <= 0:
                self.result.add_error("Caching TTL must be a positive integer")

    def _validate_async_config(self, async_config: Dict[str, Any]) -> None:
        """Validate async configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(async_config, dict):
            self.result.add_error("Async configuration must be a dictionary")
            return

        # Validate threshold_seconds
        if "threshold_seconds" in async_config:
            threshold = async_config["threshold_seconds"]
            if not isinstance(threshold, int) or threshold <= 0:
                self.result.add_error("threshold_seconds must be a positive integer")

        # Validate enable_estimation
        if "enable_estimation" in async_config:
            estimation = async_config["enable_estimation"]
            if not isinstance(estimation, bool):
                self.result.add_error("enable_estimation must be a boolean")

        # Validate webhook_url
        if "webhook_url" in async_config:
            webhook_url = async_config["webhook_url"]
            if not isinstance(webhook_url, str):
                self.result.add_error("webhook_url must be a string")
            elif not (webhook_url.startswith("http://") or webhook_url.startswith("https://")):
                self.result.add_error("webhook_url must start with http:// or https://")

        # Validate webhook_retries
        if "webhook_retries" in async_config:
            retries = async_config["webhook_retries"]
            if not isinstance(retries, int) or retries < 0:
                self.result.add_error("webhook_retries must be a non-negative integer")

        # Validate webhook_timeout
        if "webhook_timeout" in async_config:
            timeout = async_config["webhook_timeout"]
            if not isinstance(timeout, int) or timeout <= 0:
                self.result.add_error("webhook_timeout must be a positive integer")

    def _validate_a2a_service_config(self, service_config: Dict[str, Any], filename: str) -> None:
        """Validate A2A service configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(service_config, dict):
            self.result.add_error(f"A2A service configuration in {filename} must be a dictionary")
            return

        # Check required fields
        for field in self.REQUIRED_A2A_SERVICE_FIELDS:
            if field not in service_config:
                self.result.add_error(f"A2A service {filename} missing required field: {field}")

        # Validate schema version
        schema = service_config.get("schema")
        if schema and not isinstance(schema, str):
            self.result.add_error(f"A2A service {filename} schema must be a string")

        # Validate id
        service_id = service_config.get("id")
        if service_id and not isinstance(service_id, str):
            self.result.add_error(f"A2A service {filename} id must be a string")

        # Validate name
        name = service_config.get("name")
        if name and not isinstance(name, str):
            self.result.add_error(f"A2A service {filename} name must be a string")

        # Validate description
        description = service_config.get("description")
        if description and not isinstance(description, str):
            self.result.add_error(f"A2A service {filename} description must be a string")

        # Validate url
        url = service_config.get("url")
        if url:
            if not isinstance(url, str):
                self.result.add_error(f"A2A service {filename} url must be a string")
            elif not (url.startswith("http://") or url.startswith("https://")):
                self.result.add_error(
                    f"A2A service {filename} url must start with http:// or https://"
                )

        # Validate active field
        if "active" in service_config:
            active = service_config["active"]
            if not isinstance(active, bool):
                self.result.add_error(f"A2A service {filename} active must be a boolean")

        # Validate metadata fields
        self._validate_a2a_service_metadata(service_config, filename)

        # Validate retry/timeout overrides
        self._validate_a2a_service_overrides(service_config, filename)

        # Validate authentication configuration
        if "auth" in service_config:
            self._validate_a2a_service_auth(service_config["auth"], filename)

    def _validate_a2a_service_metadata(self, service_config: Dict[str, Any], filename: str) -> None:
        """Validate A2A service metadata fields."""
        metadata_fields = ["author", "version", "documentation", "support_contact"]

        for field in metadata_fields:
            if field in service_config:
                value = service_config[field]
                if not isinstance(value, str):
                    self.result.add_error(f"A2A service {filename} {field} must be a string")

    def _validate_a2a_service_overrides(
        self, service_config: Dict[str, Any], filename: str
    ) -> None:
        """Validate A2A service retry/timeout override configuration."""
        # Validate retry_attempts
        if "retry_attempts" in service_config:
            retry_attempts = service_config["retry_attempts"]
            if not isinstance(retry_attempts, int) or retry_attempts < 0:
                self.result.add_error(
                    f"A2A service {filename} retry_attempts must be a non-negative integer"
                )

        # Validate timeout_seconds
        if "timeout_seconds" in service_config:
            timeout_seconds = service_config["timeout_seconds"]
            if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
                self.result.add_error(
                    f"A2A service {filename} timeout_seconds must be a positive integer"
                )

    def _validate_a2a_service_auth(self, auth_config: Dict[str, Any], filename: str) -> None:
        """Validate A2A service authentication configuration."""
        if not isinstance(auth_config, dict):
            self.result.add_error(f"A2A service {filename} auth must be a dictionary")
            return

        # Validate auth type
        auth_type = auth_config.get("type", "none")
        valid_auth_types = ["api_key", "bearer", "basic", "custom", "none"]

        if auth_type not in valid_auth_types:
            self.result.add_error(
                f"A2A service {filename} auth type '{auth_type}' invalid. "
                f"Valid types are: {valid_auth_types}"
            )
            return

        # Validate type-specific auth requirements
        if auth_type == "api_key":
            if "api_key" not in auth_config:
                self.result.add_error(
                    f"A2A service {filename} api_key auth requires 'api_key' field"
                )
            if "header" in auth_config and not isinstance(auth_config["header"], str):
                self.result.add_error(f"A2A service {filename} auth header must be a string")

        elif auth_type == "bearer":
            if "token" not in auth_config:
                self.result.add_error(f"A2A service {filename} bearer auth requires 'token' field")

        elif auth_type == "basic":
            required_basic_fields = ["username", "password"]
            for field in required_basic_fields:
                if field not in auth_config:
                    self.result.add_error(
                        f"A2A service {filename} basic auth requires '{field}' field"
                    )

        elif auth_type == "custom":
            if "headers" not in auth_config:
                self.result.add_error(
                    f"A2A service {filename} custom auth requires 'headers' field"
                )
            elif not isinstance(auth_config["headers"], dict):
                self.result.add_error(
                    f"A2A service {filename} custom auth headers must be a dictionary"
                )

    def _validate_outbound_service_auth_config(
        self, service_config: Dict[str, Any], service_identifier: str
    ) -> None:
        """Validate outbound service authentication configuration in formation files."""
        if not isinstance(service_config, dict):
            self.result.add_error(f"{service_identifier} configuration must be a dictionary")
            return

        # Check required field: service_id
        if "service_id" not in service_config:
            self.result.add_error(f"{service_identifier} missing required field: service_id")

        # Validate service_id
        service_id = service_config.get("service_id")
        if service_id and not isinstance(service_id, str):
            self.result.add_error(f"{service_identifier} service_id must be a string")

        # Validate authentication configuration if present
        if "auth" in service_config:
            self._validate_outbound_auth_config(service_config["auth"], service_identifier)

    def _validate_outbound_auth_config(
        self, auth_config: Dict[str, Any], service_identifier: str
    ) -> None:
        """Validate outbound authentication configuration."""
        if not isinstance(auth_config, dict):
            self.result.add_error(f"{service_identifier} auth must be a dictionary")
            return

        # Validate auth type
        auth_type = auth_config.get("type", "none")
        valid_auth_types = ["api_key", "bearer", "basic", "custom", "none"]

        if auth_type not in valid_auth_types:
            self.result.add_error(
                f"{service_identifier} auth type '{auth_type}' invalid. "
                f"Valid types are: {valid_auth_types}"
            )
            return

        # Validate type-specific auth requirements
        if auth_type == "api_key":
            if "api_key" not in auth_config:
                self.result.add_error(
                    f"{service_identifier} api_key auth requires 'api_key' field"
                )
            if "header" in auth_config and not isinstance(auth_config["header"], str):
                self.result.add_error(f"{service_identifier} auth header must be a string")

        elif auth_type == "bearer":
            if "token" not in auth_config:
                self.result.add_error(f"{service_identifier} bearer auth requires 'token' field")

        elif auth_type == "basic":
            required_basic_fields = ["username", "password"]
            for field in required_basic_fields:
                if field not in auth_config:
                    self.result.add_error(
                        f"{service_identifier} basic auth requires '{field}' field"
                    )

        elif auth_type == "custom":
            if "headers" not in auth_config:
                self.result.add_error(
                    f"{service_identifier} custom auth requires 'headers' field"
                )
            elif not isinstance(auth_config["headers"], dict):
                self.result.add_error(
                    f"{service_identifier} custom auth headers must be a dictionary"
                )


def validate_formation(
    formation_path: Union[str, Path], secrets_manager: Optional[Any] = None
) -> ValidationResult:
    """
    Convenience function to validate a formation configuration.

    Args:
        formation_path: Path to formation file or directory
        secrets_manager: Optional secrets manager for credential validation

    Returns:
        ValidationResult: Comprehensive validation results
    """
    validator = FormationValidator()
    return validator.validate(formation_path, secrets_manager)


def validate_formation_cli(formation_path: Union[str, Path]) -> None:
    """
    CLI-friendly validation function that prints results to console.

    Args:
        formation_path: Path to formation file or directory
    """
    result = validate_formation(formation_path)

    print(result.detailed_report())

    if not result.is_valid:
        exit(1)
