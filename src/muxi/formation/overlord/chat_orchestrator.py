"""
Chat orchestration system for the Overlord.

This module handles the main chat orchestration logic, including async/sync decision making,
streaming support, and workflow coordination.
"""

import asyncio
import time
from typing import Optional, Any, Union, Dict, AsyncGenerator, List
from ..background.request_tracker import RequestStatus, RequestState
from ...utils.id_generator import generate_nanoid
from ...services import observability
from ...datatypes.response import MuxiResponse
from ...services import streaming
from ...services.observability.context import (
    get_current_event_logger,
    get_current_request_context,
    set_event_logger,
    set_request_context,
)


class ChatOrchestrator:
    """
    Handles chat orchestration for the Overlord.

    This class encapsulates the main chat processing logic that was previously
    embedded in the main Overlord class, providing cleaner separation of concerns
    and better maintainability.
    """

    def __init__(self, overlord):
        """
        Initialize the chat orchestrator.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord

    async def chat(
        self,
        message: str,
        agent_name: Optional[str] = None,
        user_id: Any = None,
        session_id: Optional[str] = None,
        use_async: Optional[bool] = None,
        webhook_url: Optional[str] = None,
        threshold_seconds: Optional[float] = None,
        stream: Optional[bool] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[str, Dict[str, Any], AsyncGenerator[str, None]]:
        """
        Enhanced chat with async support for long-running agentic tasks and file attachments.

        This method provides the main chat interface for the overlord with intelligent
        async decision making. For requests that are expected to take a long time,
        it automatically switches to async mode and returns a request ID while
        processing continues in the background with webhook notification upon completion.

        Args:
            message: The user's message/request to process.
            agent_name: Optional specific agent to use. If None, overlord will
                select the most appropriate agent for the message.
            user_id: Optional user ID for multi-user support and context.
            use_async: Force async behavior. None=intelligent decision, True=force async,
                False=force sync. When None, uses time estimation to decide.
            webhook_url: Optional webhook URL for completion notification. Defaults
                to formation config if not provided.
            threshold_seconds: Optional threshold override for async decision. Defaults
                to formation config if not provided.
            stream: Optional streaming behavior. None=use formation config, True=force streaming,
                False=disable streaming. Only applies to sync processing.
            files: Optional list of file attachments. Each file should be a dict with:
                - filename: Name of the file
                - content: File content (text or bytes)
                - content_type: MIME type of the file
                - size: File size in bytes

        Returns:
            For sync processing without streaming: str with the agent's response content
            For sync processing with streaming: AsyncGenerator[str, None] yielding chunks
            For async processing: Dict with request_id, status, and processing info

        Note:
            When streaming is enabled (stream=True) and sync processing is used,
            this method returns an AsyncGenerator that yields response chunks as they
            arrive from the model. This preserves true streaming behavior and prevents
            memory issues from collecting all chunks before returning.
        """
        # User ID normalization and single-user mode conversion is now done
        # in the overlord's chat method before we get here, ensuring consistency
        # throughout the entire request lifecycle

        # Validate that user_id is provided in multi-user mode
        if self.overlord.is_multi_user and user_id is None:
            from ...datatypes.exceptions import OverlordError

            raise OverlordError(
                "user_id is required when formation is running in multi-user mode. "
                "Please provide a user_id parameter to identify the user making this request."
            )

        user_id = str(user_id).lower().strip() if user_id is not None else None

        # Check if there's a pending clarification for this session
        # If so, reuse its request_id for multi-turn clarification continuity
        pending_clarification = None
        if session_id:
            pending_clarification = await self.overlord._get_pending_clarification(session_id)

        if pending_clarification:
            # Reuse the existing request_id for multi-turn clarification
            stored_request_id = pending_clarification.get("request_id")
            if stored_request_id:
                request_id = stored_request_id
                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_VALIDATED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "session_id": session_id,
                        "reused_request_id": request_id,
                        "clarification_type": pending_clarification.get("type"),
                    },
                    description=f"Reusing request_id {request_id} for clarification response",
                )
            else:
                # Fallback if somehow request_id is missing
                request_id = f"req_{generate_nanoid()}"
        else:
            # Generate new request ID for new conversations
            request_id = f"req_{generate_nanoid()}"

        timestamp = time.time()

        # Start request tracking with observability
        with self.overlord.observability_manager.track_request(
            request_id=request_id,
            session_id=session_id,
            formation_id=self.overlord.formation_id,
            user_id=str(user_id) if user_id is not None else None,
        ) as context:
            # Note: REQUEST_RECEIVED is already emitted by observability_manager.track_request
            # So we don't need to emit it again here

            # Emit request validation event (basic validation)
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_VALIDATED,
                level=observability.EventLevel.INFO,
                data={
                    "message_valid": len(message.strip()) > 0,
                    "agent_exists": agent_name is None or agent_name in self.overlord.agents,
                    "has_files": files is not None,
                    "file_count": len(files) if files else 0,
                },
                description=f"Request {request_id} validated",
            )

            # Store user message in buffer memory immediately for all messages (fire-and-forget)
            # This ensures agents have access to full conversation context
            # asyncio.create_task(
            #     self._store_user_message_async(
            #         message=message,  # Store original message, not enhanced
            #         timestamp=timestamp,
            #         agent_name=agent_name,
            #         user_id=user_id,
            #         session_id=session_id,
            #         request_id=request_id,
            #     )
            # )

            # Process files if provided
            file_results = None
            if files:
                try:
                    # Process documents but don't return early - continue with normal flow
                    context = {"agent_name": agent_name} if agent_name else {}
                    context["session_id"] = session_id
                    context["request_id"] = request_id

                    doc_result = await self.overlord.process_document_upload(
                        attachments=files,
                        user_request=message,
                        context=context,
                        user_id=user_id,
                    )
                    file_results = f"[File Processing Result]: {doc_result}"
                except Exception as e:
                    # Log error and continue with original message
                    observability.observe(
                        event_type=observability.ConversationEvents.REQUEST_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={"error": str(e), "file_count": len(files)},
                        description=f"File processing failed for request {request_id}",
                    )
                    file_results = f"[File Processing]: Failed to process {len(files)} file(s)"

            # Store ORIGINAL user message in buffer memory (fire-and-forget)
            asyncio.create_task(
                self._store_user_message_async(
                    message=message,  # Store original message, not enhanced
                    timestamp=timestamp,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                )
            )

            # Enhance message with conversation context (memories + buffer)
            enhanced_message = await self._enhance_message_with_context(
                message=message,
                user_id=user_id,
                session_id=session_id,
                file_results=file_results,
            )

            # Extract user information from enhanced message (fire-and-forget)
            # Only if persistent memory is configured
            if (
                self.overlord.long_term_memory
                and user_id
                and user_id != "0"
                and self.overlord.auto_extract_user_info
            ):
                asyncio.create_task(
                    self._extract_user_information_async(
                        user_message=message,  # Original message for storage
                        agent_response="",  # No response yet
                        user_id=user_id,
                        agent_id=agent_name or "overlord",
                        enhanced_message=enhanced_message,  # Enhanced message for context
                    )
                )

            # Use provided values or formation defaults
            webhook_url = webhook_url or getattr(self.overlord, "async_webhook_url", None)
            threshold_seconds = threshold_seconds or getattr(
                self.overlord, "async_threshold_seconds", 30
            )

            # FAIL-SAFE: Force sync mode if no webhook URL is available
            if use_async is not False and webhook_url is None:
                observability.observe(
                    event_type=observability.ConversationEvents.GENERAL,
                    level=observability.EventLevel.WARNING,
                    data={
                        "forced_sync": True,
                        "reason": "no_webhook_url",
                        "use_async_requested": use_async,
                    },
                    description="Forcing sync mode: No webhook URL configured or provided",
                )
                use_async = False

            # Smart async/sync decision making
            should_use_async = await self._determine_async_mode(
                enhanced_message, agent_name, use_async, threshold_seconds
            )

            if should_use_async:
                # Mark this request as async to prevent premature completion
                self.overlord.observability_manager.mark_request_async(request_id)

                # Execute async request
                return await self._execute_async_request(
                    message=enhanced_message,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    webhook_url=webhook_url,
                    timestamp=timestamp,
                )

            # Always enable streaming for every request (debugging/monitoring)
            streaming.enable_streaming(request_id, user_id, session_id)

            # Determine streaming behavior
            use_streaming = (
                stream if stream is not None else getattr(self.overlord, "streaming", False)
            )

            # Execute sync request
            if use_streaming:
                # NEW: Fire-and-forget + return generator (replaces _process_streaming_chat)
                asyncio.create_task(
                    self._process_sync_chat(  # Same method, just fire-and-forget!
                        message=enhanced_message,
                        agent_name=agent_name,
                        user_id=user_id,
                        session_id=session_id,
                        request_id=request_id,
                        original_message=message,  # Pass original for extraction
                        use_async=use_async,
                        webhook_url=webhook_url,
                    )
                )

                # Return the stream generator
                async for event in self._stream_request(request_id, user_id, session_id):
                    yield event
            else:
                return await self._process_sync_chat(
                    message=enhanced_message,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    original_message=message,  # Pass original for extraction
                    use_async=use_async,
                    webhook_url=webhook_url,
                )

    async def _determine_async_mode(
        self,
        message: str,
        agent_name: Optional[str],
        use_async: Optional[bool],
        threshold_seconds: float,
    ) -> bool:
        """
        Determine whether to use async or sync processing.
        Simplified: Just return the explicit preference or default to sync.
        Workflow will make the actual decision based on time estimates.

        Args:
            message: The user's message
            agent_name: Optional specific agent
            use_async: Explicit async preference
            threshold_seconds: Time threshold for async decision

        Returns:
            True if should use async, False for sync
        """
        # If explicitly specified, use that
        if use_async is not None:
            return use_async

        # Default to sync for non-workflow requests
        # Workflow will make its own async decision based on task complexity
        return False

    async def _execute_async_request(
        self,
        message: str,
        agent_name: Optional[str],
        user_id: Any,
        session_id: Optional[str],
        request_id: str,
        webhook_url: Optional[str],
        timestamp: float,
    ) -> Dict[str, Any]:
        """
        Execute a request asynchronously.

        Args:
            message: The user's message
            agent_name: Optional specific agent
            user_id: Optional user ID
            session_id: Optional session ID
            request_id: Unique request ID
            webhook_url: Optional webhook URL
            timestamp: Request timestamp

        Returns:
            Dictionary with async request information
        """
        # Create initial request state
        initial_state = RequestState(
            id=request_id,
            status=RequestStatus.PROCESSING,
            start_time=timestamp,
            original_message=message,
            user_id=user_id,
            webhook_url=webhook_url,
            session_id=session_id,
        )

        # Track the request in RequestTracker
        await self.overlord.request_tracker.track_request(request_id, initial_state)

        # Create tracked background task for async execution
        observability.observe(
            event_type=observability.ConversationEvents.ASYNC_PROCESSING_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "request_id": request_id,
                "has_execute_method": hasattr(self.overlord, "_execute_async_request"),
                "has_create_method": hasattr(self.overlord, "_create_tracked_task"),
            },
            description=f"Creating async task for request {request_id}",
        )

        # Capture the current context to propagate to the async task
        current_logger = get_current_event_logger()
        current_context = get_current_request_context()

        # Create a wrapper that sets the context before executing
        async def _execute_with_context():
            if current_logger:
                set_event_logger(current_logger)
            if current_context:
                set_request_context(current_context)

            await self.overlord._execute_async_request(
                request_id=request_id,
                message=message,
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
            )

        self.overlord._create_tracked_task(
            _execute_with_context(),
            name=f"async_request_{request_id}",
        )

        # Return immediate response
        response = {
            "status": "processing",
            "request_id": request_id,
            "message": "Request is being processed asynchronously",
        }

        if webhook_url:
            response["webhook_url"] = webhook_url
            response["webhook_info"] = (
                "Results will be delivered to the webhook URL upon completion"
            )

        return response

    async def _process_sync_chat(
        self,
        message: str,
        agent_name: Optional[str],
        user_id: Any,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        original_message: Optional[str] = None,
        use_async: Optional[bool] = None,
        webhook_url: Optional[str] = None,
    ) -> Union[str, MuxiResponse]:
        """
        Process a chat request synchronously.

        Args:
            message: The user's message
            agent_name: Optional specific agent
            user_id: Optional user ID
            session_id: Optional session ID
            request_id: Optional request ID
            original_message: Original message before enhancement
            use_async: Explicit async preference to pass to workflow
            webhook_url: Webhook URL for async responses

        Returns:
            The response string or MuxiResponse with artifacts
        """
        # Delegate to overlord's sync processing method
        result = await self.overlord._process_sync_chat(
            message=message,
            agent_name=agent_name,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            use_async=use_async,
            webhook_url=webhook_url,
        )

        # Store overlord's final response in buffer memory (fire-and-forget)
        if result and hasattr(result, "content") and result.content:
            # Extract content for storage with error handling
            try:
                content_for_storage = (
                    result.content if isinstance(result.content, str) else str(result.content)
                )
            except Exception as e:
                # Log the error and use a safe fallback
                observability.observe(
                    event_type=observability.ErrorEvents.PROCESSING_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={
                        "error": str(e),
                        "content_type": type(result.content).__name__,
                        "content_repr": repr(result.content)[:100],  # Truncate for safety
                        "user_id": user_id,
                        "session_id": session_id,
                        "request_id": request_id,
                    },
                    description=f"Failed to extract content for storage: {str(e)}",
                )
                # Use repr as fallback to ensure we have a string
                content_for_storage = repr(result.content)

            # Always call storage with valid data
            asyncio.create_task(
                self._store_assistant_response_async(
                    content=content_for_storage,
                    timestamp=time.time(),
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                )
            )

        # ALWAYS return MuxiResponse objects
        from ...datatypes.response import MuxiResponse

        if isinstance(result, MuxiResponse):
            return result

        # If we didn't get a MuxiResponse, create one
        # This should rarely happen but ensures consistency
        if result and hasattr(result, "content"):
            return MuxiResponse(
                role="assistant",
                content=result.content if isinstance(result.content, str) else str(result.content),
                artifacts=result.artifacts if hasattr(result, 'artifacts') and result.artifacts else None
            )
        elif isinstance(result, str):
            return MuxiResponse(
                role="assistant",
                content=result
            )
        else:
            # Fallback for unexpected types
            return MuxiResponse(
                role="assistant",
                content=str(result) if result else ""
            )

    async def _store_user_message_async(
        self,
        message: str,
        timestamp: float,
        agent_name: Optional[str],
        user_id: Any,
        session_id: Optional[str],
        request_id: Optional[str],
    ) -> None:
        """Store user message in buffer memory without blocking."""
        try:
            await self.overlord.add_message_to_memory(
                content=message,
                role="user",
                timestamp=timestamp,
                agent_id=agent_name or "overlord",
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
            )

            # NOTE: We do NOT store raw user messages in long-term memory
            # Only extracted facts should be in long-term memory
            # Extraction happens separately in _extract_user_information_async
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "user_id": user_id,
                    "session_id": session_id,
                    "request_id": request_id,
                    "role": "user",
                    "operation": "store_user_message",
                },
                description=f"Failed to store user message in buffer memory: {str(e)}",
            )

    async def _store_assistant_response_async(
        self,
        content: str,
        timestamp: float,
        agent_name: Optional[str],
        user_id: Any,
        session_id: Optional[str],
        request_id: Optional[str],
    ) -> None:
        """Store assistant response in buffer memory without blocking."""
        try:
            await self.overlord.add_message_to_memory(
                content=content,
                role="assistant",
                timestamp=timestamp,
                agent_id=agent_name or "overlord",
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
            )

            # NOTE: We do NOT store assistant responses in long-term memory
            # Only user messages and extracted facts should be in long-term memory
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "user_id": user_id,
                    "session_id": session_id,
                    "request_id": request_id,
                    "role": "assistant",
                    "agent_name": agent_name,
                    "operation": "store_assistant_response",
                },
                description=f"Failed to store assistant response in buffer memory: {str(e)}",
            )

    async def _enhance_message_with_context(
        self,
        message: str,
        user_id: Any,
        session_id: Optional[str],
        file_results: Optional[str] = None,
    ) -> str:
        """
        Enhance user message with conversation context.

        Uses formation buffer configuration to retrieve and format context.
        Implements priority ordering: current request → file results → conversation context.

        Args:
            message: The current user message
            user_id: User identifier for filtering
            session_id: Optional session identifier for filtering
            file_results: Optional file processing results to include

        Returns:
            Enhanced message with context in priority order
        """
        # Check if message is already enhanced to prevent double enhancement
        if "=== CURRENT REQUEST ===" in message:
            # Message is already enhanced, return as-is
            return message

        # Get configuration from formation
        buffer_config = self.overlord.formation_config.get("memory", {}).get("buffer", {})
        buffer_size = buffer_config.get("size", 10)
        vector_search = buffer_config.get("vector_search", True)

        # 1. Get user profile from long-term memory (if available)
        user_profile_text = ""
        if self.overlord.is_multi_user and user_id and user_id != "0":
            try:
                user_context = await self.overlord.get_user_context(user_id=user_id)
                if user_context:
                    # Format user profile
                    profile_parts = []
                    for key, value in user_context.items():
                        if isinstance(value, dict) and "value" in value:
                            actual_value = value["value"]
                            profile_parts.append(f"- {key}: {actual_value}")
                        else:
                            profile_parts.append(f"- {key}: {value}")
                    if profile_parts:
                        user_profile_text = "\n".join(profile_parts)
            except Exception:
                # Continue without user profile
                pass

        # 2. Search for relevant long-term memories
        long_term_memories = ""
        if self.overlord.long_term_memory and user_id and user_id != "0":
            try:
                # Search long-term memory using current message as query
                # Search specific collections that are commonly used
                collections_to_search = [
                    "activities",
                    "preferences",
                    "user_identity",
                    "relationships",
                    "work_projects",
                    "conversations",
                    "default",
                ]
                lt_results = await self.overlord.persistent_memory_manager.search_long_term_memory(
                    query=message,
                    k=5,  # Get top 5 relevant memories
                    user_id=user_id,
                    collections=collections_to_search,
                )
                if lt_results:
                    # Format long-term memories
                    memory_parts = []
                    for mem in lt_results:
                        content = mem.get("text", "")
                        if content:
                            # Truncate very long memories
                            if len(content) > 200:
                                content = content[:197] + "..."
                            memory_parts.append(f"- {content}")
                    if memory_parts:
                        long_term_memories = "\n".join(memory_parts[:3])  # Limit to top 3
            except Exception:
                # Continue without long-term memories
                pass

        # 3. Search for recent conversation context (buffer memory)
        context_text = ""
        if self.overlord.buffer_memory_manager:
            try:
                # Build metadata filter
                metadata_filter = {"user_id": user_id}
                if session_id:
                    metadata_filter["session_id"] = session_id

                # Retrieve context based on vector_search setting
                if vector_search:
                    # Semantic search using current message as query
                    context_messages_list = (
                        await self.overlord.buffer_memory_manager.search_buffer_memory(
                            query=message,  # Use current message for semantic search
                            k=buffer_size,
                            filter_metadata=metadata_filter,
                        )
                    )
                else:
                    # Chronological retrieval
                    context_messages_list = (
                        await self.overlord.buffer_memory_manager.search_buffer_memory(
                            query="",  # Empty query for chronological order
                            k=buffer_size,
                            filter_metadata=metadata_filter,
                        )
                    )

                if context_messages_list:
                    # Format context with timestamps in REVERSE order (most recent first)
                    context_parts = []
                    for msg in reversed(context_messages_list):  # Reverse for most recent first
                        role = msg.get("metadata", {}).get("role", "unknown")
                        timestamp = msg.get("metadata", {}).get("timestamp", "")
                        content = msg.get("text", "")

                        # CRITICAL FIX: Skip messages that already contain context markers
                        # This prevents the matryoshka doll effect of nested contexts
                        if any(marker in content for marker in [
                            "=== CONVERSATION CONTEXT",
                            "=== CURRENT REQUEST ===",
                            "=== USER PROFILE ===",
                            "=== FILE PROCESSING RESULTS ===",
                            "=== RELEVANT MEMORIES ==="
                        ]):
                            # This is an enhanced message, extract just the actual content
                            # Look for the actual user/assistant message
                            if "=== CURRENT REQUEST ===" in content and "User:" in content:
                                # Extract just the user's actual message
                                lines = content.split("\n")
                                for i, line in enumerate(lines):
                                    if line.strip() == "=== CURRENT REQUEST ===" and i + 1 < len(lines):
                                        next_line = lines[i + 1].strip()
                                        if next_line.startswith("User:"):
                                            content = next_line[5:].strip()  # Remove "User: " prefix
                                            break
                            else:
                                # Skip this message entirely if we can't extract clean content
                                continue

                        if timestamp:
                            # Format timestamp for readability
                            import datetime

                            dt = datetime.datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%H:%M")
                            context_parts.append(f"[{time_str}] {role.capitalize()}: {content}")
                        else:
                            context_parts.append(f"{role.capitalize()}: {content}")

                    context_text = "\n".join(context_parts)
                    # Note: No truncation needed - LLM will naturally truncate oldest messages

            except Exception:
                # Log error but continue without context
                # Failed to retrieve conversation context - continue without it
                pass

        # Build enhanced message with priority ordering (most important first)
        enhanced_parts = []

        # 1. Current request (highest priority - always preserved)
        enhanced_parts.append("=== CURRENT REQUEST ===")
        enhanced_parts.append(f"User: {message}")
        enhanced_parts.append("")

        # 2. User profile (high priority - provides context about the user)
        if user_profile_text:
            enhanced_parts.append("=== USER PROFILE ===")
            enhanced_parts.append(user_profile_text)
            enhanced_parts.append("")

        # 3. File processing results (high priority)
        if file_results:
            enhanced_parts.append("=== FILE PROCESSING RESULTS ===")
            enhanced_parts.append(file_results)
            enhanced_parts.append("")

        # 4. Relevant long-term memories (medium priority)
        if long_term_memories:
            enhanced_parts.append("=== RELEVANT MEMORIES ===")
            enhanced_parts.append(long_term_memories)
            enhanced_parts.append("")

        # 5. Conversation context (lowest priority - truncated first if needed)
        if context_text:
            enhanced_parts.append("=== CONVERSATION CONTEXT (Most Recent First) ===")
            enhanced_parts.append(context_text)

        enhanced_message = "\n".join(enhanced_parts)

        return enhanced_message

    async def _extract_user_information_async(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        agent_id: str,
        enhanced_message: str = None,
    ) -> None:
        """Extract user information from conversation without blocking."""
        try:
            # Use enhanced message for extraction if provided, otherwise use original
            extraction_message = enhanced_message if enhanced_message else user_message

            await self.overlord.extract_user_information(
                user_message=extraction_message,  # Use enhanced for better context
                agent_response=agent_response,
                user_id=user_id,
                agent_id=agent_id,
            )
            # User information extraction completed
        except Exception as e:
            import traceback

            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "operation": "extract_user_information",
                    "traceback": traceback.format_exc(),
                },
                description=f"Failed to extract user information: {str(e)}",
            )

    async def _store_to_long_term_memory_async(
        self,
        content: str,
        role: str,
        timestamp: float,
        agent_id: str,
        user_id: Any,
    ) -> None:
        """Store message to long-term memory without blocking."""
        try:
            if (
                hasattr(self.overlord, "persistent_memory_manager")
                and self.overlord.persistent_memory_manager
            ):
                await self.overlord.persistent_memory_manager.add_message_to_long_term(
                    content=content,
                    role=role,
                    timestamp=timestamp,
                    agent_id=agent_id,
                    user_id=user_id,
                    collection="conversations",  # Add this line
                )
            # Message stored in long-term memory successfully
        except Exception:
            # Failed to store message in long-term memory
            pass

    async def _stream_request(self, request_id: str, user_id: str, session_id: str):
        """Internal streaming subscription (private method)"""
        from ...services.streaming import streaming_manager
        async for event in streaming_manager.subscribe(request_id, user_id, session_id):
            yield event
