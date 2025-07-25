"""
User context management for the Overlord.

This module handles user context memory operations including getting, adding,
and clearing user-specific context information.
"""

from typing import Any, Dict, List, Optional

from ...services.memory.memobase import Memobase


class UserContextManager:
    """
    Manages user context operations for the Overlord.

    This class encapsulates all user context functionality that was previously
    embedded in the main Overlord class, providing a cleaner separation of concerns.
    """

    def __init__(self, overlord):
        """
        Initialize the user context manager.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord

    async def get_user_context(
        self, user_id: Any, agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get context memory for a specific user.

        This method retrieves structured information about a user, such as preferences,
        facts, and other contextual details that have been stored in the memory system.
        It requires multi-user support to be enabled (Memobase).

        Args:
            user_id: The user's ID to get context for. This identifies the specific
                user whose context should be retrieved.
            agent_id: Optional agent ID to scope the context. Currently not used,
                but maintained for API consistency.

        Returns:
            Dictionary of user context information. The structure depends on what
            has been stored for the user, but typically includes sections like:
            - preferences: User UI/interaction preferences
            - personal_info: User personal details
            - facts: Known facts about the user

            Returns an empty dictionary if no context exists or if multi-user
            support is not enabled.
        """
        if not self.overlord.is_multi_user or not isinstance(
            self.overlord.long_term_memory, Memobase
        ):
            return {}

        # Use external_user_id directly - no conversion needed
        context = await self.overlord.long_term_memory.get_user_context(external_user_id=user_id)

        #  Info - TODO: add observability
        # ConversationEvents.MEMORY_LONG_TERM_RETRIEVED
        # Retrieved user context memory for user: '{user_id}'

        return context

    async def add_user_context(
        self,
        user_id: Any,
        knowledge: Dict[str, Any],
        source: str = "manual_input",
        importance: float = 0.9,
        agent_id: Optional[str] = None,
    ) -> List[str]:
        """
        Add context memory for a specific user.

        This method stores structured information about a user, such as preferences,
        facts, and other contextual details. It requires multi-user support to be
        enabled (Memobase).

        Args:
            user_id: The user's ID. This identifies the specific user whose
                context is being updated.
            knowledge: Dictionary of information to store. Can contain nested
                structures like preferences, personal information, etc.
            source: Where this knowledge came from (e.g., "manual_input",
                "conversation", "profile_update").
            importance: Importance score (0.0 to 1.0). Higher values indicate
                more important information.
            agent_id: Optional agent ID that provided this information.
                Currently not used, but maintained for API consistency.

        Returns:
            List of memory IDs for stored information. These can be used to
            reference the specific memory items later.
            Returns an empty list if multi-user support is not enabled.
        """
        if not self.overlord.is_multi_user or not isinstance(
            self.overlord.long_term_memory, Memobase
        ):
            return []

        # Use external_user_id directly - no conversion needed
        context = await self.overlord.long_term_memory.add_user_context(
            external_user_id=user_id, knowledge=knowledge, source=source, importance=importance
        )

        #  Info - TODO: add observability
        # ConversationEvents.MEMORY_LONG_TERM_ENHANCED

        return context

    async def clear_user_context(
        self, user_id: Any, keys: Optional[List[str]] = None, agent_id: Optional[str] = None
    ) -> bool:
        """
        Clear context memory for a specific user.

        This method removes stored information about a user from the memory system.
        It requires multi-user support to be enabled (Memobase).

        Args:
            user_id: The user's ID. This identifies the specific user whose
                context should be cleared.
            keys: Optional list of specific keys to clear. If provided, only
                clears those specific keys rather than all context.
                Example: ["preferences.theme", "location"]
            agent_id: Optional agent ID that's clearing the memory.
                Currently not used, but maintained for API consistency.

        Returns:
            True if successful, False otherwise (including if multi-user
            support is not enabled).
        """
        if not self.overlord.is_multi_user or not isinstance(
            self.overlord.long_term_memory, Memobase
        ):
            return False

        # Use external_user_id directly - no conversion needed
        context = await self.overlord.long_term_memory.clear_user_context(
            external_user_id=user_id, keys=keys
        )

        #  Info - TODO: add observability
        # ConversationEvents.MEMORY_WORKING_UPDATED

        return context
