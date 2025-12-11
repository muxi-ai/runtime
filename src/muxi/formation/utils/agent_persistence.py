"""
Agent persistence utilities for Formation.

Handles saving and loading agent configurations to/from YAML files.
"""

import copy
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

import aiofiles
import aiofiles.os
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
    from ..formation import Formation  # noqa: E402

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

    # Check for path separators
    if any(sep in agent_id for sep in ('/', os.sep)):
        raise ValueError(f"Agent ID '{agent_id}' contains path separators which are not allowed")

    # Verify basename equals the original (prevents directory traversal attempts)
    if Path(agent_id).name != agent_id:
        raise ValueError(f"Agent ID '{agent_id}' appears to contain path traversal elements")

    # Check for existing file with any supported extension (.afs, .yaml, .yml)
    # Priority: .afs > .yaml > .yml (for existing files)
    agent_file_path = None
    for ext in [".afs", ".yaml", ".yml"]:
        candidate = agents_dir / f"{agent_id}{ext}"
        if candidate.exists():
            agent_file_path = candidate
            break

    # If no existing file found, default to .yaml for new files
    if agent_file_path is None:
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

        # Check if agent already exists in formation config BEFORE creating file
        if auto_load and formation:
            agents = formation.config.get("agents", [])
            existing_agent = next((a for a in agents if a.get("id") == agent_id), None)
            if existing_agent:
                raise ValueError(f"Agent with id '{agent_id}' already exists in formation")

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

        # Convert to YAML string first
        yaml_content = yaml.safe_dump(
            clean_config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            indent=2,
        )

        # Atomic write pattern to prevent data loss
        # Create temp file in same directory to ensure same filesystem
        agent_dir = os.path.dirname(agent_file_path)
        temp_fd, temp_path = tempfile.mkstemp(
            suffix='.tmp',
            prefix='.agent_',
            dir=agent_dir,
            text=True
        )

        try:
            # Close the file descriptor as we'll use aiofiles
            os.close(temp_fd)

            # Write to temporary file
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(yaml_content)
                await f.flush()
                # Ensure data is written to disk
                os.fsync(f.fileno())

            # Get original file stats to preserve permissions (if file exists)
            try:
                original_stats = os.stat(agent_file_path)
                # Preserve file permissions
                os.chmod(temp_path, original_stats.st_mode)
            except FileNotFoundError:
                # Original file doesn't exist, use default permissions
                pass

            # Atomically replace the original file
            # os.replace is atomic on POSIX systems and Windows
            os.replace(temp_path, agent_file_path)

        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except (OSError, FileNotFoundError):
                pass
            raise

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
                # With atomic write, the file has already been successfully written
                # No need to restore as the file update was completed before auto-reload
                logger.error(
                    f"Failed to auto-reload agent '{agent_id}' into formation after save to {agent_file_path}: {e}"
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

        # Find all config files (.afs, .yaml, .yml extensions)
        agent_files = []
        for file_path in agents_dir.iterdir():
            if file_path.is_file() and file_path.suffix in {".afs", ".yaml", ".yml"}:
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
