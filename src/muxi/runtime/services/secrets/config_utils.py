"""
Configuration utilities for secret restoration.

This module provides reusable functions for retrieving configuration items
with secrets properly restored from placeholders.
"""

from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from copy import deepcopy

if TYPE_CHECKING:
    from ...formation.formation import Formation  # noqa: E402


def get_config_item_with_secrets_restored(
    formation: "Formation", config_path: List[str], item_id: str, id_field: str = "id"
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """
    Get configuration item with secrets restored.

    Args:
        formation: Formation instance containing config and secret placeholders
        config_path: Path to the config array (e.g., ["agents"] or ["mcp", "servers"])
        item_id: ID of item to retrieve
        id_field: Field name containing the ID (default: "id")

    Returns:
        Tuple of (item_config_with_secrets_restored, item_index) or (None, None) if not found
    """
    # Avoid circular import by importing here
    from ...formation.server.secrets import restore_secret_placeholders

    # Navigate to the config array
    config_section = formation.config
    for path_part in config_path:
        if isinstance(config_section, dict):
            config_section = config_section.get(path_part, [])
        else:
            return None, None

    # Ensure we have a list
    if not isinstance(config_section, list):
        return None, None

    # Find item
    item_index = next(
        (i for i, item in enumerate(config_section) if item.get(id_field) == item_id), None
    )

    if item_index is None:
        return None, None

    # Get a deep copy of the item
    item = deepcopy(config_section[item_index])

    # Create a temporary config structure to apply placeholders
    # Build the nested structure based on config_path
    temp_config = {}
    current_level = temp_config
    for path_part in config_path[:-1]:
        current_level[path_part] = {}
        current_level = current_level[path_part]

    # Set the final array with our item
    if config_path:
        current_level[config_path[-1]] = [item]
    else:
        temp_config = [item]

    # Restore secrets
    temp_config = restore_secret_placeholders(temp_config, formation.secret_placeholders)

    # Extract the restored item
    restored_item = temp_config
    for path_part in config_path:
        restored_item = restored_item.get(path_part, {})

    if isinstance(restored_item, list) and len(restored_item) > 0:
        restored_item = restored_item[0]

    return restored_item, item_index


def get_agent_with_secrets_restored(
    formation: "Formation", agent_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get agent configuration with secrets restored.

    Args:
        formation: Formation instance containing config and secret placeholders
        agent_id: ID of agent to retrieve

    Returns:
        Agent configuration with secrets restored, or None if not found
    """
    item, _ = get_config_item_with_secrets_restored(formation, ["agents"], agent_id)

    return item
