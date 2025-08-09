"""
Agent persistence utilities for Formation.

Handles saving and loading agent configurations to/from YAML files.
"""

import copy
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

import aiofiles
import yaml

# Import runtime processor functions at module level
# to avoid runtime import failures
try:
    from ..runtime_agent_processor import (
        add_agent_to_overlord_runtime,
        process_agent_for_runtime,
    )
    RUNTIME_IMPORTS_AVAILABLE = True
except ImportError as e:
    # Log the import error but allow module to load
    logging.warning(f"Failed to import runtime agent processor functions: {e}")
    RUNTIME_IMPORTS_AVAILABLE = False

if TYPE_CHECKING:
    from ..formation import Formation

# Get logger for this module
logger = logging.getLogger(__name__)


class AgentPersistenceError(Exception):
    """Raised when agent persistence operations fail."""

    pass


def _validate_and_sanitize_agent_id(agent_id: str, agents_dir: Path) -> Path:
    """
    Validate and sanitize agent_id to prevent directory traversal attacks.

    Args:
        agent_id: The agent ID to validate
        agents_dir: The resolved agents directory path

    Returns:
        Path: The validated and resolved agent file path

    Raises:
        ValueError: If agent_id contains unsafe characters or attempts directory traversal
    """
    # Check if agent_id is a string and not empty
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("Agent ID must be a non-empty string")

    # Define safe character pattern (alphanumeric, underscore, hyphen)
    safe_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
    if not safe_pattern.match(agent_id):
        raise ValueError(
            f"Agent ID '{agent_id}' contains unsafe characters. "
            "Only alphanumeric characters, underscores, and hyphens are allowed."
        )

    # Check for path separators (both Unix and Windows)
    if '/' in agent_id or '\\' in agent_id or os.sep in agent_id:
        raise ValueError(f"Agent ID '{agent_id}' contains path separators which are not allowed")

    # Verify basename equals the original (prevents directory traversal attempts)
    if Path(agent_id).name != agent_id:
        raise ValueError(f"Agent ID '{agent_id}' appears to contain path traversal elements")

    # Construct the full path
    agent_file_path = agents_dir / f"{agent_id}.yaml"

    # Resolve both paths to absolute paths
    resolved_agents_dir = agents_dir.resolve()
    resolved_agent_path = agent_file_path.resolve()

    # Verify the resolved path is within the agents directory using robust pathlib method
    # This is the most secure way to prevent path traversal attacks
    if not resolved_agent_path.is_relative_to(resolved_agents_dir):
        raise ValueError(
            f"Agent file path is not within the agents directory. "
            f"Resolved path: {resolved_agent_path}, Expected parent: {resolved_agents_dir}"
        )

    return resolved_agent_path


async def save_agent_to_file(
    agent_config: Dict[str, Any],
    formation_path: str,
    agents_subdir: str = "agents",
    formation: "Formation" = None,
    auto_load: bool = False,
) -> str:
    """
    Save an agent configuration to a YAML file.

    Args:
        agent_config: Agent configuration dictionary
        formation_path: Path to the formation file or directory
        agents_subdir: Subdirectory name for agents (default: "agents")
        formation: Formation instance (required if auto_load=True)
        auto_load: If True, automatically load the agent into formation config and overlord

    Returns:
        str: Path to the created file

    Raises:
        AgentPersistenceError: If the operation fails
        ValueError: If agent configuration is invalid or auto_load requirements not met
    """
    # Validate agent config
    agent_id = agent_config.get("id")
    if not agent_id:
        raise ValueError("Agent configuration missing 'id' field")

    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("Agent 'id' must be a non-empty string")

    # Validate auto_load requirements
    if auto_load and formation is None:
        raise ValueError("Formation instance required when auto_load=True")

    try:
        # Determine formation directory
        formation_path = Path(formation_path)
        if formation_path.is_file():
            formation_dir = formation_path.parent
        else:
            formation_dir = formation_path

        if not formation_dir.exists():
            raise AgentPersistenceError(f"Formation directory does not exist: {formation_dir}")

        # Create agents directory
        agents_dir = formation_dir / agents_subdir
        agents_dir.mkdir(exist_ok=True)

        # Validate and sanitize agent_id to prevent directory traversal
        agent_file_path = _validate_and_sanitize_agent_id(agent_id, agents_dir)

        # Prepare agent config for serialization
        # Remove any None values and ensure clean YAML output
        clean_config = _clean_config_for_yaml(agent_config)

        # Convert to YAML string first, then write asynchronously
        yaml_content = yaml.safe_dump(
            clean_config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            indent=2,
        )

        # Write to YAML file using exclusive creation mode to prevent race conditions
        # Mode "x" will raise FileExistsError if the file already exists, ensuring atomicity
        try:
            async with aiofiles.open(agent_file_path, "x", encoding="utf-8") as f:
                await f.write(yaml_content)
        except FileExistsError:
            raise ValueError(
                f"Agent file already exists: {agent_file_path.name}. "
                f"Use update_agent_file to modify existing agents."
            )

        # Auto-load into formation if requested
        if auto_load and formation:
            try:
                # Check if agent already exists in config
                agents = formation.config.get("agents", [])
                existing_agent = next((a for a in agents if a.get("id") == agent_id), None)

                if existing_agent:
                    # Agent already exists - this is a duplicate creation attempt
                    # Clean up the file we just created and raise error
                    try:
                        agent_file_path.unlink()
                    except OSError as e:
                        logger.warning(
                            f"Failed to clean up agent file after duplicate detection: {agent_file_path}. "
                            f"Error: {e}"
                        )
                    raise ValueError(f"Agent with id '{agent_id}' already exists")

                # Check if runtime imports are available
                if not RUNTIME_IMPORTS_AVAILABLE:
                    raise ImportError(
                        "Runtime agent processor functions are not available. "
                        "Cannot auto-load agent into formation."
                    )

                # Process agent (secrets, paths, validation, etc.)
                processed_config, placeholders = await process_agent_for_runtime(
                    formation, clean_config, agent_id
                )

                # Add processed config to formation
                formation.add_agent_to_config(processed_config)

                # Track placeholders if formation tracks them
                if formation.has_secret_placeholders():
                    # Add placeholders with proper path prefix for the new agent
                    agent_index = len(formation.config.get("agents", [])) - 1
                    for path, placeholder in placeholders.items():
                        adjusted_path = (
                            f"agents[{agent_index}].{path}" if path else f"agents[{agent_index}]"
                        )
                        formation.add_secret_placeholder(adjusted_path, placeholder)

                # If overlord is running, add the agent to it as well
                if formation.is_running and formation.get_overlord():
                    await add_agent_to_overlord_runtime(formation, processed_config)

            except ValueError:
                # Re-raise ValueError as-is (for duplicate detection, etc.)
                raise
            except Exception as e:
                # If auto-load fails for other reasons, clean up the file and raise
                try:
                    agent_file_path.unlink()
                except OSError as cleanup_error:
                    logger.warning(
                        f"Failed to clean up agent file after auto-load failure: {agent_file_path}. "
                        f"Error: {cleanup_error}"
                    )
                raise AgentPersistenceError(
                    f"Failed to auto-load agent '{agent_id}': {str(e)}"
                ) from e

        return str(agent_file_path)

    except (OSError, yaml.YAMLError) as e:
        raise AgentPersistenceError(f"Failed to save agent '{agent_id}' to file: {str(e)}") from e


def load_agent_from_file(agent_file_path: str) -> Dict[str, Any]:
    """
    Load an agent configuration from a YAML file.

    Args:
        agent_file_path: Path to the agent YAML file

    Returns:
        Dict[str, Any]: Agent configuration

    Raises:
        AgentPersistenceError: If the operation fails
        ValueError: If the file contains invalid data
    """
    try:
        agent_path = Path(agent_file_path)

        if not agent_path.exists():
            raise AgentPersistenceError(f"Agent file does not exist: {agent_file_path}")

        with open(agent_path, "r", encoding="utf-8") as f:
            agent_config = yaml.safe_load(f)

        if not isinstance(agent_config, dict):
            raise ValueError("Agent file must contain a YAML dictionary")

        # Validate required fields
        if "id" not in agent_config:
            raise ValueError("Agent configuration missing required 'id' field")

        return agent_config

    except (OSError, yaml.YAMLError) as e:
        raise AgentPersistenceError(f"Failed to load agent from file: {str(e)}") from e


async def update_agent_file(
    agent_id: str,
    updates: Dict[str, Any],
    formation_path: str,
    agents_subdir: str = "agents",
    formation: "Formation" = None,
    auto_reload: bool = False,
) -> str:
    """
    Update an agent's YAML file with partial data and optionally reload it.

    Args:
        agent_id: ID of the agent to update
        updates: Dictionary of fields to update
        formation_path: Path to the formation file or directory
        agents_subdir: Subdirectory name for agents (default: "agents")
        formation: Formation instance (required if auto_reload=True)
        auto_reload: If True, automatically reload the agent in formation and overlord

    Returns:
        str: Path to the updated file

    Raises:
        AgentPersistenceError: If the operation fails
        ValueError: If agent file doesn't exist or auto_reload requirements not met
    """
    # Validate auto_reload requirements
    if auto_reload and formation is None:
        raise ValueError("Formation instance required when auto_reload=True")

    try:
        # Determine formation directory
        formation_path = Path(formation_path)
        if formation_path.is_file():
            formation_dir = formation_path.parent
        else:
            formation_dir = formation_path

        agents_dir = formation_dir / agents_subdir

        # Validate and sanitize agent_id to prevent directory traversal
        agent_file_path = _validate_and_sanitize_agent_id(agent_id, agents_dir)

        # Check if agent file exists
        if not agent_file_path.exists():
            raise ValueError(f"Agent file does not exist: {agent_file_path}")

        # Load existing agent configuration
        existing_config = load_agent_from_file(str(agent_file_path))

        # Apply updates (deep merge)
        updated_config = _deep_merge(existing_config, updates)

        # Clean and save the updated configuration
        clean_config = _clean_config_for_yaml(updated_config)

        # Convert to YAML string first, then write asynchronously
        yaml_content = yaml.safe_dump(
            clean_config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            indent=2,
        )

        async with aiofiles.open(agent_file_path, "w", encoding="utf-8") as f:
            await f.write(yaml_content)

        # Auto-reload into formation if requested
        if auto_reload and formation:
            try:
                # Check if runtime imports are available
                if not RUNTIME_IMPORTS_AVAILABLE:
                    raise ImportError(
                        "Runtime agent processor functions are not available. "
                        "Cannot auto-reload agent in formation."
                    )

                # Process the full updated config (secrets, paths, validation, etc.)
                processed_config, placeholders = await process_agent_for_runtime(
                    formation, updated_config, agent_id
                )

                # Update in formation config
                formation.update_agent_in_config(agent_id, processed_config)

                # Update placeholders if formation tracks them
                if formation.has_secret_placeholders():
                    # Find the agent index
                    agents = formation.config.get("agents", [])
                    agent_index = next(
                        (i for i, a in enumerate(agents) if a.get("id") == agent_id), -1
                    )
                    if agent_index >= 0:
                        # Remove old placeholders for this agent
                        prefix = f"agents[{agent_index}]"
                        formation.remove_secret_placeholders_for_prefix(prefix)

                        # Add new placeholders
                        for path, placeholder in placeholders.items():
                            adjusted_path = (
                                f"agents[{agent_index}].{path}"
                                if path
                                else f"agents[{agent_index}]"
                            )
                            formation.add_secret_placeholder(adjusted_path, placeholder)

                # If overlord is running and agent is active, reload it
                overlord = formation.get_overlord()
                if overlord and processed_config.get("active", True):
                    # Remove the old agent and add the updated one
                    if agent_id in overlord.agents:
                        del overlord.agents[agent_id]

                    # Add the updated agent
                    await add_agent_to_overlord_runtime(formation, processed_config)

            except Exception as e:
                # If auto-reload fails, restore the original file
                try:
                    with open(agent_file_path, "w", encoding="utf-8") as f:
                        yaml.dump(
                            existing_config,
                            f,
                            default_flow_style=False,
                            sort_keys=False,
                            allow_unicode=True,
                            indent=2,
                        )
                except OSError as restore_error:
                    logger.error(
                        f"Failed to restore original file after auto-reload failure for agent '{agent_id}': "
                        f"{agent_file_path}. Error: {restore_error}. "
                        f"File may be in an inconsistent state."
                    )
                raise AgentPersistenceError(
                    f"Failed to auto-reload agent '{agent_id}': {str(e)}"
                ) from e

        return str(agent_file_path)

    except (OSError, yaml.YAMLError) as e:
        raise AgentPersistenceError(f"Failed to update agent '{agent_id}': {str(e)}") from e


def delete_agent_file(agent_id: str, formation_path: str, agents_subdir: str = "agents") -> bool:
    """
    Delete an agent YAML file.

    Args:
        agent_id: ID of the agent to delete
        formation_path: Path to the formation file or directory
        agents_subdir: Subdirectory name for agents (default: "agents")

    Returns:
        bool: True if file was deleted, False if it didn't exist

    Raises:
        AgentPersistenceError: If the deletion fails
    """
    try:
        # Determine formation directory
        formation_path = Path(formation_path)
        if formation_path.is_file():
            formation_dir = formation_path.parent
        else:
            formation_dir = formation_path

        # Construct agent file path
        agents_dir = formation_dir / agents_subdir

        # Validate and sanitize agent_id to prevent directory traversal
        agent_file_path = _validate_and_sanitize_agent_id(agent_id, agents_dir)

        if not agent_file_path.exists():
            return False

        agent_file_path.unlink()
        return True

    except OSError as e:
        raise AgentPersistenceError(
            f"Failed to delete agent file for '{agent_id}': {str(e)}"
        ) from e


def list_agent_files(formation_path: str, agents_subdir: str = "agents") -> list[str]:
    """
    List all agent YAML files in the agents directory.

    Args:
        formation_path: Path to the formation file or directory
        agents_subdir: Subdirectory name for agents (default: "agents")

    Returns:
        List[str]: List of agent file paths

    Raises:
        AgentPersistenceError: If the operation fails
    """
    try:
        # Determine formation directory
        formation_path = Path(formation_path)
        if formation_path.is_file():
            formation_dir = formation_path.parent
        else:
            formation_dir = formation_path

        agents_dir = formation_dir / agents_subdir

        if not agents_dir.exists():
            return []

        # Find all YAML files (both .yaml and .yml extensions)
        # Using glob pattern "*.y*ml" captures both .yaml and .yml in one pass
        agent_files = []
        for file_path in agents_dir.glob("*.y*ml"):
            if file_path.is_file():
                agent_files.append(str(file_path))

        return sorted(agent_files)

    except OSError as e:
        raise AgentPersistenceError(f"Failed to list agent files: {str(e)}") from e


def _clean_config_for_yaml(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean configuration dictionary for YAML serialization.

    Removes None values and ensures proper data types.

    Args:
        config: Configuration dictionary

    Returns:
        Dict[str, Any]: Cleaned configuration
    """
    cleaned = {}

    for key, value in config.items():
        if value is None:
            continue

        if isinstance(value, dict):
            cleaned_dict = _clean_config_for_yaml(value)
            if cleaned_dict:  # Only add non-empty dicts
                cleaned[key] = cleaned_dict
        elif isinstance(value, list):
            cleaned_list = []
            for item in value:
                if isinstance(item, dict):
                    cleaned_item = _clean_config_for_yaml(item)
                    if cleaned_item:
                        cleaned_list.append(cleaned_item)
                elif item is not None:
                    cleaned_list.append(item)
            if cleaned_list:  # Only add non-empty lists
                cleaned[key] = cleaned_list
        else:
            cleaned[key] = value

    return cleaned


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a deep merge of two dictionaries.

    Updates take precedence over base values. For nested dictionaries,
    the merge is recursive. Lists are replaced entirely.

    Args:
        base: Base dictionary
        updates: Updates to apply

    Returns:
        Dict[str, Any]: Merged dictionary
    """
    result = copy.deepcopy(base)

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = _deep_merge(result[key], value)
        else:
            # Replace the value (including lists)
            result[key] = value

    return result
