"""
Chat orchestration system for the Overlord.

This module handles the main chat orchestration logic, including async/sync decision making,
streaming support, and workflow coordination.
"""

import asyncio
import time
import traceback
from typing import Optional, Any, Union, Dict, AsyncGenerator, List
from ..background.request_tracker import RequestStatus, RequestState
from ..background.cancellation import RequestCancelledException
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

    async def _create_stream_generator(
        self,
        enhanced_message: str,
        original_message: str,
        agent_name: Optional[str],
        user_id: str,
        session_id: str,
        request_id: str,
        use_async: Optional[bool],
        webhook_url: Optional[str],
        internal_user_id: Optional[int] = None,
        muxi_user_id: Optional[str] = None,
        bypass_workflow_approval: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Create a streaming generator that fires off processing and yields events.
        This function contains yield, making it a generator.
        """
        # Capture the current context to propagate to background task
        import contextvars
        current_context = contextvars.copy_context()

        # Fire-and-forget the processing with a delay to ensure subscription is ready
        async def delayed_process():
            # Set the request context for this background task
            from ...services.observability.context import set_request_context, RequestContext
            request_context = RequestContext(
                id=request_id,
                user_id=user_id,
                session_id=session_id,
                formation_id=getattr(self.overlord, 'formation_id', 'unknown'),
                internal_user_id=internal_user_id,
                muxi_user_id=muxi_user_id,
            )
            set_request_context(request_context)

            await asyncio.sleep(1.0)  # Give time for subscription to be established

            # Emit initial acknowledgment event (respects progress config)
            import random
            from ...services import streaming

            # Randomize the initial acknowledgment message
            initial_messages = [
                "One moment...",
                "Processing...",
                "Working on it...",
                "Got it, processing...",
                "Request received...",
                "On it...",
                "Let me check that for you...",
                "Looking into this...",
                "Let me see...",
                "One second..."
            ]

            # Use streaming.stream() to respect progress filtering
            streaming.stream(
                "progress",
                random.choice(initial_messages),
                stage="init",
                skip_rephrase=True
            )

            # Process the request - overlord._process_sync_chat will handle all streaming events
            result = await self._process_sync_chat(
                message=enhanced_message,
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                original_message=original_message,
                use_async=use_async,
                webhook_url=webhook_url,
                bypass_workflow_approval=bypass_workflow_approval,
            )

            # Note: The overlord._process_sync_chat method handles all streaming events:
            # - It emits "content" events with the actual response
            # - It emits "completed" event when done
            # - It disables streaming when finished
            # We don't need to duplicate that here.

            return result

        # Create task with context propagation (Python 3.10 compatible)
        def create_task_with_context():
            return asyncio.create_task(delayed_process())

        current_context.run(create_task_with_context)

        # Yield events from the stream
        async for event in self._stream_request(request_id, user_id, session_id):
            yield event

    async def chat(
        self,
        message: str,
        agent_name: Optional[str] = None,
        user_id: Any = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        use_async: Optional[bool] = None,
        webhook_url: Optional[str] = None,
        threshold_seconds: Optional[float] = None,
        stream: Optional[bool] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        bypass_workflow_approval: bool = False,
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
            session_id: Optional session ID for conversation grouping.
            request_id: Optional request ID for tracing/correlation. If not provided,
                a new one will be generated automatically.
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

        # Determine request_id: use provided -> clarification -> generate new
        if request_id:
            # Use provided request_id (e.g., from triggers or external callers)
            pass
        elif pending_clarification:
            # Reuse the existing request_id for multi-turn clarification
            stored_request_id = pending_clarification.get("request_id")
            if stored_request_id:
                request_id = stored_request_id
                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_ID_REUSED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "session_id": session_id,
                        "request_id": request_id,
                        "clarification_type": pending_clarification.get("type"),
                        "clarification_turn": "response",
                    },
                    description=(
                        "Reusing request_id for multi-turn clarification "
                        f"(type: {pending_clarification.get('type')})"
                    ),
                )
            else:
                # Fallback if somehow request_id is missing
                request_id = f"req_{generate_nanoid()}"
        else:
            # Generate new request ID for new conversations
            request_id = f"req_{generate_nanoid()}"

        timestamp = time.time()

        # Resolve user identifier to internal IDs (multi-identity support)
        # This maps external identifiers (email, Slack ID, etc.) to internal MUXI user
        internal_user_id = None
        muxi_user_id = None
        if user_id is not None:
            from ...utils.user_resolution import resolve_user_identifier

            # Use long_term_memory's db_manager if overlord's is not available
            db_mgr = self.overlord.db_manager or (
                self.overlord.long_term_memory.db_manager
                if self.overlord.long_term_memory else None
            )

            # Only resolve if db_manager is available
            if db_mgr is not None:
                internal_user_id, muxi_user_id = await resolve_user_identifier(
                    identifier=user_id,
                    formation_id=self.overlord.formation_id,
                    db_manager=db_mgr,
                    kv_cache=None,  # KV cache not yet implemented
                )
            else:
                # No database available - skip resolution
                # user_id will be used directly by downstream code
                internal_user_id = None
                muxi_user_id = None

        # Start request tracking with observability
        with self.overlord.observability_manager.track_request(
            request_id=request_id,
            session_id=session_id,
            formation_id=self.overlord.formation_id,
            user_id=str(user_id) if user_id is not None else None,
            internal_user_id=internal_user_id,
            muxi_user_id=muxi_user_id,
        ) as context:
            # Track request in RequestTracker for cancellation support
            initial_state = RequestState(
                id=request_id,
                status=RequestStatus.PROCESSING,
                start_time=timestamp,
                original_message=message,
                user_id=user_id,
                session_id=session_id,
            )
            await self.overlord.request_tracker.track_request(request_id, initial_state)

            # Note: REQUEST_RECEIVED is already emitted by observability_manager.track_request
            # So we don't need to emit it again here

            # Emit request validation event (basic validation)
            validation_start = time.time()
            message_valid = len(message.strip()) > 0
            agent_exists = agent_name is None or agent_name in self.overlord.agents
            has_files = files is not None
            file_count = len(files) if files else 0

            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_VALIDATED,
                level=observability.EventLevel.INFO,
                data={
                    "message_valid": message_valid,
                    "agent_exists": agent_exists,
                    "has_files": has_files,
                    "file_count": file_count,
                    "validation_checks_passed": message_valid and agent_exists,
                    "file_processing_required": has_files,
                    "validation_duration_ms": (time.time() - validation_start) * 1000,
                },
                description=f"Request {request_id} validated successfully",
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
                # Log file processing start
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_STARTED,
                    level=observability.EventLevel.INFO,
                    data={"file_count": len(files), "filenames": [f.get("filename", "unknown") for f in files]},
                    description=f"Starting file processing for {len(files)} file(s)",
                )

                # Emit progress event for file processing (only works when streaming is enabled)
                streaming.stream(
                    "progress",
                    "Processing files...",
                    stage="file_processing",
                    file_count=len(files),
                    skip_rephrase=True,
                )

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

            # Store ORIGINAL user message in buffer memory (fire-and-forget with tracking)
            self.overlord._create_tracked_task(
                self._store_user_message_async(
                    message=message,  # Store original message, not enhanced
                    timestamp=timestamp,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                ),
                name=f"store_user_message_{request_id}"
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
                and self.overlord.auto_extract_user_info
            ):
                # Log user info extraction task creation
                observability.observe(
                    event_type=observability.ConversationEvents.USER_INFO_EXTRACTION_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "user_id": user_id,
                        "extraction_enabled": True,
                        "background_task": True,
                    },
                    description="Starting background user information extraction task",
                )

                self.overlord._create_tracked_task(
                    self._extract_user_information_async(
                        user_message=message,  # Original message for storage
                        agent_response="",  # No response yet
                        user_id=user_id,
                        agent_id=agent_name or "overlord",
                        enhanced_message=enhanced_message,  # Enhanced message for context
                    ),
                    name=f"extract_user_info_{request_id}"
                )

            # Use provided values or formation defaults
            webhook_url = webhook_url or getattr(self.overlord, "async_webhook_url", None)
            threshold_seconds = threshold_seconds or getattr(
                self.overlord, "async_threshold_seconds", 30
            )

            # FAIL-SAFE: Force sync mode if no webhook URL is available
            if use_async is not False and webhook_url is None:
                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_MODE_CHANGED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "requested_mode": "async",
                        "forced_mode": "sync",
                        "reason": "no_webhook_url",
                        "webhook_url_provided": webhook_url is not None,
                    },
                    description="Request mode forced from async to sync due to missing webhook URL",
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

            # Determine streaming behavior
            use_streaming = (
                stream if stream is not None else getattr(self.overlord, "streaming", False)
            )

            # Only enable streaming if actually needed
            if use_streaming:
                streaming.enable_streaming(request_id, user_id, session_id)

            # Execute sync request
            if use_streaming:
                # Return the streaming generator (delegates to separate function with yield)
                return self._create_stream_generator(
                    enhanced_message=enhanced_message,
                    original_message=message,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    use_async=use_async,
                    webhook_url=webhook_url,
                    internal_user_id=internal_user_id,
                    muxi_user_id=muxi_user_id,
                    bypass_workflow_approval=bypass_workflow_approval,
                )

            # else...
            return await self._process_sync_chat(
                message=enhanced_message,
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                original_message=message,  # Pass original for extraction
                use_async=use_async,
                webhook_url=webhook_url,
                bypass_workflow_approval=bypass_workflow_approval,
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
            event_type=observability.ConversationEvents.REQUEST_QUEUED_ASYNC,
            level=observability.EventLevel.INFO,
            data={
                "request_id": request_id,
                "webhook_url": webhook_url,
                "estimated_duration_ms": None,  # Unknown at queue time
                "queue_position": None,  # Single task queue currently
            },
            description=f"Request queued for asynchronous processing: {request_id}",
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
        bypass_workflow_approval: bool = False,
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
        try:
            result = await self.overlord._process_sync_chat(
                message=message,
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                request_id=request_id,
                use_async=use_async,
                webhook_url=webhook_url,
                bypass_workflow_approval=bypass_workflow_approval,
            )
        except RequestCancelledException as e:
            # Request was cancelled by user - log and return empty response
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_FAILED,
                level=observability.EventLevel.INFO,
                data={
                    "request_id": e.request_id,
                    "reason": "cancelled_by_user",
                    "cancelled": True,
                },
                description=f"Request {e.request_id} cancelled by user",
            )
            # Return empty response - the DELETE endpoint already responded
            return MuxiResponse(
                role="assistant",
                content="",
                metadata={"cancelled": True, "request_id": e.request_id},
            )

        # Note: overlord._process_sync_chat already emits streaming events
        # including "completed" with actual content - don't duplicate here

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

            # Always call storage with valid data (tracked)
            self.overlord._create_tracked_task(
                self._store_assistant_response_async(
                    content=content_for_storage,
                    timestamp=time.time(),
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                ),
                name=f"store_assistant_response_{request_id}"
            )

        # ALWAYS return MuxiResponse objects with session_id in metadata
        # Note: MuxiResponse is imported at module level

        # Build metadata with session_id for API layer
        response_metadata = {"session_id": session_id} if session_id else {}

        if isinstance(result, MuxiResponse):
            # Merge session_id into existing metadata
            if result.metadata:
                result.metadata["session_id"] = session_id
            else:
                result.metadata = response_metadata
            return result

        # If we didn't get a MuxiResponse, create one
        # This should rarely happen but ensures consistency
        if result and hasattr(result, "content"):
            return MuxiResponse(
                role="assistant",
                content=result.content if isinstance(result.content, str) else str(result.content),
                artifacts=result.artifacts if hasattr(result, 'artifacts') and result.artifacts else None,
                metadata=response_metadata
            )
        elif isinstance(result, str):
            return MuxiResponse(
                role="assistant",
                content=result,
                metadata=response_metadata
            )
        else:
            # Fallback for unexpected types
            return MuxiResponse(
                role="assistant",
                content=str(result) if result else "",
                metadata=response_metadata
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
                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
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
                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
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

        # 1. Get user synopsis (cached) from user context manager
        user_profile_text = ""
        if self.overlord.is_multi_user and user_id:
            try:
                # Use cached synopsis instead of querying Memobase every time
                synopsis = await self.overlord.get_user_synopsis(external_user_id=user_id)
                # Only set if we got actual content (not empty string)
                if synopsis and synopsis.strip():
                    user_profile_text = synopsis
            except Exception:
                pass  # Continue without user profile

        # 2. Search for relevant long-term memories
        long_term_memories = ""
        if self.overlord.long_term_memory and user_id:
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
            except Exception as e:
                # Log error but continue without long-term memories
                from ...services import observability
                observability.observe(
                    event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                    level=observability.EventLevel.ERROR,  # Changed to ERROR to see it
                    data={
                        "operation": "long_term_memory_search",
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "traceback": str(e.__traceback__) if hasattr(e, '__traceback__') else None,
                    },
                    description=f"Long-term memory search failed: {str(e)}",
                )
                # Make sure long_term_memories is empty
                long_term_memories = ""

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
        # Include a unique request marker to prevent semantic cache matching
        # with previous requests that had similar text but no files
        if file_results:
            import uuid
            cache_bust_id = str(uuid.uuid4())[:8]  # Short unique ID
            enhanced_parts.append(f"=== FILE PROCESSING RESULTS [req:{cache_bust_id}] ===")
            enhanced_parts.append(file_results)
            enhanced_parts.append("")

        # 4. Relevant long-term memories (medium priority)
        if long_term_memories:
            # Load memory usage protocol from prompts
            from ..prompts.loader import PromptLoader
            try:
                memory_protocol = PromptLoader.get('memory_usage_protocol.md')
                enhanced_parts.append(memory_protocol)
                enhanced_parts.append("")
            except KeyError:
                # Fallback to inline protocol if file not found
                enhanced_parts.append("=== RELEVANT MEMORIES ===")
                enhanced_parts.append(
                    "IMPORTANT: The following are verified FACTS about this specific user. "
                    "When answering their question, you MUST use ALL relevant items from this list. "
                    "These are their stated preferences and information - prioritize these OVER general advice:"
                )

            enhanced_parts.append(long_term_memories)
            enhanced_parts.append("")

        # 5. Conversation context (lowest priority - truncated first if needed)
        if context_text:
            # Load conversation awareness protocol from prompts
            from ..prompts.loader import PromptLoader
            try:
                conv_protocol = PromptLoader.get('conversation_awareness_protocol.md')
                enhanced_parts.append(conv_protocol)
                enhanced_parts.append("")
            except Exception:
                pass  # Continue without protocol if not found
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
