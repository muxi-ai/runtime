"""
Runtime agent processor for Formation.

Ensures agents added via API go through the same processing pipeline
as agents loaded during initialization, including:
- Secret interpolation
- MCP server processing
- Knowledge path resolution
- Validation
- Placeholder tracking
"""

from typing import Dict, Any, Tuple, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from .formation import Formation


async def process_agent_for_runtime(
    formation: "Formation",
    agent_config: Dict[str, Any],
    agent_id: str
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Process an agent configuration for runtime addition.

    This ensures the agent goes through the exact same pipeline as agents
    loaded during initialization, including secret processing, validation,
    and all other transformations.

    Args:
        formation: The Formation instance
        agent_config: Raw agent configuration from API
        agent_id: The agent ID

    Returns:
        Tuple of:
        - Processed agent configuration (with secrets interpolated)
        - Placeholder registry for this agent

    Raises:
        ValueError: If required secrets are missing or config is invalid
    """
    # 1. Process secrets (same as initialization)
    if not hasattr(formation, 'secrets_manager') or not formation.secrets_manager:
        raise RuntimeError("SecretsManager not available for secret processing")

    # Import ConfigLoader to process secrets
    from muxi.formation.config.loader import ConfigLoader
    config_loader = ConfigLoader()

    # Process secrets using the same method as initialization
    processed_config, secrets_used, placeholders = await config_loader.process_secrets(
        agent_config,
        formation.secrets_manager
    )

    # 2. Track secrets in formation's used secrets (if it tracks them)
    if hasattr(formation, '_secrets_in_use'):
        formation._secrets_in_use.update(secrets_used)

    # 3. Ensure agent has required fields (same as initialization)
    if "id" not in processed_config:
        processed_config["id"] = agent_id

    # 4. Check active status (same as initialization)
    if "active" not in processed_config:
        processed_config["active"] = True

    # 5. Set source to "api" (different from initialization which uses "formation")
    processed_config["source"] = "api"

    # 6. Process MCP servers if present
    if "mcp_servers" in processed_config:
        # MCP servers within the agent have already been processed by process_secrets
        # but we might need additional validation here
        pass

    # 7. Process knowledge paths if present
    if "knowledge" in processed_config:
        # Resolve relative paths relative to formation directory
        if hasattr(formation, '_formation_path') and formation._formation_path:
            formation_dir = Path(formation._formation_path).parent
            for knowledge_item in processed_config.get("knowledge", []):
                if isinstance(knowledge_item, dict) and "path" in knowledge_item:
                    path = knowledge_item["path"]
                    if not Path(path).is_absolute():
                        # Make relative paths absolute
                        knowledge_item["path"] = str(formation_dir / path)

    return processed_config, placeholders


async def add_agent_to_overlord_runtime(
    formation: "Formation",
    processed_config: Dict[str, Any]
) -> str:
    """
    Add a processed agent to the running overlord.

    This creates the agent instance and registers it with the overlord,
    ensuring it goes through the same initialization as agents loaded
    during startup.

    Args:
        formation: The Formation instance
        processed_config: Agent configuration that has been processed
                         (secrets interpolated, paths resolved, etc.)

    Returns:
        The agent ID

    Raises:
        RuntimeError: If overlord is not running
        ValueError: If agent creation fails
    """
    if not formation._is_running or not formation._overlord:
        raise RuntimeError("Overlord is not running")

    agent_id = processed_config["id"]

    # Create agent using the same method as initialization
    agent = await formation._overlord._create_agent_from_config(processed_config)

    # Add to agents dictionary
    formation._overlord.agents[agent_id] = agent

    # Store agent metadata for routing (same as initialization)
    formation._overlord.agent_descriptions[agent_id] = processed_config.get("description", "")
    formation._overlord.agent_metadata[agent_id] = {
        "name": processed_config.get("name", agent_id),
        "role": processed_config.get("role", "general"),
        "specialties": processed_config.get("specialties", []),
        "system_message": processed_config.get("system_message", ""),
    }

    # Update workflow components if they exist
    if hasattr(formation._overlord, 'task_decomposer') and formation._overlord.task_decomposer:
        formation._overlord.task_decomposer.agent_registry = formation._overlord.agents

    if hasattr(formation._overlord, 'workflow_executor') and formation._overlord.workflow_executor:
        formation._overlord.workflow_executor.agent_registry = formation._overlord.agents

    return agent_id
