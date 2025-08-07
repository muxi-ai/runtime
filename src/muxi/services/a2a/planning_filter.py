from typing import List, Dict, Any, Optional
from .hashing import AgentCardHasher


class PlanningAgentFilter:
    """
    Thin wrapper that combines existing MUXI components for cached agent filtering.
    Reuses RequestAnalyzer for task analysis and existing capability matching logic.
    """

    def __init__(self, overlord, config: Dict[str, Any]):
        """Initialize with existing overlord components and config."""
        self.overlord = overlord
        self.cache = overlord.a2a_cache_manager  # Extended A2ACacheManager
        self.request_analyzer = overlord.request_analyzer  # Reuse existing analyzer

        # Load filtering config
        self.threshold = config.get("threshold", 50)
        self.always_include_threshold = config.get("always_include_threshold", 0.8)
        self.min_relevance_score = config.get("min_relevance_score", 0.3)
        self.cache_ttl = config.get("cache_ttl", 1800)

    async def get_relevant_agents(
        self,
        task: str,
        all_agents: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        bypass_cache: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get relevant agents for planning with caching.

        Filters agents only if total count exceeds threshold.
        Respects agent-level allow_filtering setting.

        Args:
            task: The task to be planned
            all_agents: List of all available agent cards
            context: Optional context for the task
            bypass_cache: Force fresh analysis (for testing)

        Returns:
            List of relevant agent cards sorted by relevance
        """

        # Check if filtering is needed based on threshold
        if len(all_agents) <= self.threshold:
            return all_agents  # No filtering needed for small agent pools

        # Separate non-filterable agents
        non_filterable = []
        filterable = []

        for agent in all_agents:
            # Check agent-level filtering preference
            if not agent.get("allow_filtering", True):
                non_filterable.append(agent)
            else:
                filterable.append(agent)

        # If no agents are filterable, return all
        if not filterable:
            return all_agents

        # Generate hashes for caching
        task_hash = AgentCardHasher.hash_task(task, context)
        agents_hash = AgentCardHasher.hash_agent_collection(filterable)

        # Check cache unless bypassed
        if not bypass_cache:
            cached_ids = self.cache.get_filtered_agents(task_hash, agents_hash)
            if cached_ids:
                # Reconstruct filtered agents from cache
                agent_map = {agent["id"]: agent for agent in filterable}
                filtered = [agent_map[aid] for aid in cached_ids if aid in agent_map]
                # Combine non-filterable and filtered agents
                return non_filterable + filtered

        # Use existing RequestAnalyzer to analyze task
        analysis = await self.request_analyzer.analyze_request(task, context)

        # Extract capabilities from analysis
        required_capabilities = set()
        if hasattr(analysis, "identified_capabilities"):
            required_capabilities = set(analysis.identified_capabilities)
        if hasattr(analysis, "required_tools"):
            required_capabilities.update(analysis.required_tools)

        # Score filterable agents
        scored_agents = []
        for agent in filterable:
            score = self._score_agent_capabilities(agent, required_capabilities)

            # Include if above minimum threshold or high confidence
            if score >= self.always_include_threshold:
                scored_agents.append((agent, score))
            elif score >= self.min_relevance_score:
                scored_agents.append((agent, score))

        # Sort by score and combine with non-filterable
        scored_agents.sort(key=lambda x: x[1], reverse=True)
        filtered_agents = [agent for agent, _ in scored_agents]

        # Cache the filtered result
        agent_ids = [agent["id"] for agent in filtered_agents]
        self.cache.set_filtered_agents(task_hash, agents_hash, agent_ids, ttl=self.cache_ttl)

        # Return combined list: non-filterable + filtered
        return non_filterable + filtered_agents

    def _score_agent_capabilities(self, agent: Dict[str, Any], required_capabilities: set) -> float:
        """
        Simple capability scoring similar to existing WorkflowExecutor patterns.

        Args:
            agent: Agent card dictionary
            required_capabilities: Set of required capabilities from task analysis

        Returns:
            Relevance score between 0.0 and 1.0
        """
        if not required_capabilities:
            return 0.5  # Default score if no specific requirements

        agent_caps = set(agent.get("capabilities", []))
        agent_tools = set([t.get("name", "") for t in agent.get("tools", [])])

        # Count matches
        cap_matches = len(agent_caps & required_capabilities)
        tool_matches = len(agent_tools & required_capabilities)

        # Calculate score (similar to existing _calculate_capability_match patterns)
        total_matches = cap_matches + (tool_matches * 0.8)
        max_possible = len(required_capabilities)

        if max_possible == 0:
            return 0.5

        score = min(total_matches / max_possible, 1.0)

        # Bonus for internal agents (similar to existing preference)
        if agent.get("type") == "internal":
            score = min(score + 0.1, 1.0)

        return score
