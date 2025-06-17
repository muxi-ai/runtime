"""
Buffer memory management for the Overlord.

This module handles all buffer memory operations including adding messages,
searching, and clearing buffer memory.
"""
from typing import Any, Dict, List, Optional

from ...services import observability


class BufferMemoryManager:
    """
    Manages buffer memory operations for the Overlord.

    This class encapsulates all buffer memory functionality that was previously
    embedded in the main Overlord class, providing a cleaner separation of concerns.
    """

    def __init__(self, overlord):
        """
        Initialize the buffer memory manager.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord

    async def add_to_buffer_memory(
        self,
        message: Any,
        metadata: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> bool:
        """
        Add a message to the overlord's buffer memory.

        This method stores a message in the short-term buffer memory, which maintains
        context for ongoing conversations. The buffer memory provides recent message
        history and context for agents during conversation.

        Args:
            message: The message to add. Can be text or a vector embedding.
                For text messages, if buffer_memory has an embedding model,
                it will automatically generate the embedding.
            metadata: Optional metadata to associate with the message.
                Useful for filtering during retrieval (e.g., by topic, importance).
            agent_id: Optional agent ID to include in metadata.
                Used to track which agent was involved with this message.

        Returns:
            True if added successfully, False if buffer_memory is not available
            or an error occurred during addition.
        """
        if not self.overlord.buffer_memory:
            return False

        # Add agent_id to metadata for context if provided
        full_metadata = metadata or {}
        if agent_id:
            full_metadata["agent_id"] = agent_id

        # Add to buffer memory (now async)
        try:
            await self.overlord.buffer_memory.add(message, metadata=full_metadata)
            #  Info - TODO: add observability
            # ConversationEvents.MEMORY_SHORT_TERM_UPDATED
            return True
        except Exception as e:
            #  Warning - TODO: add observability
            # ConversationEvents.MEMORY_SHORT_TERM_UPDATE_FAILED
            _ = e  # remove this after implementing observability
            return False

    async def search_buffer_memory(
        self,
        query: str,
        agent_id: Optional[str] = None,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search buffer memory for relevant information.

        Args:
            query: The query text to search for
            agent_id: Optional agent ID to filter results by
            k: The number of results to return
            filter_metadata: Additional metadata filters to apply

        Returns:
            List of relevant memory items from buffer memory
        """
        if not self.overlord.buffer_memory:
            return []

        # Prepare metadata filter
        full_filter = filter_metadata or {}
        if agent_id:
            full_filter["agent_id"] = agent_id

        try:
            # Emit memory search started event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_SHORT_TERM_LOOKUP,
                level=observability.EventLevel.DEBUG,
                data={
                    "query": query[:100],
                    "memory_type": "buffer",
                    "k": k,
                    "agent_id": agent_id,
                },
                description="Starting buffer memory search",
            )

            # Use updated search method (now async)
            buffer_results = await self.overlord.buffer_memory.search(
                query=query, limit=k, filter_metadata=full_filter
            )

            # Emit memory search completed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_SHORT_TERM_RETRIEVED,
                level=observability.EventLevel.DEBUG,
                data={
                    "query": query[:100],
                    "memory_type": "buffer",
                    "results_count": len(buffer_results),
                },
                description=(f"Buffer memory search completed: {len(buffer_results)} results"),
            )

            # Convert to standard format
            results = []
            for item in buffer_results:
                results.append(
                    {
                        "text": item["content"],
                        "metadata": item["metadata"],
                        "distance": 1.0 - item["score"],  # Convert score to distance
                        "source": "buffer",
                    }
                )

            return results

        except Exception as e:
            #  Warning - TODO: add observability
            # ConversationEvents.MEMORY_SHORT_TERM_RETRIEVAL_FAILED
            _ = e  # remove this after implementing observability
            return []

    async def clear_buffer_memory(
        self,
        agent_id: Optional[str] = None,
    ) -> None:
        """
        Clear buffer memory for the specified agent.

        Args:
            agent_id: Optional agent ID to filter by.
                Only clears memories associated with this specific agent.
        """
        if not self.overlord.buffer_memory:
            return

        filter_metadata = {}
        if agent_id:
            filter_metadata["agent_id"] = agent_id

        try:
            self.overlord.buffer_memory.clear(
                filter_metadata=filter_metadata if filter_metadata else None
            )
        except Exception as e:
            #  Buffer memory clear error - TODO: add observability
            #  MEMORY_SHORT_TERM_LOOKUP
            _ = e  # remove this after implementing observability

    async def add_message_to_buffer(
        self,
        content: str,
        role: str,
        timestamp: float,
        agent_id: str,
    ) -> None:
        """
        Add a message to buffer memory with standard metadata.

        Args:
            content: The message content to store
            role: The role of the message sender (e.g., 'user', 'assistant')
            timestamp: The timestamp of the message as a float (unix timestamp)
            agent_id: The ID of the agent involved in the conversation
        """
        if self.overlord.buffer_memory:
            metadata = {"role": role, "timestamp": timestamp, "agent_id": agent_id}
            await self.overlord.buffer_memory.add(content, metadata=metadata)
