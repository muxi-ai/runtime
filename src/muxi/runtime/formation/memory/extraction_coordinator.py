"""
User information extraction coordination for the Overlord.

This module handles the coordination of automatic user information extraction
from conversations, including triggering extraction and managing the process.
"""

from typing import Any

from ...services.memory.extractor import MemoryExtractor
from ...datatypes import observability


class ExtractionCoordinator:
    """
    Coordinates user information extraction for the Overlord.

    This class encapsulates all extraction functionality that was previously
    embedded in the main Overlord class, providing a cleaner separation of concerns.
    """

    def __init__(self, overlord):
        """
        Initialize the extraction coordinator.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord

    async def handle_user_information_extraction(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        agent_id: str,
        extraction_model=None,
    ) -> None:
        """
        Handle user information extraction from a conversation turn.

        This method coordinates the extraction of user information from conversations,
        managing the extraction process and delegating to the appropriate extractor.

        Args:
            user_message: The message to analyze (may be enhanced with context)
            agent_response: The agent's response content
            user_id: The user's ID (extraction skipped for user_id=0)
            agent_id: The agent's ID that handled the conversation
            extraction_model: Optional model to use for extraction
        """
        # Skip extraction for anonymous users in multi-user mode only
        # In single-user mode, user_id="0" is normal and expected
        if self.overlord.is_multi_user and (user_id == 0 or user_id == "0"):
            return

        # Skip if extraction is disabled
        if not self.overlord.auto_extract_user_info:
            return

        # Skip if no extractor is available
        if not hasattr(self.overlord, "extractor") or not self.overlord.extractor:
            return

        # Run extraction asynchronously to avoid blocking
        await self._run_extraction(
            user_message=user_message,
            agent_response=agent_response,
            user_id=user_id,
            agent_id=agent_id,
            extraction_model=extraction_model,
        )

    async def _run_extraction(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        agent_id: str,
        extraction_model=None,
    ) -> None:
        """
        Run the actual extraction process.

        This is an internal method that performs the extraction work,
        separated for better error handling and testing.

        Args:
            user_message: The message to analyze (may be enhanced with context)
            agent_response: The agent's response content
            user_id: The user's ID
            agent_id: The agent's ID that handled the conversation
            extraction_model: Optional model to use for extraction
        """
        try:
            # Use the provided extraction model or fall back to the overlord's default
            model_to_use = extraction_model or self.overlord.extraction_model

            # Create a temporary extractor if needed or use the existing one
            if hasattr(self.overlord, "extractor") and self.overlord.extractor:
                extractor = self.overlord.extractor
            else:
                # Create a temporary extractor for this extraction
                extractor = MemoryExtractor(
                    overlord=self.overlord,
                    extraction_model=model_to_use,
                    auto_extract=True,
                )

            # Perform the extraction using the enhanced message for better context
            # Note: The extractor will store the facts with the enhanced message
            # which provides better context for extraction
            await extractor.process_conversation_turn(
                user_message=user_message,  # Enhanced message for context
                agent_response=agent_response,
                user_id=user_id,
                message_count=1,  # We don't track message count here
            )

        except Exception as e:
            # Log the error but don't let it break the conversation flow
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": agent_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to extract data from conversation",
            )
            pass

    async def extract_user_information(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        agent_id: str,
        extraction_model=None,
        original_message: str = None,
    ) -> None:
        """
        Extract user information from a conversation turn.

        This is a public interface for triggering extraction, which delegates
        to the internal extraction handling logic.

        Args:
            user_message: The message to analyze (may be enhanced with context)
            agent_response: The agent's response content
            user_id: The user's ID (extraction skipped for user_id=0)
            agent_id: The agent's ID that handled the conversation
            extraction_model: Optional model to use for extraction
            original_message: The original user message (without enhancement)
        """
        await self.handle_user_information_extraction(
            user_message=user_message,
            agent_response=agent_response,
            user_id=user_id,
            agent_id=agent_id,
            extraction_model=extraction_model,
            original_message=original_message,
        )
