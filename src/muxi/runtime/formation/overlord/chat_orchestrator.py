"""
Chat orchestration system for the Overlord.

This module handles the main chat orchestration logic, including async/sync decision making,
streaming support, and workflow coordination.
"""

import asyncio
import time
import traceback
from contextlib import suppress
from typing import Any, AsyncGenerator, Dict, List, NamedTuple, Optional, Union

from ...datatypes.response import MuxiResponse
from ...services import observability, streaming
from ...services.observability.context import (
    get_current_event_logger,
    get_current_request_context,
    set_event_logger,
    set_request_context,
)
from ...utils.id_generator import generate_nanoid
from ..background.cancellation import RequestCancelledException
from ..background.request_tracker import RequestState, RequestStatus


class EnhancedMessage(NamedTuple):
    """Pair of (original, enhanced) messages produced by context enrichment.

    The marker-formatted ``enhanced`` blob is the analyzer-pipeline contract
    (clarification analyzer, planning, intent extraction, and other
    pre-agent text-parsing hops still expect the legacy shape). The
    ``original`` is the raw user text — the value we want to surface in
    observability events. Returning both at the source kills the
    re-parse-the-wrapper pattern that used to be repeated 5+ times across
    overlord internals.
    """

    original: str
    enhanced: str


# Marker prefix the agent sees in front of a scheduled-execution message.
# Resolves the ambiguity where ``remind me to X`` reads as a chat request
# to *configure* a reminder rather than as the reminder firing right now.
# Applied only at the agent's view of the message — buffer memory and
# observability still see the raw user text. See
# ``_apply_scheduled_marker`` for the single-place rule.
SCHEDULED_EXECUTION_MARKER = "[SCHEDULED] "


def _apply_scheduled_marker(message: str, session_id: Optional[str]) -> str:
    """Return ``message`` with the scheduled-execution marker if and only
    if ``session_id`` belongs to the scheduler namespace.

    Centralized so both message-rendering paths
    (``_enhance_message_with_context`` and ``_build_clean_chat_context``)
    apply the same rule, and so a single source-shape assertion can lock
    the policy.

    Idempotent: if ``message`` already starts with the marker (e.g. a
    user copy-pasted a prior scheduled-firing transcript into a new
    scheduled job, or two render paths chain the helper through the
    same string), the marker is not doubled. Double-prefixing is
    harmless for well-behaved models but still a silent edge case
    worth guarding against.
    """
    if session_id and session_id.startswith("job_"):
        if not message.startswith(SCHEDULED_EXECUTION_MARKER):
            return f"{SCHEDULED_EXECUTION_MARKER}{message}"
    return message


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
        clean_chat_context: Optional[Dict[str, Any]] = None,
        is_scheduled_execution: bool = False,
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
            from ...services.observability.context import RequestContext, set_request_context

            request_context = RequestContext(
                id=request_id,
                user_id=user_id,
                session_id=session_id,
                formation_id=getattr(self.overlord, "formation_id", "unknown"),
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
                "One second...",
            ]

            # Use streaming.stream() to respect progress filtering
            streaming.stream(
                "progress", random.choice(initial_messages), stage="init", skip_rephrase=True
            )

            # Process the request - overlord._process_sync_chat will handle all streaming events
            try:
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
                    clean_chat_context=clean_chat_context,
                    is_scheduled_execution=is_scheduled_execution,
                )
            except Exception as exc:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.ERROR,
                    data={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "request_id": request_id,
                    },
                    description=f"Chat processing failed: {exc}",
                )
                streaming.stream(
                    "completed",
                    f"I'm sorry, I encountered an error processing your request: {exc}",
                    status="error",
                    processing_time_ms=0,
                )
                return MuxiResponse(
                    role="assistant",
                    content=f"I'm sorry, I encountered an error processing your request: {exc}",
                )

            # Note: The overlord._process_sync_chat method handles all streaming events:
            # - It emits "content" events with the actual response
            # - It emits "completed" event when done
            # - It disables streaming when finished
            # We don't need to duplicate that here.

            return result

        # Create task with context propagation (Python 3.10 compatible)
        processing_task = None

        def create_task_with_context():
            nonlocal processing_task
            processing_task = asyncio.create_task(delayed_process())
            return processing_task

        current_context.run(create_task_with_context)

        # Yield events from the stream; cancel processing on client disconnect
        try:
            async for event in self._stream_request(request_id, user_id, session_id):
                yield event
        finally:
            # Client disconnected or stream ended -- cancel if still running
            if processing_task and not processing_task.done():
                processing_task.cancel()
                mcp_service = getattr(self.overlord, "mcp_service", None)
                if mcp_service and request_id:
                    with suppress(Exception):
                        await mcp_service.cancel_requests_for_request(
                            request_id, close_live_connections=True
                        )
                # Wait briefly for the task to acknowledge cancellation.
                # Don't wait forever -- the task may be stuck in a blocking
                # MCP/DB call that doesn't respond to cancellation.
                with suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(processing_task), timeout=5.0)
                # Mark request as cancelled so it doesn't block future requests
                await self.overlord.request_tracker.update_request(
                    request_id, RequestStatus.CANCELLED
                )
            streaming.disable_streaming(request_id)

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
        is_scheduled_execution: bool = False,
    ) -> Union[str, Dict[str, Any], AsyncGenerator[str, None], MuxiResponse]:
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

        # Track framework mode requests (direct Python API calls, not via HTTP)
        # HTTP requests are tracked by middleware with route="direct" or "server"
        from ...services.telemetry import get_telemetry
        from ..server.middleware import is_http_request

        _framework_start_time = time.time()
        _is_framework_mode = not is_http_request()

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
                if self.overlord.long_term_memory
                else None
            )

            # Only resolve if db_manager is available
            if db_mgr is not None:
                resolved_user = await resolve_user_identifier(
                    identifier=user_id,
                    formation_id=self.overlord.formation_id,
                    db_manager=db_mgr,
                    kv_cache=None,  # KV cache not yet implemented
                )
                if resolved_user is not None:
                    internal_user_id, muxi_user_id = resolved_user
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
                    data={
                        "file_count": len(files),
                        "filenames": [f.get("filename", "unknown") for f in files],
                    },
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
                name=f"store_user_message_{request_id}",
            )

            # Early non-actionable heuristic on raw message (before context enhancement).
            # If the message is a simple greeting/acknowledgment and this is the first
            # message (no buffer context with a prior assistant question), we can skip
            # the expensive context enhancement and LLM actionability check entirely.
            _raw_lower = message.lower().strip()
            _skip_context_enhancement = False
            # Only attempt fast-path for non-streaming sync requests.
            # Streaming callers expect an AsyncGenerator return type which the
            # fast-path does not produce.
            _use_streaming = (
                stream if stream is not None else getattr(self.overlord, "streaming", False)
            )
            if not _use_streaming and _raw_lower in (
                "hi",
                "hello",
                "hey",
                "thanks",
                "thank you",
                "ok",
                "okay",
                "got it",
            ):
                # Check if there's a recent assistant message with a question
                # (which would mean this is a follow-up answer, not a greeting).
                # Fetch k=5 to avoid race with the just-stored user message.
                _has_prior_question = False
                if self.overlord.buffer_memory_manager:
                    try:
                        _filter = {"user_id": user_id}
                        if session_id:
                            _filter["session_id"] = session_id
                        _recent = await self.overlord.buffer_memory_manager.search_buffer_memory(
                            query="",
                            k=5,
                            filter_metadata=_filter,
                        )
                        for _item in _recent or []:
                            _role = _item.get("metadata", {}).get("role", "")
                            if _role == "assistant":
                                if "?" in _item.get("text", ""):
                                    _has_prior_question = True
                                break
                    except Exception:
                        pass
                if not _has_prior_question:
                    _skip_context_enhancement = True

            if _skip_context_enhancement:
                # Fast path: skip context enhancement, go straight to persona response
                response = await self.overlord._apply_persona(None, message)

                if self.overlord.buffer_memory_manager:
                    self.overlord._create_tracked_task(
                        self.overlord.buffer_memory_manager.add_to_buffer_memory(
                            message=response,
                            metadata={
                                "user_id": user_id,
                                "session_id": session_id,
                                "role": "assistant",
                                "timestamp": time.time(),
                                "request_id": request_id,
                            },
                            agent_id="overlord",
                        ),
                        name=f"store_response_{request_id}",
                    )

                # Record framework mode telemetry
                if _is_framework_mode:
                    telemetry = get_telemetry()
                    if telemetry:
                        latency_ms = (time.time() - _framework_start_time) * 1000
                        telemetry.record_request(True, latency_ms, "framework")

                # Mark request as completed in tracker
                await self.overlord.request_tracker.update_request(
                    request_id, RequestStatus.COMPLETED, result=response
                )

                return MuxiResponse(
                    role="assistant",
                    content=response,
                    metadata={
                        "handled_by": "overlord_direct",
                        "is_actionable": False,
                        "fast_path": True,
                        "early_heuristic": True,
                        "processing_time_ms": (time.time() - timestamp) * 1000,
                    },
                )

            # Enhance message with conversation context (memories + buffer).
            # We build BOTH representations in parallel:
            #
            # * ``enhanced_message`` is the marker-formatted analyzer
            #   blob (``=== CURRENT REQUEST ===`` / ``=== CONVERSATION
            #   CONTEXT ===`` / etc). It is consumed by the
            #   clarification analyzer, planning, intent extraction,
            #   and other pre-agent text-parsing hops that depend on
            #   the existing string layout.
            #
            # * ``clean_chat_context`` is a structured bundle of the
            #   same pieces (buffer history as proper role turns,
            #   profile + memories as separate fields). The agent
            #   uses this to assemble a chat-API-shaped message list
            #   with its own system message — avoiding the
            #   double-encoding of conversation history that broke
            #   Sonnet 4.6's pure-chat behavior on PR #160's casual
            #   chat test.
            enhanced_pair, clean_chat_context = await asyncio.gather(
                self._enhance_message_with_context(
                    message=message,
                    user_id=user_id,
                    session_id=session_id,
                    file_results=file_results,
                ),
                self._build_clean_chat_context(
                    current_user_message=message,
                    user_id=user_id,
                    session_id=session_id,
                    file_results=file_results,
                ),
            )
            # ``enhanced_pair.original`` is just ``message`` — we destructure
            # for symmetry with ``enhanced`` and to make the data contract
            # visible at the call site. Both values are threaded through
            # the call chain so observability emits can log the bare user
            # request without re-parsing the marker wrapper.
            enhanced_message = enhanced_pair.enhanced
            original_message = enhanced_pair.original

            # Extract user information from enhanced message (fire-and-forget)
            # Only if persistent memory is configured
            if self.overlord.long_term_memory and user_id and self.overlord.auto_extract_user_info:
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
                    name=f"extract_user_info_{request_id}",
                )

            # Use provided values or formation defaults
            if webhook_url is None:
                webhook_url = getattr(self.overlord, "async_webhook_url", None)
            if threshold_seconds is None:
                threshold_seconds = getattr(self.overlord, "async_threshold_seconds", 30)

            # Log when async mode is used without a webhook (polling-only)
            if use_async and webhook_url is None:
                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_MODE_CHANGED,
                    level=observability.EventLevel.INFO,
                    data={
                        "requested_mode": "async",
                        "webhook_url_provided": False,
                        "delivery_method": "polling",
                    },
                    description="Async request without webhook; client must poll GET /requests/{id}",
                )

            # Smart async/sync decision making
            should_use_async = await self._determine_async_mode(
                enhanced_message, agent_name, use_async, threshold_seconds
            )

            if should_use_async:
                # Mark this request as async to prevent premature completion
                self.overlord.observability_manager.mark_request_async(request_id)

                # Execute async request
                async_result = await self._execute_async_request(
                    message=enhanced_message,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    webhook_url=webhook_url,
                    timestamp=timestamp,
                    original_message=original_message,
                    is_scheduled_execution=is_scheduled_execution,
                )

                # Record framework mode telemetry (async requests are always "successful" at queue time)
                if _is_framework_mode:
                    telemetry = get_telemetry()
                    if telemetry:
                        latency_ms = (time.time() - _framework_start_time) * 1000
                        telemetry.record_request(True, latency_ms, "framework")

                return async_result

            # Determine streaming behavior
            use_streaming = (
                stream if stream is not None else getattr(self.overlord, "streaming", False)
            )
            stream_user_id = user_id or "0"
            stream_session_id = session_id or request_id
            chat_result: Union[str, Dict[str, Any], MuxiResponse]

            # Only enable streaming if actually needed
            if use_streaming:
                streaming.enable_streaming(request_id, stream_user_id, stream_session_id)

            # Execute sync request
            if use_streaming:
                # For streaming, record telemetry at start (can't easily track end)
                if _is_framework_mode:
                    telemetry = get_telemetry()
                    if telemetry:
                        latency_ms = (time.time() - _framework_start_time) * 1000
                        telemetry.record_request(True, latency_ms, "framework")

                # Return the streaming generator (delegates to separate function with yield)
                return self._create_stream_generator(
                    enhanced_message=enhanced_message,
                    original_message=original_message,
                    agent_name=agent_name,
                    user_id=stream_user_id,
                    session_id=stream_session_id,
                    request_id=request_id,
                    use_async=use_async,
                    webhook_url=webhook_url,
                    internal_user_id=internal_user_id,
                    muxi_user_id=muxi_user_id,
                    bypass_workflow_approval=bypass_workflow_approval,
                    clean_chat_context=clean_chat_context,
                    is_scheduled_execution=is_scheduled_execution,
                )

            # Sync processing
            success = False  # Initialize before try block to prevent UnboundLocalError in finally
            try:
                chat_result = await self._process_sync_chat(
                    message=enhanced_message,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    original_message=original_message,
                    use_async=use_async,
                    webhook_url=webhook_url,
                    bypass_workflow_approval=bypass_workflow_approval,
                    clean_chat_context=clean_chat_context,
                    is_scheduled_execution=is_scheduled_execution,
                )
                success = True
            except Exception:
                success = False
                raise
            finally:
                # Record framework mode telemetry for sync requests
                if _is_framework_mode:
                    telemetry = get_telemetry()
                    if telemetry:
                        latency_ms = (time.time() - _framework_start_time) * 1000
                        telemetry.record_request(success, latency_ms, "framework")

            return chat_result

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
        original_message: Optional[str] = None,
        is_scheduled_execution: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a request asynchronously.

        Args:
            message: Marker-formatted enhanced blob
            agent_name: Optional specific agent
            user_id: Optional user ID
            session_id: Optional session ID
            request_id: Unique request ID
            webhook_url: Optional webhook URL
            timestamp: Request timestamp
            original_message: Bare user text (no markers) — stored on
                ``RequestState`` so that downstream observability events
                in the async background path read the actual user
                request rather than the wrapper.

        Returns:
            Dictionary with async request information
        """
        # Create initial request state
        initial_state = RequestState(
            id=request_id,
            status=RequestStatus.PROCESSING,
            start_time=timestamp,
            original_message=original_message if original_message is not None else message,
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
                original_message=original_message,
                is_scheduled_execution=is_scheduled_execution,
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
            response["delivery"] = "webhook"
        else:
            response["delivery"] = "polling"
            response["poll_url"] = f"/v1/requests/{request_id}"

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
        clean_chat_context: Optional[Dict[str, Any]] = None,
        is_scheduled_execution: bool = False,
    ) -> Union[str, Dict[str, Any], MuxiResponse]:
        """
        Process a chat request synchronously.

        Args:
            message: The user's message (analyzer-formatted enhanced blob)
            agent_name: Optional specific agent
            user_id: Optional user ID
            session_id: Optional session ID
            request_id: Optional request ID
            original_message: Original message before enhancement
            use_async: Explicit async preference to pass to workflow
            webhook_url: Webhook URL for async responses
            clean_chat_context: Optional bundle from
                ``_build_clean_chat_context`` carrying buffer history
                as proper role turns + the raw current user message.
                When supplied, the agent uses this for its LLM call
                instead of accumulating ``self._messages`` from
                marker-formatted enhanced blobs.

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
                original_message=original_message,
                use_async=use_async,
                webhook_url=webhook_url,
                bypass_workflow_approval=bypass_workflow_approval,
                clean_chat_context=clean_chat_context,
                is_scheduled_execution=is_scheduled_execution,
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
                name=f"store_assistant_response_{request_id}",
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

        # Check for async processing response (dict with request_id and status: processing)
        # Return as-is to preserve async response structure for callers
        if (
            isinstance(result, dict)
            and result.get("status") == "processing"
            and "request_id" in result
        ):
            return result

        # If we didn't get a MuxiResponse, create one
        # This should rarely happen but ensures consistency
        if result and hasattr(result, "content"):
            return MuxiResponse(
                role="assistant",
                content=result.content if isinstance(result.content, str) else str(result.content),
                artifacts=(
                    result.artifacts if hasattr(result, "artifacts") and result.artifacts else None
                ),
                metadata=response_metadata,
            )
        elif isinstance(result, str):
            return MuxiResponse(role="assistant", content=result, metadata=response_metadata)
        else:
            # Fallback for unexpected types
            return MuxiResponse(
                role="assistant", content=str(result) if result else "", metadata=response_metadata
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
    ) -> EnhancedMessage:
        """
        Enhance user message with conversation context.

        Uses formation buffer configuration to retrieve and format context.
        Implements priority ordering: current request → file results → conversation context.

        Args:
            message: The current user message (raw, no markers)
            user_id: User identifier for filtering
            session_id: Optional session identifier for filtering
            file_results: Optional file processing results to include

        Returns:
            ``EnhancedMessage(original, enhanced)`` — the raw user request
            alongside the marker-formatted analyzer blob. Returning both
            here (instead of just the enhanced string) is what lets every
            downstream observability event log the bare user text without
            re-parsing the wrapper out of it.
        """
        # Check if message is already enhanced to prevent double enhancement.
        # In this defensive branch we cannot recover the *true* original
        # (whoever pre-enhanced lost it), so we surface the wrapper as both
        # fields. Callers normally never hit this branch; it exists as a
        # safety rail against double-enhancement.
        if "=== CURRENT REQUEST ===" in message:
            return EnhancedMessage(original=message, enhanced=message)

        def _is_profile_recall_request(current_message: str) -> bool:
            normalized = current_message.strip().lower()
            profile_patterns = [
                "what is my current user profile",
                "what's my current user profile",
                "what is my user profile",
                "what's my user profile",
                "what is my current profile",
                "what's my current profile",
                "what is my profile",
                "what's my profile",
                "what do you know about me",
                "tell me about me",
                "summarize my profile",
                "summarise my profile",
            ]
            return any(pattern in normalized for pattern in profile_patterns)

        # Get configuration from formation
        buffer_config = self.overlord.formation_config.get("memory", {}).get("buffer", {})
        buffer_size = buffer_config.get("size", 10)
        vector_search = buffer_config.get("vector_search", True)
        is_profile_recall_request = _is_profile_recall_request(message)

        # Run all three context sources concurrently
        async def _fetch_user_synopsis():
            if self.overlord.is_multi_user and user_id:
                try:
                    synopsis = await self.overlord.get_user_synopsis(external_user_id=user_id)
                    if synopsis and synopsis.strip():
                        return synopsis
                except Exception:
                    pass
            return ""

        async def _fetch_long_term_memories():
            if self.overlord.long_term_memory and user_id:
                try:
                    collections_to_search = [
                        "activities",
                        "preferences",
                        "user_identity",
                        "relationships",
                        "work_projects",
                        "conversations",
                        "goals",
                        "default",
                    ]
                    lt_results = (
                        await self.overlord.persistent_memory_manager.search_long_term_memory(
                            query=message,
                            k=5,
                            user_id=user_id,
                            collections=collections_to_search,
                        )
                    )
                    if lt_results:
                        memory_parts = []
                        for mem in lt_results:
                            content = mem.get("text", "")
                            if content:
                                if len(content) > 200:
                                    content = content[:197] + "..."
                                memory_parts.append(f"- {content}")
                        if memory_parts:
                            return "\n".join(memory_parts[:3])
                except Exception as e:
                    from ...services import observability

                    observability.observe(
                        event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={
                            "operation": "long_term_memory_search",
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "traceback": (
                                str(e.__traceback__) if hasattr(e, "__traceback__") else None
                            ),
                        },
                        description=f"Long-term memory search failed: {str(e)}",
                    )
            return ""

        async def _fetch_profile_memory_facts():
            if not self.overlord.long_term_memory or not user_id:
                return ""

            if not hasattr(self.overlord.long_term_memory, "list_memories"):
                return ""

            try:
                profile_collections = [
                    "user_identity",
                    "relationships",
                    "work_projects",
                    "preferences",
                    "activities",
                ]
                seen_contents = set()
                memory_parts = []

                for collection in profile_collections:
                    memories = await self.overlord.long_term_memory.list_memories(
                        limit=2,
                        collection=collection,
                        external_user_id=user_id,
                    )
                    for mem in memories:
                        content = (mem.get("text") or mem.get("content") or "").strip()
                        if not content or content in seen_contents:
                            continue
                        seen_contents.add(content)
                        if len(content) > 200:
                            content = content[:197] + "..."
                        memory_parts.append(f"- {content}")
                        if len(memory_parts) >= 6:
                            return "\n".join(memory_parts)

                return "\n".join(memory_parts)
            except Exception:
                return ""

        async def _fetch_buffer_context():
            if self.overlord.buffer_memory_manager:
                try:
                    metadata_filter = {"user_id": user_id}
                    if session_id:
                        metadata_filter["session_id"] = session_id

                    if vector_search:
                        # When vector search is enabled, the current
                        # message is used as the embedding key. For
                        # meta-recall queries ("list back what I
                        # mentioned earlier", "summarise what we've
                        # discussed") that embedding does NOT match the
                        # content messages well, and conversation
                        # recency_bias alone (0.3) is too weak to
                        # surface recent turns. Always merge a recency
                        # floor — the last buffer_size items by
                        # recency — with the vector-search results so
                        # follow-up / recall questions still see the
                        # most recent conversational context. The
                        # local-only path already does pure-recency
                        # via the empty-query fast path.
                        vector_results, recency_results = await asyncio.gather(
                            self.overlord.buffer_memory_manager.search_buffer_memory(
                                query=message,
                                k=buffer_size,
                                filter_metadata=metadata_filter,
                            ),
                            self.overlord.buffer_memory_manager.search_buffer_memory(
                                query="",
                                k=buffer_size,
                                filter_metadata=metadata_filter,
                            ),
                        )
                        # De-duplicate by (text, timestamp). Preserve
                        # vector_results ordering (most relevant first)
                        # and append any recency-only items missing
                        # from the vector pass at the end.
                        seen_keys = set()
                        merged: List[Dict[str, Any]] = []
                        for item in vector_results or []:
                            key = (
                                item.get("text", ""),
                                item.get("metadata", {}).get("timestamp"),
                            )
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                            merged.append(item)
                        for item in recency_results or []:
                            key = (
                                item.get("text", ""),
                                item.get("metadata", {}).get("timestamp"),
                            )
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                            merged.append(item)
                        context_messages_list = merged
                    else:
                        context_messages_list = (
                            await self.overlord.buffer_memory_manager.search_buffer_memory(
                                query="",
                                k=buffer_size,
                                filter_metadata=metadata_filter,
                            )
                        )
                    return context_messages_list
                except Exception:
                    pass
            return None

        if is_profile_recall_request:
            user_profile_text, profile_memory_facts, context_messages_list = await asyncio.gather(
                _fetch_user_synopsis(),
                _fetch_profile_memory_facts(),
                _fetch_buffer_context(),
            )
            long_term_memories = profile_memory_facts
            if not user_profile_text and not long_term_memories:
                long_term_memories = await _fetch_long_term_memories()
        else:
            user_profile_text, long_term_memories, context_messages_list = await asyncio.gather(
                _fetch_user_synopsis(),
                _fetch_long_term_memories(),
                _fetch_buffer_context(),
            )

        # Format buffer context results
        context_text = ""
        if context_messages_list:
            context_parts = []
            for msg in reversed(context_messages_list):
                role = msg.get("metadata", {}).get("role", "unknown")
                timestamp = msg.get("metadata", {}).get("timestamp", "")
                content = msg.get("text", "")

                if any(
                    marker in content
                    for marker in [
                        "=== CONVERSATION CONTEXT",
                        "=== CURRENT REQUEST ===",
                        "=== USER PROFILE ===",
                        "=== FILE PROCESSING RESULTS ===",
                        "=== RELEVANT MEMORIES ===",
                    ]
                ):
                    if "=== CURRENT REQUEST ===" in content and "User:" in content:
                        lines = content.split("\n")
                        for i, line in enumerate(lines):
                            if line.strip() == "=== CURRENT REQUEST ===" and i + 1 < len(lines):
                                next_line = lines[i + 1].strip()
                                if next_line.startswith("User:"):
                                    content = next_line[5:].strip()
                                    break
                    else:
                        continue

                if timestamp:
                    import datetime

                    dt = datetime.datetime.fromtimestamp(timestamp)
                    time_str = dt.strftime("%H:%M")
                    context_parts.append(f"[{time_str}] {role.capitalize()}: {content}")
                else:
                    context_parts.append(f"{role.capitalize()}: {content}")

            context_text = "\n".join(context_parts)

        # Build enhanced message with priority ordering (most important first)
        enhanced_parts = []

        # 1. Current request (highest priority - always preserved).
        # Apply the scheduled-execution marker only at the rendering
        # layer — the ``message`` variable (and the EnhancedMessage
        # ``original`` field returned below) stays unchanged so memory
        # storage and observability emits keep the raw user text.
        display_message = _apply_scheduled_marker(message, session_id)
        enhanced_parts.append("=== CURRENT REQUEST ===")
        enhanced_parts.append(f"User: {display_message}")
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
        # IMPORTANT: Put memories BEFORE the protocol so LLM sees the data first
        if long_term_memories:
            # Add memories section FIRST - before instructions
            enhanced_parts.append("=== RELEVANT MEMORIES ===")
            enhanced_parts.append(long_term_memories)
            enhanced_parts.append("")

            # Then add the usage protocol as guidance
            from ..prompts.loader import PromptLoader

            try:
                memory_protocol = PromptLoader.get("memory_usage_protocol.md")
                enhanced_parts.append(memory_protocol)
                enhanced_parts.append("")
            except KeyError:
                # Fallback to inline protocol if file not found
                enhanced_parts.append(
                    "IMPORTANT: The memories above are verified FACTS about this specific user. "
                    "When answering their question, you MUST use ALL relevant items from the RELEVANT MEMORIES section. "
                    "These are their stated preferences and information - prioritize these OVER general advice:"
                )
                enhanced_parts.append("")

        # 5. Conversation context (lowest priority - truncated first if needed)
        if context_text:
            # Load conversation awareness protocol from prompts
            from ..prompts.loader import PromptLoader

            try:
                conv_protocol = PromptLoader.get("conversation_awareness_protocol.md")
                enhanced_parts.append(conv_protocol)
                enhanced_parts.append("")
            except Exception:
                pass  # Continue without protocol if not found
            enhanced_parts.append("=== CONVERSATION CONTEXT (Most Recent First) ===")
            enhanced_parts.append(context_text)

        enhanced_message = "\n".join(enhanced_parts)

        return EnhancedMessage(original=message, enhanced=enhanced_message)

    async def _build_clean_chat_context(
        self,
        *,
        current_user_message: str,
        user_id: Any,
        session_id: Optional[str],
        file_results: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a chat-API-shaped context bundle for the agent's LLM call.

        Returns a dict bundle that the agent assembles into a clean
        role-turn transcript using its own system message::

            {
              "buffer_turns": [{"role": "user"|"assistant", "content": "..."}],
              "current_user_message": "<user text, optionally prefixed
                                       with '[SCHEDULED] ' when
                                       session_id belongs to the
                                       scheduler namespace>",
              "user_profile_text": "...",
              "long_term_memories": "...",
              "file_results": "...",
            }

        ``current_user_message`` is the only field the marker is applied
        to — ``buffer_turns`` mirrors buffer memory's stored shape (the
        original user text, no marker) and the remaining fields carry
        no user input. See ``_apply_scheduled_marker`` for the rule.

        in contrast to ``_enhance_message_with_context`` which produces a
        single flat string with ``=== CURRENT REQUEST ===`` /
        ``=== CONVERSATION CONTEXT ===`` markers (still consumed by the
        clarification analyzer, planning, intent extraction, and other
        pre-agent processing hops).

        The two functions exist side-by-side intentionally:

        * The marker-formatted string is the analyzer-pipeline contract.
          Anything that parses the user's request with regex/text
          extraction still sees the same shape it always saw.
        * This clean bundle is the LLM-completion contract. Buffer
          memory stores ORIGINAL (un-enhanced) user/assistant text —
          see ``_store_user_message_async`` /
          ``_store_assistant_response_async`` — so we can simply
          replay those rows as proper role tags without any string
          parsing.

        Why this matters: rendering the conversation history twice
        (once as proper role turns, once as a flat ``[12:30] User:``
        block embedded inside every fresh user-turn) gives the LLM
        contradictory framing. Models with strong honesty training
        (Sonnet 4.6, GPT-5) read the ``=== CURRENT REQUEST ===``
        wrapper as an isolated query and treat the surrounding flat
        blob as metadata-not-history, then ask for clarification on
        questions that are unambiguous in the proper role-turn view.
        See mental-model.md for the full diagnosis.

        The agent owns the final assembly because the agent owns its
        own ``system_message``; we don't want the orchestrator to have
        to know which agent was selected.
        """
        buffer_config = self.overlord.formation_config.get("memory", {}).get("buffer", {})
        buffer_size = buffer_config.get("size", 10)

        # Run profile/memories/buffer fetches concurrently, mirroring
        # _enhance_message_with_context's approach.
        async def _fetch_user_synopsis() -> str:
            if self.overlord.is_multi_user and user_id:
                try:
                    synopsis = await self.overlord.get_user_synopsis(external_user_id=user_id)
                    if synopsis and synopsis.strip():
                        return synopsis
                except Exception:
                    pass
            return ""

        async def _fetch_long_term_memories() -> str:
            if self.overlord.long_term_memory and user_id:
                try:
                    collections_to_search = [
                        c
                        for c in (
                            self.overlord.formation_config.get("memory", {})
                            .get("long_term", {})
                            .get("collections", [])
                            or []
                        )
                        if isinstance(c, str) and c
                    ]
                    if not collections_to_search:
                        collections_to_search = ["conversations"]
                    results = await self.overlord.long_term_memory.search(
                        query=current_user_message,
                        user_id=user_id,
                        collections=collections_to_search,
                        k=5,
                    )
                    if results:
                        formatted_memories = []
                        for r in results:
                            text = r.get("text") or r.get("content") or ""
                            if text:
                                formatted_memories.append(f"- {text}")
                        if formatted_memories:
                            return "\n".join(formatted_memories)
                except Exception:
                    pass
            return ""

        async def _fetch_buffer_role_turns() -> List[Dict[str, str]]:
            """Pull recent buffer rows as proper {role, content} dicts.

            Buffer storage is keyed by recency only (we use the
            empty-query branch of search_buffer_memory). The current
            user turn itself was just stored fire-and-forget by
            ``_store_user_message_async`` immediately before this
            method runs; it MAY or MAY NOT be visible in the buffer
            yet depending on ordering, so we filter it out by content
            equality to avoid double-injection.
            """
            if not self.overlord.buffer_memory_manager:
                return []
            try:
                metadata_filter: Dict[str, Any] = {"user_id": user_id}
                if session_id:
                    metadata_filter["session_id"] = session_id
                rows = await self.overlord.buffer_memory_manager.search_buffer_memory(
                    query="",
                    k=buffer_size,
                    filter_metadata=metadata_filter,
                )
            except Exception:
                return []
            if not rows:
                return []

            # search_buffer_memory returns most-recent-first; reverse
            # for chronological replay into the LLM context.
            ordered = list(reversed(rows))
            turns: List[Dict[str, str]] = []
            for row in ordered:
                meta = row.get("metadata", {}) or {}
                role = meta.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = row.get("text") or ""
                if not text:
                    continue
                # Skip the current user message if buffer storage
                # raced ahead of us; the orchestrator appends it
                # separately at the tail of this list.
                if role == "user" and text.strip() == current_user_message.strip():
                    continue
                turns.append({"role": role, "content": text})
            return turns

        user_profile_text, long_term_memories, buffer_turns = await asyncio.gather(
            _fetch_user_synopsis(),
            _fetch_long_term_memories(),
            _fetch_buffer_role_turns(),
        )

        # Apply the scheduled-execution marker only at the agent's
        # view of the current message. ``buffer_turns`` is left
        # untouched — those rows came from buffer memory which stores
        # the original user text, so prior scheduled invocations
        # appear in history without the marker (correct: only the
        # *current* turn needs the marker to disambiguate intent;
        # past turns' assistant responses already encode the
        # scheduled-execution behavior).
        return {
            "buffer_turns": buffer_turns,
            "current_user_message": _apply_scheduled_marker(current_user_message, session_id),
            "user_profile_text": user_profile_text,
            "long_term_memories": long_term_memories,
            "file_results": file_results or "",
        }

    async def _extract_user_information_async(
        self,
        user_message: str,
        agent_response: str,
        user_id: Any,
        agent_id: str,
        enhanced_message: Optional[str] = None,
    ) -> None:
        """Extract user information from conversation without blocking."""
        try:
            # IMPORTANT: Use the ORIGINAL user message for extraction, not enhanced.
            # The enhanced message contains memories/context that confuses the extraction LLM
            # into re-extracting old information instead of the new message content.
            await self.overlord.extract_user_information(
                user_message=user_message,  # Use original message, not enhanced
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
