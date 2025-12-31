"""
Formation configuration validation utilities.

This module provides tools for validating formation configurations,
detecting common issues, and ensuring configurations are well-formed.
"""

from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import yaml
import json
import re
import asyncio

# Import the MCP registry to get valid MCP names dynamically
from ...services.mcp.built_in import BUILTIN_MCP_REGISTRY

# Pattern for detecting user credentials in configuration
USER_CREDENTIAL_PATTERN = re.compile(r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}")


def extract_user_credential_placeholders(obj: Any, found_credentials: set, path: str = "") -> None:
    """
    Recursively extract all user credential placeholders from a configuration object.

    Args:
        obj: The configuration object to scan
        found_credentials: Set to store found credential service names and paths
        path: Current path in the configuration tree (for error reporting)
    """
    if isinstance(obj, str):
        matches = USER_CREDENTIAL_PATTERN.findall(obj)
        for match in matches:
            # findall returns the captured group directly (e.g., "github")
            service_name = match
            found_credentials.add((service_name, path))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            extract_user_credential_placeholders(value, found_credentials, new_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            extract_user_credential_placeholders(item, found_credentials, new_path)


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
                if file_path.suffix.lower() in [".afs", ".yaml", ".yml"]:
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
            # Check for formation config file (priority: .afs > .yaml > .yml)
            formation_file = dir_path / "formation.afs"
            if not formation_file.exists():
                formation_file = dir_path / "formation.yaml"
            if not formation_file.exists():
                formation_file = dir_path / "formation.yml"

            if not formation_file.exists():
                self.result.add_error("Missing formation config file (formation.afs/yaml/yml) in modular formation")
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
                if file_path.suffix.lower() in [".afs", ".yaml", ".yml"]:
                    config = yaml.safe_load(f)
                elif file_path.suffix.lower() == ".json":
                    config = json.load(f)
                else:
                    return False

            if not isinstance(config, dict):
                return False

            # Check for formation-specific indicators first
            formation_fields = ["agents", "overlord", "mcp", "memory", "logging", "server"]
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
                if file_path.suffix.lower() in [".afs", ".yaml", ".yml"]:
                    config = yaml.safe_load(f)
                elif file_path.suffix.lower() == ".json":
                    config = json.load(f)
                else:
                    self.result.add_error(f"Unsupported file format: {file_path.suffix}")
                    return

            if not isinstance(config, dict):
                self.result.add_error("Agent configuration must be a dictionary")
                return

            # Validate as a single agent (standalone agent file requires schema)
            self._validate_agents([config], is_inline=False)

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
            elif schema != "1.0.0":
                self.result.add_error(
                    f"Invalid formation schema version: {schema}. Only '1.0.0' is supported."
                )

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

        # Validate server configuration
        if "server" in config:
            self._validate_server_config(config["server"])

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

        # Validate document processing configuration
        if "document_processing" in config:
            self._validate_document_processing_config(config["document_processing"])

        # Validate scheduler configuration
        if "scheduler" in config:
            self._validate_scheduler_config(config["scheduler"])

        # Validate runtime configuration
        if "runtime" in config:
            self._validate_runtime_config(config["runtime"])

        # Validate user credentials configuration
        if "user_credentials" in config:
            self._validate_user_credentials_config(config["user_credentials"])

    def _validate_user_credentials_config(self, credentials_config: Dict[str, Any]) -> None:
        """Validate user credentials configuration."""
        if not isinstance(credentials_config, dict):
            self.result.add_error("user_credentials must be a dictionary")
            return

        # Validate mode
        if "mode" in credentials_config:
            mode = credentials_config["mode"]
            if mode not in ["redirect", "dynamic"]:
                self.result.add_error(
                    f"Invalid user_credentials.mode: {mode}. Must be 'redirect' or 'dynamic'"
                )

        # Validate redirect_message
        if "redirect_message" in credentials_config:
            redirect_msg = credentials_config["redirect_message"]
            if not isinstance(redirect_msg, str) or not redirect_msg.strip():
                self.result.add_error(
                    "user_credentials.redirect_message must be a non-empty string"
                )

        # Validate encryption_key
        if "encryption_key" in credentials_config:
            enc_key = credentials_config["encryption_key"]
            if enc_key is not None and (not isinstance(enc_key, str) or not enc_key.strip()):
                self.result.add_error(
                    "user_credentials.encryption_key must be null or a non-empty string"
                )



    def _validate_agents(self, agents_config: List[Dict[str, Any]], is_inline: bool = True) -> None:
        """Validate agents configuration.

        Args:
            agents_config: List of agent configurations
            is_inline: True if agents are inline in a flattened formation (no schema required),
                      False if they are standalone agent files (schema required)
        """
        if not isinstance(agents_config, list):
            self.result.add_error("Agents configuration must be a list")
            return

        agent_ids = set()
        for i, agent_config in enumerate(agents_config):
            if not isinstance(agent_config, dict):
                self.result.add_error(f"Agent {i} configuration must be a dictionary")
                continue

            # Check required fields
            # For inline agents in flattened formations, schema is not required
            required_fields = [
                field for field in self.REQUIRED_AGENT_FIELDS if field != "schema" or not is_inline
            ]
            for field in required_fields:
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

    def _validate_mcp_config(self, mcp_config: Dict[str, Any], is_inline: bool = True) -> None:
        """Validate MCP configuration according to SCHEMA_GUIDE.md.

        Args:
            mcp_config: MCP configuration dictionary
            is_inline: True if servers are inline in a flattened formation (no schema required),
                      False if they are standalone MCP files (schema required)
        """
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

                self._validate_single_mcp_server(server_config, i, server_ids, is_inline)

    def _validate_single_mcp_server(
        self, server_config: Dict[str, Any], index: int, server_ids: set, is_inline: bool = True
    ) -> None:
        """Validate a single MCP server configuration according to SCHEMA_GUIDE.md.

        Args:
            server_config: MCP server configuration
            index: Index of the server in the list
            server_ids: Set of already seen server IDs for duplicate detection
            is_inline: True if server is inline in a flattened formation (no schema required),
                      False if it's a standalone MCP file (schema required)
        """
        # Check required fields
        # For inline MCP servers in flattened formations, schema is not required
        required_fields = [
            field for field in self.REQUIRED_MCP_SERVER_FIELDS if field != "schema" or not is_inline
        ]
        for field in required_fields:
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
            else:
                # Validate inbound auth configuration if present
                if "auth" in inbound:
                    self._validate_inbound_auth_config(inbound["auth"])

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

        # Check for agent files (support .afs, .yaml, .yml)
        agent_files = list(agents_dir.glob("*.afs")) + list(agents_dir.glob("*.yaml")) + list(agents_dir.glob("*.yml"))
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

                    self._validate_agents([agent_config], is_inline=False)
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

        # Check for MCP files (support .afs, .yaml, .yml)
        mcp_files = list(mcp_dir.glob("*.afs")) + list(mcp_dir.glob("*.yaml")) + list(mcp_dir.glob("*.yml"))
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

                    # Create servers list structure for validation (standalone files require schema)
                    servers_config = {"servers": [mcp_config]}
                    self._validate_mcp_config(servers_config, is_inline=False)
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

        # Check for A2A files (support .afs, .yaml, .yml)
        a2a_files = list(a2a_dir.glob("*.afs")) + list(a2a_dir.glob("*.yaml")) + list(a2a_dir.glob("*.yml"))
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

            # Find the capability (text, vision, audio, video, documents, embedding, streaming)
            known_capabilities = {"text", "vision", "audio", "video", "documents", "embedding", "streaming"}
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

        # Ensure working memory configuration exists (always required)
        if "working" not in memory_config:
            # Add default working memory configuration
            memory_config["working"] = self._get_default_working_memory_config()

        # Validate working memory configuration
        working_config = memory_config["working"]
        if not isinstance(working_config, dict):
            self.result.add_error("Memory working configuration must be a dictionary")
        else:
            self._validate_working_memory_config(working_config)

        # Validate buffer memory configuration (moved up from working.buffer)
        if "buffer" in memory_config:
            buffer_config = memory_config["buffer"]
            if not isinstance(buffer_config, dict):
                self.result.add_error("Memory buffer configuration must be a dictionary")
            else:
                self._validate_buffer_memory_config(buffer_config)
        else:
            # Ensure buffer memory is always available with default settings
            memory_config["buffer"] = {"size": 10, "multiplier": 10, "vector_search": True}

        # Validate persistent memory configuration
        if "persistent" in memory_config:
            persistent_config = memory_config["persistent"]
            if not isinstance(persistent_config, dict):
                self.result.add_error("Memory persistent configuration must be a dictionary")
            else:
                self._validate_persistent_memory_config(persistent_config)

    def _get_default_working_memory_config(self) -> Dict[str, Any]:
        """Get default working memory configuration."""
        return {
            "max_memory_mb": "auto",
            "vector_dimension": 1536,
            "mode": "local",
            "fifo_interval_min": 5,
        }

    def _validate_working_memory_config(self, working_config: Dict[str, Any]) -> None:
        """Validate working memory configuration."""
        # Set defaults for missing fields
        if "max_memory_mb" not in working_config:
            working_config["max_memory_mb"] = "auto"
        if "vector_dimension" not in working_config:
            working_config["vector_dimension"] = 1536
        if "mode" not in working_config:
            working_config["mode"] = "local"
        if "fifo_interval_min" not in working_config:
            working_config["fifo_interval_min"] = 5

        # Validate max_memory_mb
        max_memory = working_config["max_memory_mb"]
        if max_memory != "auto" and (not isinstance(max_memory, int) or max_memory <= 0):
            self.result.add_error(
                "Working memory max_memory_mb must be 'auto' or a positive integer"
            )

        # Validate mode
        mode = working_config.get("mode", "local")
        if mode not in ["local", "remote"]:
            self.result.add_error("Working memory mode must be 'local' or 'remote'")

        # Reject "auto" with remote mode - remote servers require explicit memory limits
        if mode == "remote" and max_memory == "auto":
            self.result.add_error(
                "Working memory max_memory_mb cannot be 'auto' with remote mode. "
                "Remote servers require explicit memory limits (e.g., max_memory_mb: 512)."
            )

        # Validate vector dimension
        if "vector_dimension" in working_config:
            dimension = working_config["vector_dimension"]
            if not isinstance(dimension, int) or dimension <= 0:
                self.result.add_error("Working memory vector_dimension must be a positive integer")

        # Validate fifo_interval_min
        if "fifo_interval_min" in working_config:
            interval = working_config["fifo_interval_min"]
            if not isinstance(interval, int) or interval <= 0:
                self.result.add_error("Working memory fifo_interval_min must be a positive integer")

        # Validate remote configuration if mode is remote
        if working_config.get("mode") == "remote" and "remote" in working_config:
            remote_config = working_config["remote"]
            if not isinstance(remote_config, dict):
                self.result.add_error("Working memory remote configuration must be a dictionary")
            elif "url" not in remote_config:
                self.result.add_error("Working memory remote configuration must include 'url'")

    def _validate_buffer_memory_config(self, buffer_config: Dict[str, Any]) -> None:
        """Validate buffer memory configuration."""
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
            self.result.add_error("Buffer memory size must be a positive integer")

        multiplier = buffer_config["multiplier"]
        if not isinstance(multiplier, int) or multiplier <= 0:
            self.result.add_error("Buffer memory multiplier must be a positive integer")

        # Validate vector search settings
        vector_search = buffer_config["vector_search"]
        if not isinstance(vector_search, bool):
            self.result.add_error("Buffer memory vector_search must be a boolean")

    def _validate_persistent_memory_config(self, persistent_config: Dict[str, Any]) -> None:
        """Validate persistent memory configuration."""
        # Validate connection string
        if "connection_string" in persistent_config:
            connection_string = persistent_config["connection_string"]
            if not isinstance(connection_string, str) or not connection_string.strip():
                self.result.add_error(
                    "Persistent memory connection_string must be a non-empty string"
                )
            else:
                # Skip validation for secret placeholders
                if "${{" in connection_string and "}}" in connection_string:
                    # This is a secret placeholder, skip validation
                    pass
                else:
                    # Basic format validation
                    valid_prefixes = ["postgresql://", "postgres://", "sqlite://"]
                    valid_suffix = connection_string.endswith(".db")
                    if (
                        not any(connection_string.startswith(prefix) for prefix in valid_prefixes)
                        and not valid_suffix
                    ):
                        self.result.add_warning(
                            "Persistent memory connection_string should start with "
                            "postgresql://, postgres://, sqlite:// or end with .db"
                        )

        # Validate embedding model
        if "embedding_model" in persistent_config:
            embedding_model = persistent_config["embedding_model"]
            if not isinstance(embedding_model, str) or not embedding_model.strip():
                self.result.add_error(
                    "Persistent memory embedding_model must be a non-empty string"
                )

    def _validate_document_processing_config(self, doc_config: Dict[str, Any]) -> None:
        """Validate document processing configuration."""
        if not isinstance(doc_config, dict):
            self.result.add_error("Document processing configuration must be a dictionary")
            return

        # Set defaults for all fields
        if "enabled" not in doc_config:
            doc_config["enabled"] = True
        if "chunking" not in doc_config:
            doc_config["chunking"] = {}
        if "files" not in doc_config:
            doc_config["files"] = {}
        if "models" not in doc_config:
            doc_config["models"] = {}

        # Validate enabled field
        if not isinstance(doc_config["enabled"], bool):
            self.result.add_error("Document processing enabled must be a boolean")

        # Validate chunking configuration
        chunking_config = doc_config["chunking"]
        if not isinstance(chunking_config, dict):
            self.result.add_error("Document processing chunking configuration must be a dictionary")
        else:
            self._validate_document_chunking_config(chunking_config)

        # Validate files configuration
        files_config = doc_config["files"]
        if not isinstance(files_config, dict):
            self.result.add_error("Document processing files configuration must be a dictionary")
        else:
            self._validate_document_files_config(files_config)

        # Validate models configuration
        models_config = doc_config["models"]
        if not isinstance(models_config, dict):
            self.result.add_error("Document processing models configuration must be a dictionary")
        else:
            self._validate_document_models_config(models_config)

    def _validate_document_chunking_config(self, chunking_config: Dict[str, Any]) -> None:
        """Validate document processing chunking configuration."""
        # Set defaults
        if "default_size" not in chunking_config:
            chunking_config["default_size"] = 1000
        if "overlap" not in chunking_config:
            chunking_config["overlap"] = 100
        if "strategies" not in chunking_config:
            chunking_config["strategies"] = ["adaptive", "semantic", "fixed", "paragraph"]

        # Validate default_size
        default_size = chunking_config["default_size"]
        if not isinstance(default_size, int) or default_size <= 0:
            self.result.add_error("Document chunking default_size must be a positive integer")

        # Validate overlap
        overlap = chunking_config["overlap"]
        if not isinstance(overlap, int) or overlap < 0:
            self.result.add_error("Document chunking overlap must be a non-negative integer")

        # Validate strategies
        strategies = chunking_config["strategies"]
        if not isinstance(strategies, list):
            self.result.add_error("Document chunking strategies must be a list")
        else:
            valid_strategies = ["adaptive", "semantic", "fixed", "paragraph"]
            for strategy in strategies:
                if not isinstance(strategy, str) or strategy not in valid_strategies:
                    self.result.add_error(
                        f"Invalid chunking strategy '{strategy}'. "
                        f"Valid strategies are: {', '.join(valid_strategies)}"
                    )

    def _validate_document_files_config(self, files_config: Dict[str, Any]) -> None:
        """Validate document processing files configuration."""
        # Set defaults
        if "max_size_mb" not in files_config:
            files_config["max_size_mb"] = 50
        if "cache_ttl_seconds" not in files_config:
            files_config["cache_ttl_seconds"] = 3600

        # Validate max_size_mb
        max_size_mb = files_config["max_size_mb"]
        if not isinstance(max_size_mb, int) or max_size_mb <= 0:
            self.result.add_error("Document files max_size_mb must be a positive integer")

        # Validate cache_ttl_seconds
        cache_ttl = files_config["cache_ttl_seconds"]
        if not isinstance(cache_ttl, int) or cache_ttl <= 0:
            self.result.add_error("Document files cache_ttl_seconds must be a positive integer")

    def _validate_document_models_config(self, models_config: Dict[str, Any]) -> None:
        """Validate document processing models configuration."""
        # Set defaults
        if "nltk_data_path" not in models_config:
            models_config["nltk_data_path"] = "~/nltk_data"
        if "spacy_model" not in models_config:
            models_config["spacy_model"] = "en_core_web_sm"
        if "sentence_transformer" not in models_config:
            models_config["sentence_transformer"] = "all-MiniLM-L6-v2"

        # Validate nltk_data_path
        nltk_path = models_config["nltk_data_path"]
        if not isinstance(nltk_path, str) or not nltk_path.strip():
            self.result.add_error("Document models nltk_data_path must be a non-empty string")

        # Validate spacy_model
        spacy_model = models_config["spacy_model"]
        if not isinstance(spacy_model, str) or not spacy_model.strip():
            self.result.add_error("Document models spacy_model must be a non-empty string")

        # Validate sentence_transformer
        sentence_transformer = models_config["sentence_transformer"]
        if not isinstance(sentence_transformer, str) or not sentence_transformer.strip():
            self.result.add_error("Document models sentence_transformer must be a non-empty string")

    def _validate_logging_config(self, logging_config: Dict[str, Any]) -> None:
        """Validate logging configuration with two-tier system/conversation architecture."""
        if not isinstance(logging_config, dict):
            self.result.add_error("Logging configuration must be a dictionary")
            return

        # Validate system config (optional)
        if "system" in logging_config:
            self._validate_logging_system_config(logging_config["system"])

        # Validate conversation config (optional)
        if "conversation" in logging_config:
            self._validate_logging_conversation_config(logging_config["conversation"])

    def _validate_logging_system_config(self, system_config: Dict[str, Any]) -> None:
        """Validate logging.system configuration."""
        if not isinstance(system_config, dict):
            self.result.add_error("Logging 'system' must be a dictionary")
            return

        # Validate level (optional, defaults to "debug")
        if "level" in system_config:
            level = system_config["level"]
            valid_levels = ["debug", "info", "warning", "error"]
            if level not in valid_levels:
                self.result.add_error(
                    f"Logging system invalid level '{level}'. "
                    f"Valid levels: {', '.join(valid_levels)}"
                )

        # Validate destination (optional, defaults to "stdout")
        if "destination" in system_config:
            destination = system_config["destination"]
            if not isinstance(destination, str):
                self.result.add_error("Logging system 'destination' must be a string")

    def _validate_logging_conversation_config(self, conversation_config: Dict[str, Any]) -> None:
        """Validate logging.conversation configuration."""
        if not isinstance(conversation_config, dict):
            self.result.add_error("Logging 'conversation' must be a dictionary")
            return

        # Validate enabled (boolean)
        if "enabled" in conversation_config:
            enabled = conversation_config["enabled"]
            if not isinstance(enabled, bool):
                self.result.add_error("Logging conversation 'enabled' field must be a boolean")

        # Validate streams array (optional - if conversation exists, streams is expected)
        if "streams" in conversation_config:
            streams = conversation_config["streams"]
            if not isinstance(streams, list):
                self.result.add_error("Logging conversation 'streams' must be an array")
                return

            if len(streams) == 0:
                self.result.add_warning("Logging conversation streams array is empty - no conversation logging will occur")

            # Validate each stream
            for i, stream in enumerate(streams):
                self._validate_logging_stream(stream, i)

    def _validate_logging_stream(self, stream: Dict[str, Any], index: int) -> None:
        """Validate a single logging stream configuration."""
        if not isinstance(stream, dict):
            self.result.add_error(f"Logging stream {index} must be a dictionary")
            return

        # Validate transport (required)
        if "transport" not in stream:
            self.result.add_error(f"Logging stream {index} missing required field: transport")
            return

        transport = stream["transport"]
        valid_transports = ["stdout", "file", "stream", "trail"]
        if transport not in valid_transports:
            self.result.add_error(
                f"Logging stream {index} invalid transport '{transport}'. "
                f"Valid transports: {', '.join(valid_transports)}"
            )
            return

        # Validate level (optional, defaults to "info")
        if "level" in stream:
            level = stream["level"]
            valid_levels = ["debug", "info", "warn", "error"]
            if level not in valid_levels:
                self.result.add_error(
                    f"Logging stream {index} invalid level '{level}'. "
                    f"Valid levels: {', '.join(valid_levels)}"
                )

        # Validate format (optional, defaults to "jsonl")
        if "format" in stream:
            format_value = stream["format"]
            valid_formats = [
                "jsonl",
                "text",
                "msgpack",
                "protobuf",
                "datadog_json",
                "splunk_hec",
                "elastic_bulk",
                "grafana_loki",
                "newrelic_json",
                "opentelemetry",
            ]
            if format_value not in valid_formats:
                self.result.add_error(
                    f"Logging stream {index} invalid format '{format_value}'. "
                    f"Valid formats: {', '.join(valid_formats)}"
                )

        # Validate transport-specific fields
        if transport == "file":
            self._validate_file_stream(stream, index)
        elif transport == "stream":
            self._validate_stream_stream(stream, index)
        elif transport == "trail":
            self._validate_trail_stream(stream, index)

        # Validate events (optional)
        if "events" in stream:
            events = stream["events"]
            if not isinstance(events, list):
                self.result.add_error(f"Logging stream {index} 'events' must be an array")
            else:
                for event in events:
                    if not isinstance(event, str):
                        self.result.add_error(f"Logging stream {index} event must be a string")

        # Validate auth (optional)
        if "auth" in stream:
            self._validate_logging_auth(stream["auth"], index)

    def _validate_file_stream(self, stream: Dict[str, Any], index: int) -> None:
        """Validate file transport specific fields."""
        if "destination" not in stream:
            self.result.add_error(
                f"Logging stream {index} with file transport requires 'destination' field"
            )
        else:
            destination = stream["destination"]
            if not isinstance(destination, str) or not destination.strip():
                self.result.add_error(
                    f"Logging stream {index} destination must be a non-empty string"
                )

    def _validate_stream_stream(self, stream: Dict[str, Any], index: int) -> None:
        """Validate stream transport specific fields."""
        if "destination" not in stream:
            self.result.add_error(
                f"Logging stream {index} with stream transport requires 'destination' field"
            )
            return

        destination = stream["destination"]
        if not isinstance(destination, str) or not destination.strip():
            self.result.add_error(f"Logging stream {index} destination must be a non-empty string")
            return

        # Validate protocol (optional, auto-detected if not specified)
        protocol = stream.get("protocol")
        if protocol is not None:
            valid_protocols = ["zmq", "webhook", "websocket", "kafka", "tcp", "udp"]
            if protocol not in valid_protocols:
                self.result.add_error(
                    f"Logging stream {index} invalid protocol '{protocol}'. "
                    f"Valid protocols: {', '.join(valid_protocols)}"
                )
        else:
            # Auto-detect protocol from URL and suggest
            if destination.startswith(("https://", "http://")):
                suggested_protocol = "webhook"
            elif destination.startswith(("tcp://", "tcps://", "ipc://", "ipcs://")):
                suggested_protocol = "zmq"
            elif destination.startswith(("ws://", "wss://")):
                suggested_protocol = "websocket"
            else:
                suggested_protocol = "zmq"  # Default fallback

            self.result.add_suggestion(
                f"Logging stream {index}: protocol not specified. Based on URL '{destination}', "
                f"consider adding 'protocol: \"{suggested_protocol}\"'"
            )

    def _validate_trail_stream(self, stream: Dict[str, Any], index: int) -> None:
        """Validate trail transport specific fields."""
        # Trail transport is a special case for MUXI - minimal configuration needed
        # Auth is required but will be validated separately
        if "auth" not in stream:
            self.result.add_error(
                f"Logging stream {index} with trail transport requires 'auth' configuration"
            )

    def _validate_logging_auth(self, auth: Dict[str, Any], stream_index: int) -> None:
        """Validate logging stream authentication configuration."""
        if not isinstance(auth, dict):
            self.result.add_error(f"Logging stream {stream_index} auth must be a dictionary")
            return

        # Validate auth type
        auth_type = auth.get("type", "none")
        valid_auth_types = ["bearer", "basic", "api_key", "token", "custom"]
        if auth_type not in valid_auth_types:
            self.result.add_error(
                f"Logging stream {stream_index} invalid auth type '{auth_type}'. "
                f"Valid types: {', '.join(valid_auth_types)}"
            )
            return

        # Validate type-specific auth fields
        if auth_type == "bearer":
            if "token" not in auth:
                self.result.add_error(
                    f"Logging stream {stream_index} bearer auth requires 'token' field"
                )
        elif auth_type == "basic":
            if "username" not in auth:
                self.result.add_error(
                    f"Logging stream {stream_index} basic auth requires 'username' field"
                )
            if "password" not in auth:
                self.result.add_error(
                    f"Logging stream {stream_index} basic auth requires 'password' field"
                )
        elif auth_type == "api_key":
            if "key" not in auth:
                self.result.add_error(
                    f"Logging stream {stream_index} api_key auth requires 'key' field"
                )
        elif auth_type == "token":
            if "token" not in auth:
                self.result.add_error(
                    f"Logging stream {stream_index} token auth requires 'token' field"
                )
        elif auth_type == "custom":
            if "headers" not in auth:
                self.result.add_error(
                    f"Logging stream {stream_index} custom auth requires 'headers' field"
                )
            elif not isinstance(auth["headers"], dict):
                self.result.add_error(
                    f"Logging stream {stream_index} custom auth headers must be a dictionary"
                )

    def _validate_overlord_config(self, overlord_config: Dict[str, Any]) -> None:
        """Validate overlord configuration according to SCHEMA_GUIDE.md."""
        if not isinstance(overlord_config, dict):
            self.result.add_error("Overlord configuration must be a dictionary")
            return

        # Allow any additional fields users might want to add for overlord configuration

        # Validate persona new
        if "persona" in overlord_config:
            if not isinstance(overlord_config["persona"], str):
                self.result.add_error("Overlord persona must be a string")

        # Validate overlord LLM configuration
        if "llm" in overlord_config:
            self._validate_overlord_llm_config(overlord_config["llm"])

        # Validate response configuration
        if "response" in overlord_config:
            self._validate_overlord_response_config(overlord_config["response"])

        # Validate workflow configuration
        if "workflow" in overlord_config:
            self._validate_overlord_workflow_config(overlord_config["workflow"])

        # Validate caching configuration
        if "caching" in overlord_config:
            self._validate_overlord_caching_config(overlord_config["caching"])

        # Validate clarification configuration
        if "clarification" in overlord_config:
            self._validate_overlord_clarification_config(overlord_config["clarification"])

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

        # Validate max_extraction_tokens
        if "max_extraction_tokens" in llm_config:
            tokens = llm_config["max_extraction_tokens"]
            if not isinstance(tokens, int) or tokens <= 0:
                self.result.add_error("overlord.llm.max_extraction_tokens must be a positive integer")

        # Validate settings
        if "settings" in llm_config:
            self._validate_llm_global_settings(llm_config["settings"])

    def _validate_overlord_clarification_config(self, clarification_config: Dict[str, Any]) -> None:
        """Validate overlord clarification configuration."""
        if not isinstance(clarification_config, dict):
            self.result.add_error("Overlord clarification configuration must be a dictionary")
            return

        # Validate max_questions
        if "max_questions" in clarification_config:
            max_q = clarification_config["max_questions"]
            if not isinstance(max_q, int) or max_q < 1:
                self.result.add_error("clarification.max_questions must be a positive integer")

        # Validate style
        if "style" in clarification_config:
            style = clarification_config["style"]
            valid_styles = ["conversational", "formal", "brief"]
            if style not in valid_styles:
                self.result.add_error(
                    f"clarification.style '{style}' invalid. Valid: {', '.join(valid_styles)}"
                )

    def _validate_overlord_workflow_config(self, workflow_config: Dict[str, Any]) -> None:
        """Validate overlord workflow configuration."""
        if not isinstance(workflow_config, dict):
            self.result.add_error("Overlord workflow configuration must be a dictionary")
            return

        # Validate core workflow settings
        if "auto_decomposition" in workflow_config:
            if not isinstance(workflow_config["auto_decomposition"], bool):
                self.result.add_error("workflow.auto_decomposition must be a boolean")

        if "plan_approval_threshold" in workflow_config:
            threshold = workflow_config["plan_approval_threshold"]
            if not isinstance(threshold, (int, float)) or threshold < 1 or threshold > 10:
                self.result.add_error("workflow.plan_approval_threshold must be a number between 1 and 10")

        # Validate complexity settings
        if "complexity_method" in workflow_config:
            method = workflow_config["complexity_method"]
            valid_methods = ["heuristic", "llm", "custom", "hybrid"]
            if method not in valid_methods:
                self.result.add_error(
                    f"workflow.complexity_method '{method}' invalid. Valid: {', '.join(valid_methods)}"
                )

        if "complexity_threshold" in workflow_config:
            threshold = workflow_config["complexity_threshold"]
            if not isinstance(threshold, (int, float)) or threshold < 1 or threshold > 10:
                self.result.add_error("workflow.complexity_threshold must be a number between 1 and 10")

        # Allow any additional workflow configuration fields for extensibility

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

        # Validate streaming
        if "streaming" in response_config:
            if not isinstance(response_config["streaming"], bool):
                self.result.add_error("response.streaming must be a boolean")

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
            if "key" not in auth_config:
                self.result.add_error(
                    f"A2A service {filename} api_key auth requires 'key' field"
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
            if "key" not in auth_config:
                self.result.add_error(f"{service_identifier} api_key auth requires 'key' field")
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
                self.result.add_error(f"{service_identifier} custom auth requires 'headers' field")
            elif not isinstance(auth_config["headers"], dict):
                self.result.add_error(
                    f"{service_identifier} custom auth headers must be a dictionary"
                )

    def _validate_inbound_auth_config(self, auth_config: Dict[str, Any]) -> None:
        """Validate inbound authentication configuration."""
        if not isinstance(auth_config, dict):
            self.result.add_error("A2A inbound auth must be a dictionary")
            return

        # Validate auth type
        auth_type = auth_config.get("type", "none")
        valid_auth_types = ["api_key", "bearer", "basic", "custom", "none"]

        if auth_type not in valid_auth_types:
            self.result.add_error(
                f"A2A inbound auth type '{auth_type}' invalid. "
                f"Valid types are: {valid_auth_types}"
            )
            return

        # Validate type-specific auth requirements
        if auth_type == "api_key":
            if "key" not in auth_config:
                self.result.add_error("A2A inbound api_key auth requires 'key' field")
            if "header" in auth_config and not isinstance(auth_config["header"], str):
                self.result.add_error("A2A inbound auth header must be a string")

        elif auth_type == "bearer":
            if "token" not in auth_config:
                self.result.add_error("A2A inbound bearer auth requires 'token' field")

        elif auth_type == "basic":
            required_basic_fields = ["username", "password"]
            for field in required_basic_fields:
                if field not in auth_config:
                    self.result.add_error(
                        f"A2A inbound basic auth requires '{field}' field"
                    )

        elif auth_type == "custom":
            if "headers" not in auth_config:
                self.result.add_error("A2A inbound custom auth requires 'headers' field")
            elif not isinstance(auth_config["headers"], dict):
                self.result.add_error(
                    "A2A inbound custom auth headers must be a dictionary"
                )

    def _validate_scheduler_config(self, scheduler_config: Dict[str, Any]) -> None:
        """Validate scheduler configuration."""
        if not isinstance(scheduler_config, dict):
            self.result.add_error("Scheduler configuration must be a dictionary")
            return

        # Validate enabled field (optional, defaults to true)
        if "enabled" in scheduler_config:
            enabled = scheduler_config["enabled"]
            if not isinstance(enabled, bool):
                self.result.add_error("Scheduler 'enabled' field must be a boolean")

        # Validate timezone field (optional, defaults to "UTC")
        if "timezone" in scheduler_config:
            timezone = scheduler_config["timezone"]
            if not isinstance(timezone, str) or not timezone.strip():
                self.result.add_error("Scheduler 'timezone' field must be a non-empty string")

        # Validate check_interval_minutes field (optional, defaults to 1)
        if "check_interval_minutes" in scheduler_config:
            interval = scheduler_config["check_interval_minutes"]
            if not isinstance(interval, int) or interval <= 0:
                self.result.add_error(
                    "Scheduler 'check_interval_minutes' must be a positive integer"
                )

        # Validate max_concurrent_jobs field (optional, defaults to 10)
        if "max_concurrent_jobs" in scheduler_config:
            max_jobs = scheduler_config["max_concurrent_jobs"]
            if not isinstance(max_jobs, int) or max_jobs <= 0:
                self.result.add_error("Scheduler 'max_concurrent_jobs' must be a positive integer")

        # Validate max_failures_before_pause field (optional, defaults to 3)
        if "max_failures_before_pause" in scheduler_config:
            max_failures = scheduler_config["max_failures_before_pause"]
            if not isinstance(max_failures, int) or max_failures <= 0:
                self.result.add_error(
                    "Scheduler 'max_failures_before_pause' must be a positive integer"
                )

    def _validate_runtime_config(self, runtime_config: Dict[str, Any]) -> None:
        """Validate runtime configuration."""
        if not isinstance(runtime_config, dict):
            self.result.add_error("Runtime configuration must be a dictionary")
            return

        # Validate built_in_mcps field (optional, defaults to true)
        if "built_in_mcps" in runtime_config:
            built_in_mcps = runtime_config["built_in_mcps"]

            # Support both boolean (simple mode) and list (granular mode)
            if isinstance(built_in_mcps, bool):
                # Simple mode - all on or all off
                pass
            elif isinstance(built_in_mcps, list):
                # Granular mode - validate each MCP name
                # Use dynamic registry or fallback to known MCPs
                valid_mcps = (
                    set(BUILTIN_MCP_REGISTRY.keys())
                    if BUILTIN_MCP_REGISTRY
                    else {"file-generation"}
                )
                # Add future planned MCPs for forward compatibility
                valid_mcps.update({"web-search", "database"})

                for i, mcp_name in enumerate(built_in_mcps):
                    if not isinstance(mcp_name, str):
                        self.result.add_error(f"Runtime built_in_mcps[{i}] must be a string")
                    elif mcp_name not in valid_mcps:
                        self.result.add_error(
                            f"Runtime built_in_mcps[{i}] has invalid value '{mcp_name}'. "
                            f"Valid values are: {', '.join(sorted(valid_mcps))}"
                        )
            else:
                self.result.add_error(
                    "Runtime 'built_in_mcps' must be either a boolean or a list of MCP names"
                )

    def _validate_server_config(self, server_config: Dict[str, Any]) -> None:
        """Validate server configuration."""
        if not isinstance(server_config, dict):
            self.result.add_error("Server configuration must be a dictionary")
            return

        # Validate host
        if "host" in server_config:
            host = server_config["host"]
            if not isinstance(host, str) or not host.strip():
                self.result.add_error("Server host must be a non-empty string")

        # Validate port
        if "port" in server_config:
            port = server_config["port"]
            if not isinstance(port, int) or port < 1 or port > 65535:
                self.result.add_error("Server port must be an integer between 1 and 65535")

        # Validate api_keys
        if "api_keys" in server_config:
            api_keys = server_config["api_keys"]
            if not isinstance(api_keys, dict):
                self.result.add_error("Server api_keys must be a dictionary")
            else:
                # Validate admin_key
                if "admin_key" in api_keys:
                    admin_key = api_keys["admin_key"]
                    if not isinstance(admin_key, str) or not admin_key.strip():
                        self.result.add_error("Server admin_key must be a non-empty string")

                # Validate client_key
                if "client_key" in api_keys:
                    client_key = api_keys["client_key"]
                    if not isinstance(client_key, str) or not client_key.strip():
                        self.result.add_error("Server client_key must be a non-empty string")


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


def validate_user_credentials_requirements(
    config: Dict[str, Any], secrets_manager: Optional[Any] = None
) -> None:
    """
    Validate that database is configured if user credentials are used (synchronous version).
    Also validates that USER_CREDENTIALS_* secrets exist for MCP servers.

    This function checks if any user credential placeholders (${{ user.credentials.* }})
    are used in the configuration and ensures that:
    1. Persistent database storage is configured when they are found
    2. For MCP servers, corresponding USER_CREDENTIALS_* secrets exist

    NOTE: This is the synchronous version. Use validate_user_credentials_requirements_async
    if calling from an async context.

    Args:
        config: The formation configuration dictionary to validate
        secrets_manager: Optional secrets manager to check for initialization credentials

    Raises:
        ValueError: If user credentials are used but database is not configured
                   or if USER_CREDENTIALS_* secrets are missing for MCP servers
        RuntimeError: If called from an async context (use async version instead)
    """
    # Check if we're in an async context
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError(
                "validate_user_credentials_requirements called from async context. "
                "Use validate_user_credentials_requirements_async instead."
            )
    except RuntimeError:
        # No event loop, we're in sync context - this is fine
        pass

    def contains_user_credentials(obj: Any) -> bool:
        """Recursively check if object contains user credential patterns."""
        if isinstance(obj, str):
            return bool(USER_CREDENTIAL_PATTERN.search(obj))
        elif isinstance(obj, dict):
            return any(contains_user_credentials(v) for v in obj.values())
        elif isinstance(obj, list):
            return any(contains_user_credentials(item) for item in obj)
        return False

    def find_user_credentials_in_mcp(obj: Any, found_credentials: set, path: str = "") -> None:
        """Recursively find all user credential patterns in MCP configurations."""
        extract_user_credential_placeholders(obj, found_credentials, path)

    # Check if any part of config uses user credentials
    if contains_user_credentials(config):
        # Ensure persistent memory is configured
        memory_config = config.get("memory", {})
        persistent = memory_config.get("persistent", {})

        # Check if persistent memory is configured using the current schema
        if not persistent or not persistent.get("connection_string"):
            raise ValueError(
                "User credentials (${{ user.credentials.* }}) require persistent database storage. "
                "Please configure memory.persistent with a connection_string in your formation."
            )

    # Check MCP servers for user credentials that need initialization secrets
    mcp_config = config.get("mcp", {})
    servers = list(mcp_config.get("servers", []))  # Create a copy for validation

    # Also check agent-level MCP servers (add to validation copy only)
    agents = config.get("agents", [])
    for agent in agents:
        if isinstance(agent, dict) and "mcp_servers" in agent:
            agent_servers = agent["mcp_servers"]
            if isinstance(agent_servers, list):
                servers.extend(agent_servers)  # Only extend the validation copy

    # Find all user credentials in MCP server configurations
    found_credentials = set()
    for server in servers:
        if isinstance(server, dict):
            server_id = server.get("id", "unknown")
            find_user_credentials_in_mcp(server, found_credentials, f"mcp_server[{server_id}]")

    # Check if we have corresponding USER_CREDENTIALS_* secrets
    if found_credentials and secrets_manager:
        try:

            async def check_secrets():
                await secrets_manager.initialize_encryption()
                available_secrets = await secrets_manager.list_secrets()
                return available_secrets

            # In sync context, use asyncio.run
            available_secrets = asyncio.run(check_secrets())

            # Check each found credential
            missing_secrets = []
            for service_name, location in found_credentials:
                initialization_secret = f"USER_CREDENTIALS_{service_name.upper()}"
                if initialization_secret not in available_secrets:
                    missing_secrets.append((service_name, initialization_secret, location))

            if missing_secrets:
                error_msg = "MCP servers require initialization credentials:\n"
                for service, secret, location in missing_secrets:
                    error_msg += f"\n  • {location} uses ${{{{ user.credentials.{service} }}}} but {secret} is missing."
                    error_msg += f"\n    To fix: python -m muxi.utils.secrets add {secret} <{service}_token>\n"

                raise ValueError(error_msg)

        except ValueError:
            # Re-raise our validation errors
            raise
        except Exception:
            # For other exceptions, just continue (secrets manager might not be initialized)
            pass


async def validate_user_credentials_requirements_async(
    config: Dict[str, Any], secrets_manager: Optional[Any] = None
) -> None:
    """
    Validate that database is configured if user credentials are used (asynchronous version).
    Also validates that USER_CREDENTIALS_* secrets exist for MCP servers.

    This function checks if any user credential placeholders (${{ user.credentials.* }})
    are used in the configuration and ensures that:
    1. Persistent database storage is configured when they are found
    2. For MCP servers, corresponding USER_CREDENTIALS_* secrets exist

    This is the async version for use in async contexts. Use validate_user_credentials_requirements
    for synchronous contexts.

    Args:
        config: The formation configuration dictionary to validate
        secrets_manager: Optional secrets manager to check for initialization credentials

    Raises:
        ValueError: If user credentials are used but database is not configured
                   or if USER_CREDENTIALS_* secrets are missing for MCP servers
    """

    def contains_user_credentials(obj: Any) -> bool:
        """Recursively check if object contains user credential patterns."""
        if isinstance(obj, str):
            return bool(USER_CREDENTIAL_PATTERN.search(obj))
        elif isinstance(obj, dict):
            return any(contains_user_credentials(v) for v in obj.values())
        elif isinstance(obj, list):
            return any(contains_user_credentials(item) for item in obj)
        return False

    def find_user_credentials_in_mcp(obj: Any, found_credentials: set, path: str = "") -> None:
        """Recursively find all user credential patterns in MCP configurations."""
        extract_user_credential_placeholders(obj, found_credentials, path)

    # Check if any user credentials are used
    if contains_user_credentials(config):
        # Get memory configuration
        memory = config.get("memory", {})
        persistent = memory.get("persistent", {})

        # Check if persistent memory is configured using the current schema
        if not persistent or not persistent.get("connection_string"):
            raise ValueError(
                "User credentials (${{ user.credentials.* }}) require persistent database storage. "
                "Please configure memory.persistent with a connection_string in your formation."
            )

    # Check MCP servers for user credentials that need initialization secrets
    mcp_config = config.get("mcp", {})
    servers = list(mcp_config.get("servers", []))  # Create a copy for validation

    # Also check agent-level MCP servers (add to validation copy only)
    agents = config.get("agents", [])
    for agent in agents:
        if isinstance(agent, dict) and "mcp_servers" in agent:
            agent_servers = agent["mcp_servers"]
            if isinstance(agent_servers, list):
                servers.extend(agent_servers)  # Only extend the validation copy

    # Find all user credentials in MCP server configurations
    found_credentials = set()
    for server in servers:
        if isinstance(server, dict):
            server_id = server.get("id", "unknown")
            find_user_credentials_in_mcp(server, found_credentials, f"mcp_server[{server_id}]")

    # Check if we have corresponding USER_CREDENTIALS_* secrets
    if found_credentials and secrets_manager:
        try:
            # In async context, use await directly
            await secrets_manager.initialize_encryption()
            available_secrets = await secrets_manager.list_secrets()

            # Check each found credential
            missing_secrets = []
            for service_name, location in found_credentials:
                initialization_secret = f"USER_CREDENTIALS_{service_name.upper()}"
                if initialization_secret not in available_secrets:
                    missing_secrets.append((service_name, initialization_secret, location))

            if missing_secrets:
                error_msg = "MCP servers require initialization credentials:\n"
                for service, secret, location in missing_secrets:
                    error_msg += f"\n  • {location} uses ${{{{ user.credentials.{service} }}}} but {secret} is missing."
                    error_msg += f"\n    To fix: python -m muxi.utils.secrets add {secret} <{service}_token>\n"

                raise ValueError(error_msg)

        except ValueError:
            # Re-raise our validation errors
            raise
        except Exception:
            # For other exceptions, just continue (secrets manager might not be initialized)
            pass


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
