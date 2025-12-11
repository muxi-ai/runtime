# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Configuration Loader - External Config Processing
# Description:  Utilities for loading and processing configuration files
# Role:         Provides configuration loading from YAML/JSON files
# Usage:        Used to load agent configurations from external files
# Author:       Muxi Framework Team
#
# The Configuration Loader module provides utilities for loading and processing
# external configuration files for the Muxi Framework. It supports YAML and JSON
# formats, handles GitHub Actions-style secrets interpolation, and normalizes
# configuration structures to ensure consistent format.
#
# Key features include:
#
# 1. File Loading
#    - Support for YAML and JSON formats
#    - Path resolution and error handling
#    - Format auto-detection based on file extension
#
# 2. Secrets Variable Processing
#    - Replace ${{ secrets.SECRET_NAME }} patterns with actual secret values
#    - Formation-level secrets management with encryption
#
# 3. Configuration Normalization
#    - Converts simplified config formats to standardized structure
#    - Provides sensible defaults for missing values
#
# Example usage:
#
#   from .config.loader import ConfigLoader
#   from .secrets import SecretsManager
#
#   # Load and process a configuration file
#   loader = ConfigLoader()
#   secrets_manager = SecretsManager(formation_dir)
#   config = loader.load_and_process("path/to/config.afs", secrets_manager)
# =============================================================================

import re
import json
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class ConfigLoader:
    """
    Load and process configuration files for the Muxi Framework.

    This class provides utilities for loading configuration files in YAML or JSON
    format, processing GitHub Actions-style secrets within those configurations,
    and normalizing the configuration structure to ensure consistency across the
    framework.
    """

    @staticmethod
    def load(path: str) -> Dict[str, Any]:
        """
        Load a configuration file from the given path.

        This method detects the file format based on extension and loads the
        configuration using the appropriate parser. It supports AFS/YAML (.afs, .yaml, .yml)
        and JSON (.json) formats.

        Args:
            path: Path to the configuration file (YAML or JSON)

        Returns:
            Dict[str, Any]: The loaded configuration as a dictionary

        Raises:
            ValueError: If the file format is not supported
            FileNotFoundError: If the file does not exist
        """
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(file_path, "r") as f:
            content = f.read()

            if file_path.suffix.lower() in [".afs", ".yaml", ".yml"]:
                return yaml.safe_load(content)

            elif file_path.suffix.lower() == ".json":
                return json.loads(content)

            else:
                raise ValueError(
                    f"Unsupported file format: {file_path.suffix}. "
                    "Supported formats: .afs, .yaml, .yml, .json"
                )

    @staticmethod
    async def process_secrets(
        config: Dict[str, Any], secrets_manager: Optional[Any] = None
    ) -> tuple[Dict[str, Any], set[str], Dict[str, str]]:
        """
        Process secrets variables in the configuration and track secrets in use.

        Replaces ${{ secrets.SECRET_NAME }} patterns in string values with the
        corresponding secret values from the SecretsManager. This allows for
        secure, encrypted secrets management at the formation level.

        Args:
            config: The configuration dictionary to process
            secrets_manager: SecretsManager instance for retrieving secrets

        Returns:
            Tuple of:
            - Dict[str, Any]: The processed configuration with secrets replaced
            - set[str]: Set of secret names that are in use
            - Dict[str, str]: Registry mapping paths to original placeholder values

        Raises:
            ValueError: If a required secret is not found
        """
        secrets_in_use = set()
        placeholder_registry = {}

        async def replace_secrets(obj: Any, path: str = "") -> Any:
            if isinstance(obj, str):
                # Find all ${{ secrets.SECRET_NAME }} patterns (whitespace tolerant)
                secret_pattern = r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}"
                matches = re.findall(secret_pattern, obj)
                result = obj

                # Track all secrets in use
                for secret_name in matches:
                    secrets_in_use.add(secret_name)

                # Also find user.credentials patterns and track them as USER_CREDENTIALS_X
                user_cred_pattern = r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}"
                user_cred_matches = re.findall(user_cred_pattern, obj)
                for cred_name in user_cred_matches:
                    # Track USER_CREDENTIALS_X secret as being in use
                    secrets_in_use.add(f"USER_CREDENTIALS_{cred_name.upper().replace('-', '_')}")

                # Check if this string contains any secret patterns
                has_secrets = bool(matches) or bool(user_cred_matches)

                # If this string contains secrets, store the original placeholder in registry
                if has_secrets and path:
                    placeholder_registry[path] = obj

                # Only process secrets if a secrets manager is provided
                if secrets_manager is not None:
                    # Replace each pattern with the secret value
                    for secret_name in matches:
                        try:
                            secret_value = await secrets_manager.get_secret(secret_name)
                            if secret_value is None:
                                raise ValueError(f"Secret '{secret_name}' not found in SecretsManager")

                            # Replace the pattern with the secret value
                            pattern = rf"\$\{{\{{\s*secrets\.{secret_name}\s*\}}\}}"
                            result = re.sub(pattern, secret_value, result)

                        except Exception as e:
                            raise ValueError(f"Failed to retrieve secret '{secret_name}': {str(e)}") from e

                return result
            elif isinstance(obj, dict):
                result = {}
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    result[k] = await replace_secrets(v, new_path)
                return result
            elif isinstance(obj, list):
                result = []
                for i, item in enumerate(obj):
                    new_path = f"{path}[{i}]"
                    result.append(await replace_secrets(item, new_path))
                return result
            else:
                return obj

        processed_config = await replace_secrets(config)
        return processed_config, secrets_in_use, placeholder_registry

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> None:
        """
        Validate the configuration.

        Checks that the configuration has required fields and that their values
        are of the expected types. Raises ValueError if validation fails.

        Args:
            config: The configuration dictionary to validate

        Raises:
            ValueError: If the configuration is invalid or missing required fields
        """
        # Required fields
        if not config.get("name"):
            raise ValueError("Missing required field: name")

        # Model validation
        model = config.get("model", {})
        if not model.get("provider"):
            raise ValueError("Missing required field: model.provider")
        if not model.get("model"):
            raise ValueError("Missing required field: model.model")

        # Agent metadata validation
        if "description" in config and not isinstance(config["description"], str):
            raise ValueError("Invalid field: description must be a string")
        if "system_message" in config and not isinstance(config["system_message"], str):
            raise ValueError("Invalid field: system_message must be a string")

        # Memory validation - simpler now as we already normalized it
        memory = config.get("memory", {})
        if not isinstance(memory, dict):
            raise ValueError("Invalid field: memory must be an object")

        # Buffer memory validation
        buffer = memory.get("buffer", {})
        if not isinstance(buffer, dict):
            raise ValueError("Invalid field: memory.working must be an object")

        # Long-term memory validation
        long_term = memory.get("long_term", {})
        if not isinstance(long_term, dict):
            raise ValueError("Invalid field: memory.long_term must be an object")

        # Tools validation
        tools = config.get("tools", [])
        if not isinstance(tools, list):
            raise ValueError("Invalid field: tools must be an array")

        # MCP servers validation
        mcp_servers = config.get("mcp_servers", [])
        if not isinstance(mcp_servers, list):
            raise ValueError("Invalid field: mcp_servers must be an array")

        for server in mcp_servers:
            if not server.get("name"):
                raise ValueError("Missing required field: mcp_servers[].name")
            if not server.get("url") and not server.get("command"):
                raise ValueError(
                    "Missing required field: mcp_servers[].url or mcp_servers[].command"
                )

    async def load_and_process(
        self, path: str, secrets_manager: Optional[Any] = None
    ) -> tuple[Dict[str, Any], set[str], Dict[str, str]]:
        """
        Load, validate, and process a configuration file.

        This is the main method for loading configuration files, providing
        a complete workflow that:
        1. Loads the file
        2. Processes secrets variables
        3. Normalizes the configuration structure
        4. Validates the resulting configuration

        Args:
            path: Path to the configuration file
            secrets_manager: SecretsManager instance for secret interpolation

        Returns:
            Tuple of:
            - Dict[str, Any]: The processed configuration
            - set[str]: Set of secret names that are in use
            - Dict[str, str]: Registry mapping paths to original placeholder values

        Raises:
            ValueError: If the configuration is invalid
            FileNotFoundError: If the file does not exist
        """
        config = self.load(path)
        config, secrets_in_use, placeholder_registry = await self.process_secrets(config, secrets_manager)
        self.validate_config(config)
        return config, secrets_in_use, placeholder_registry
