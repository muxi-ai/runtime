"""
ActiveAgentsTracker - Ultra-simple agent activity tracking for safe removal.

This module implements the "delete when done" pattern for agent management,
tracking only which agents are currently busy to prevent removal of active agents.
"""

import asyncio
from typing import Set, List, Callable, Optional


class ActiveAgentsTracker:
    """Ultra-simple: just track which agents are currently busy"""

    def __init__(self):
        self.busy_agents: Set[str] = set()               # agent_ids currently handling requests
        self.pending_deletions: Set[str] = set()         # agent_ids marked for deletion
        self.overlord_shutting_down: bool = False        # overlord marked for shutdown
        self._lock = asyncio.Lock()

        # Callbacks for actual deletion (set by overlord)
        self._delete_agent: Optional[Callable[[str], None]] = None
        self._shutdown_overlord: Optional[Callable[[], None]] = None

    async def mark_agent_busy(self, agent_id: str):
        """Mark agent as busy handling a request."""
        async with self._lock:
            self.busy_agents.add(agent_id)

    async def mark_agent_idle(self, agent_id: str):
        """Mark agent as idle (finished request)."""
        async with self._lock:
            self.busy_agents.discard(agent_id)

            # Check if any pending deletions can now be executed
            await self._process_pending_deletions()

    async def mark_agent_for_deletion(self, agent_id: str):
        """Mark agent for deletion when no longer busy."""
        async with self._lock:
            self.pending_deletions.add(agent_id)
            await self._process_pending_deletions()

    async def mark_overlord_for_shutdown(self):
        """Mark overlord for shutdown when no busy agents."""
        async with self._lock:
            self.overlord_shutting_down = True
            await self._process_pending_deletions()

    def is_agent_busy(self, agent_id: str) -> bool:
        """Check if agent is currently busy."""
        return agent_id in self.busy_agents

    def can_accept_new_requests(self) -> bool:
        """Check if overlord can accept new requests."""
        return not self.overlord_shutting_down

    def get_available_agents(self, all_agent_ids: List[str]) -> List[str]:
        """Get agents that can handle new requests (not marked for deletion)."""
        return [aid for aid in all_agent_ids if aid not in self.pending_deletions]

    def get_busy_agents_count(self) -> int:
        """Get count of currently busy agents."""
        return len(self.busy_agents)

    def get_pending_deletions_count(self) -> int:
        """Get count of agents pending deletion."""
        return len(self.pending_deletions)

    def is_idle(self) -> bool:
        """Check if all agents are idle (no busy agents)."""
        return len(self.busy_agents) == 0

    async def _process_pending_deletions(self):
        """Process any agents/overlord ready for deletion."""
        # Check agents ready for deletion (not busy)
        agents_to_delete = []
        for agent_id in self.pending_deletions:
            if not self.is_agent_busy(agent_id):
                agents_to_delete.append(agent_id)

        # Remove agents that are no longer busy
        for agent_id in agents_to_delete:
            self.pending_deletions.remove(agent_id)
            await self._delete_agent_callback(agent_id)

        # Check if overlord can be shut down (no busy agents)
        if self.overlord_shutting_down and not self.busy_agents:
            await self._shutdown_overlord_callback()

    async def _delete_agent_callback(self, agent_id: str):
        """Actually delete the agent (callback to overlord)."""
        if self._delete_agent:
            await self._delete_agent(agent_id)

    async def _shutdown_overlord_callback(self):
        """Actually shutdown the overlord (callback to formation)."""
        if self._shutdown_overlord:
            await self._shutdown_overlord()

    def get_status_summary(self) -> dict:
        """Get summary of tracker status for debugging/monitoring."""
        return {
            'busy_agents_count': len(self.busy_agents),
            'busy_agents': list(self.busy_agents),
            'pending_deletions_count': len(self.pending_deletions),
            'pending_deletions': list(self.pending_deletions),
            'overlord_shutting_down': self.overlord_shutting_down,
            'is_idle': self.is_idle()
        }
