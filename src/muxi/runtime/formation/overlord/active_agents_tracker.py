"""
ActiveAgentsTracker - Ultra-simple agent activity tracking for safe removal.

This module implements the "delete when done" pattern for agent management,
tracking only which agents are currently busy to prevent removal of active agents.

Enhanced with request-scoped exclusion for resilience fallback strategies.
"""

import asyncio
from typing import Set, List, Callable, Optional, Awaitable, Dict


class ActiveAgentsTracker:
    """Ultra-simple: just track which agents are currently busy"""

    def __init__(self):
        self.busy_agents: Set[str] = set()  # agent_ids currently handling requests
        self.pending_deletions: Set[str] = set()  # agent_ids marked for deletion
        self.overlord_shutting_down: bool = False  # overlord marked for shutdown
        self._lock = asyncio.Lock()

        # Request-scoped exclusions for resilience fallback
        self._request_exclusions: Dict[str, Set[str]] = {}  # request_id -> excluded agent_ids

        # Callbacks for actual deletion (set by overlord)
        self._delete_agent: Optional[Callable[[str], Awaitable[None]]] = None
        self._shutdown_overlord: Optional[Callable[[], Awaitable[None]]] = None

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

    async def is_agent_busy(self, agent_id: str) -> bool:
        """Check if agent is currently busy."""
        async with self._lock:
            return agent_id in self.busy_agents

    async def can_accept_new_requests(self) -> bool:
        """Check if overlord can accept new requests."""
        async with self._lock:
            return not self.overlord_shutting_down

    async def get_available_agents(
        self, all_agent_ids: List[str], request_id: Optional[str] = None
    ) -> List[str]:
        """Get agents that can handle new requests (not marked for deletion or excluded for request)."""
        async with self._lock:
            # Get request-specific exclusions if request_id provided
            excluded = self._request_exclusions.get(request_id, set()) if request_id else set()

            # Filter out pending deletions and request-specific exclusions
            return [
                aid
                for aid in all_agent_ids
                if aid not in self.pending_deletions and aid not in excluded
            ]

    async def get_busy_agents_count(self) -> int:
        """Get count of currently busy agents."""
        async with self._lock:
            return len(self.busy_agents)

    async def get_pending_deletions_count(self) -> int:
        """Get count of agents pending deletion."""
        async with self._lock:
            return len(self.pending_deletions)

    async def get_pending_deletions(self) -> List[str]:
        """Get list of agents pending deletion."""
        async with self._lock:
            return list(self.pending_deletions)

    async def is_idle(self) -> bool:
        """Check if all agents are idle (no busy agents)."""
        async with self._lock:
            return len(self.busy_agents) == 0

    async def exclude_agent_for_request(self, request_id: str, agent_id: str):
        """Exclude an agent for a specific request (used by resilience fallback)."""
        async with self._lock:
            if request_id not in self._request_exclusions:
                self._request_exclusions[request_id] = set()
            self._request_exclusions[request_id].add(agent_id)

    async def cleanup_request(self, request_id: str):
        """Clean up exclusions when request completes."""
        async with self._lock:
            if request_id in self._request_exclusions:
                del self._request_exclusions[request_id]

    async def get_request_exclusions(self, request_id: str) -> Set[str]:
        """Get the set of excluded agents for a specific request."""
        async with self._lock:
            return self._request_exclusions.get(request_id, set()).copy()

    async def _process_pending_deletions(self):
        """Process any agents/overlord ready for deletion."""
        # Check agents ready for deletion (not busy)
        # Note: We're already within the lock context when this is called,
        # so we access busy_agents directly to avoid deadlock
        agents_to_delete = []
        for agent_id in self.pending_deletions:
            if agent_id not in self.busy_agents:  # Direct access to avoid deadlock
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

    async def get_status_summary(self) -> dict:
        """Get summary of tracker status for debugging/monitoring."""
        async with self._lock:
            return {
                "busy_agents_count": len(self.busy_agents),
                "busy_agents": list(self.busy_agents),
                "pending_deletions_count": len(self.pending_deletions),
                "pending_deletions": list(self.pending_deletions),
                "overlord_shutting_down": self.overlord_shutting_down,
                "is_idle": len(self.busy_agents)
                == 0,  # Use direct check to avoid calling is_idle() within lock
                "request_exclusions_count": len(self._request_exclusions),
                "active_requests_with_exclusions": list(self._request_exclusions.keys()),
            }
