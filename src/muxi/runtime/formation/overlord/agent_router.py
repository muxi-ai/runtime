"""
Agent routing system for the Overlord.

This module handles intelligent agent selection and routing based on message
content, agent capabilities, and availability.
"""

import time
from typing import Any, Dict, Optional

from ...datatypes.exceptions import NoAvailableAgentsError


class AgentRouter:
    """
    Handles intelligent agent routing for the Overlord.

    This class encapsulates all agent routing functionality that was previously
    embedded in the main Overlord class, providing efficient and intelligent
    agent selection based on message content and agent capabilities.
    """

    def __init__(self, overlord):
        """
        Initialize the agent router.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord
        self._routing_cache: Dict[str, Any] = {}

    async def select_agent_for_message(self, message: str) -> str:
        """
        Select the most appropriate agent for a given message using intelligent routing.

        This method analyzes the content of a message and determines which agent is best
        suited to handle it, based on agent descriptions and capabilities. It uses the
        routing model to make this determination with intelligent fallbacks.

        Args:
            message: The message to route. This is the user's message or query
                that needs to be directed to an appropriate agent.

        Returns:
            The ID of the selected agent. This will always be a valid agent ID
            registered with this overlord.

        Raises:
            ValueError: If no agents are available in the overlord.
        """
        # If there are no agents, raise an error
        if not self.overlord.agents:
            raise NoAvailableAgentsError("No agents available")

        # Get available agents (not marked for deletion)
        available_agents = await self.overlord.active_agent_tracker.get_available_agents(
            list(self.overlord.agents.keys())
        )

        if not available_agents:
            raise NoAvailableAgentsError("No agents available for new requests")

        # If there's only one available agent, use it
        if len(available_agents) == 1:
            return available_agents[0]

        # Get caching configuration
        overlord_config = self.overlord.formation_config.get("overlord", {})
        config_section = overlord_config.get("config", {})
        caching_config = config_section.get("caching", {})

        caching_enabled = caching_config.get("enabled", True)  # Default: enabled
        cache_ttl = caching_config.get("ttl", 3600)  # Default: 3600 seconds (1 hour)

        # Check if we've seen this message before (use cached routing decision)
        if caching_enabled and message in self._routing_cache:
            cached_entry = self._routing_cache[message]

            # Check if cache entry is a simple string (old format) or dict with timestamp
            if isinstance(cached_entry, str):
                # Old format - assume it's still valid
                return cached_entry
            elif isinstance(cached_entry, dict):
                # New format with timestamp
                cached_time = cached_entry.get("timestamp", 0)
                cached_agent = cached_entry.get("agent_id")

                # Check if cache entry is still valid (within TTL)
                if time.time() - cached_time < cache_ttl:
                    return cached_agent
                else:
                    # Cache entry expired, remove it
                    del self._routing_cache[message]

        # Get routing model if not available
        routing_model = getattr(self.overlord, "routing_model", None)
        if routing_model is None:
            try:
                # Try to get text model from formation
                routing_model = await self.overlord.get_model_for_capability("text")
                #  Info - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_COMPLETED
            except Exception as e:
                # Fall back to intelligent selection if model creation fails
                #  Warning - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_FAILED
                _ = e  # remove this after implementing observability
                return await self._select_best_available_agent(message)

        try:
            # Create a prompt for the routing model
            prompt = self._create_routing_prompt(message)

            # Query the routing model
            response = await routing_model.generate_text(prompt)

            # Parse the response
            selected_agent_id = self._parse_routing_response(response)

            # If parsing failed or the agent doesn't exist, use intelligent fallback
            if selected_agent_id is None or selected_agent_id not in self.overlord.agents:
                selected_agent_id = await self._select_best_available_agent(message)
                #  Warning - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_COMPLETED
                # Routing model returned invalid agent. Selected best available agent
            else:
                #  Info - TODO: add observability
                # ConversationEvents.OVERLORD_ROUTING_COMPLETED
                _ = None  # remove this after implementing observability

            # Cache the result for future identical messages (if caching is enabled)
            if caching_enabled:
                self._routing_cache[message] = {
                    "agent_id": selected_agent_id,
                    "timestamp": time.time(),
                }

            return selected_agent_id

        except Exception as e:
            # If anything goes wrong, use intelligent selection
            #  Warning - TODO: add observability
            # ConversationEvents.OVERLORD_ROUTING_FAILED
            _ = e  # remove this after implementing observability
            return await self._select_best_available_agent(message)

    def _create_routing_prompt(self, message: str) -> str:
        """
        Create a prompt for the routing model to determine the appropriate agent.

        This internal method constructs a prompt that instructs the LLM to select
        the most appropriate agent based on the message content and available agents.

        Args:
            message: The message content to analyze

        Returns:
            A formatted prompt string for the routing model
        """
        # Build agent descriptions for the prompt
        agent_descriptions = []
        for agent_id in self.overlord.agents.keys():
            description = self.overlord.agent_descriptions.get(agent_id, "General purpose agent")
            agent_descriptions.append(f"- {agent_id}: {description}")

        agents_info = "\n".join(agent_descriptions)

        prompt = f"""You are a message routing system.
Your job is to select the most appropriate agent to handle a user's message.

Available agents:
{agents_info}

User message: "{message}"

Analyze the message and select the best agent. Consider:
- The subject matter and topic of the message
- The specific capabilities each agent offers
- Which agent would be most helpful for this type of request

Respond with only the agent ID (the text before the colon), nothing else."""

        return prompt

    async def _select_best_available_agent(self, message: str) -> str:
        """
        Select the best available agent using intelligent analysis.

        This method provides a fallback when the routing model is unavailable or fails.
        It uses simple heuristics to match message content with agent descriptions.

        Args:
            message: The message content to analyze

        Returns:
            The ID of the best available agent
        """
        available_agents = await self.overlord.active_agent_tracker.get_available_agents(
            list(self.overlord.agents.keys())
        )

        if not available_agents:
            raise NoAvailableAgentsError("No agents available for new requests")

        # If only one agent is available, use it
        if len(available_agents) == 1:
            return available_agents[0]

        # Simple keyword matching approach
        message_lower = message.lower()

        # Define keyword categories and their corresponding priorities
        keyword_priorities = {
            "code": ["code", "programming", "debug", "function", "script", "software"],
            "data": ["data", "analysis", "statistics", "csv", "database", "chart"],
            "research": ["research", "study", "academic", "paper", "literature"],
            "creative": ["write", "creative", "story", "content", "blog", "article"],
            "support": ["help", "support", "question", "assistance", "problem"],
        }

        # Score agents based on their descriptions and keyword matches
        agent_scores = {}
        for agent_id in available_agents:
            score = 0
            description = self.overlord.agent_descriptions.get(agent_id, "").lower()

            # Check for keyword matches between message and agent description
            for category, keywords in keyword_priorities.items():
                for keyword in keywords:
                    if keyword in message_lower and keyword in description:
                        score += 2  # Higher score for direct matches
                    elif keyword in message_lower or keyword in description:
                        score += 1  # Lower score for partial matches

            agent_scores[agent_id] = score

        # Select agent with highest score, or use default/first available if tied
        if agent_scores:
            best_agent = max(agent_scores.keys(), key=lambda x: agent_scores[x])
            if agent_scores[best_agent] > 0:
                return best_agent

        # Fallback to default agent or first available agent
        default_agent = getattr(self.overlord, "default_agent_id", None)
        if default_agent and default_agent in available_agents:
            return default_agent

        return available_agents[0]

    def _parse_routing_response(self, response: str) -> Optional[str]:
        """
        Parse the routing model response to extract the agent ID.

        This method attempts to extract a valid agent ID from the routing model's
        response, handling various response formats and potential issues.

        Args:
            response: The raw response from the routing model

        Returns:
            The extracted agent ID if valid, None otherwise
        """
        if not response:
            return None

        # Clean up the response
        response = response.strip()

        # Try to extract agent ID - handle various formats
        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Direct agent ID
            if line in self.overlord.agents:
                return line

            # Format: "agent_id" or 'agent_id'
            if (line.startswith('"') and line.endswith('"')) or (
                line.startswith("'") and line.endswith("'")
            ):
                agent_id = line[1:-1]
                if agent_id in self.overlord.agents:
                    return agent_id

            # Format: Agent: agent_id
            if ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    agent_id = parts[1].strip().strip("\"'")
                    if agent_id in self.overlord.agents:
                        return agent_id

            # Check if any part of the line matches an agent ID
            words = line.split()
            for word in words:
                word = word.strip(".,!?;\"'()[]{}")
                if word in self.overlord.agents:
                    return word

        return None

    def clear_routing_cache(self) -> None:
        """Clear the routing cache."""
        self._routing_cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get routing cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cache_size": len(self._routing_cache),
            "cache_entries": list(self._routing_cache.keys()),
        }
