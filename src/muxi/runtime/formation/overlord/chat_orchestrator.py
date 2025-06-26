"""
Chat orchestration system for the Overlord.

This module handles the main chat orchestration logic, including async/sync decision making,
streaming support, and workflow coordination.
"""

import time
from typing import Optional, Any, Union, Dict, AsyncGenerator, List

from ...utils.id_generator import generate_nanoid
from ...services import observability


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
        # Generate unique request ID for all requests (for tracking and logging)
        request_id = f"req_{generate_nanoid()}"
        timestamp = time.time()

        # Start request tracking with observability
        async with self.overlord.observability_manager.track_request(
            request_id=request_id,
            session_id=session_id,
            formation_id=self.overlord.formation_id,
            user_id=str(user_id) if user_id is not None else None,
        ):
            # Emit request received event
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_RECEIVED,
                level=observability.EventLevel.INFO,
                data={
                    "message_length": len(message),
                    "agent_name": agent_name,
                    "user_id": str(user_id) if user_id is not None else None,
                    "use_async": use_async,
                    "has_webhook": webhook_url is not None,
                    "has_files": files is not None and len(files) > 0,
                    "file_count": len(files) if files else 0,
                },
                description=f"Request {request_id} received",
            )

            # Emit request validation event (basic validation)
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_VALIDATED,
                level=observability.EventLevel.INFO,
                data={
                    "message_valid": len(message.strip()) > 0,
                    "agent_exists": agent_name is None or agent_name in self.overlord.agents,
                },
                description=f"Request {request_id} validated",
            )

            # Check if files are provided and we need to use document processing
            if files:
                # Use existing document processing functionality
                return await self.overlord.process_document_upload(
                    attachments=files,
                    user_request=message,
                    context={"agent_name": agent_name} if agent_name else None,
                    user_id=user_id,
                )

            # Use provided values or formation defaults
            webhook_url = webhook_url or getattr(self.overlord, "async_webhook_url", None)
            threshold_seconds = threshold_seconds or getattr(
                self.overlord, "async_threshold_seconds", 30
            )

            # Determine streaming behavior
            use_streaming = (
                stream if stream is not None else getattr(self.overlord, "streaming", False)
            )

            # Smart async/sync decision making
            should_use_async = await self._determine_async_mode(
                message, agent_name, use_async, threshold_seconds
            )

            if should_use_async:
                # Execute async request
                return await self._execute_async_request(
                    message=message,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    webhook_url=webhook_url,
                    timestamp=timestamp,
                )
            else:
                # Execute sync request
                if use_streaming:
                    # Return async generator directly for streaming behavior
                    return self._process_streaming_chat(
                        message=message,
                        agent_name=agent_name,
                        user_id=user_id,
                    )
                else:
                    return await self._process_sync_chat(
                        message=message,
                        agent_name=agent_name,
                        user_id=user_id,
                        session_id=session_id,
                        request_id=request_id,
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

        # If no time estimator available, use sync
        if not hasattr(self.overlord, "time_estimator") or not self.overlord.time_estimator:
            return False

        try:
            # Estimate processing time
            estimated_time = await self.overlord.time_estimator.estimate_processing_time(
                message=message,
                agent_name=agent_name,
                formation_config=self.overlord.formation_config,
            )

            # Use async if estimated time exceeds threshold
            should_async = estimated_time > threshold_seconds

            # Emit decision event
            observability.observe(
                event_type=observability.ConversationEvents.ASYNC_DECISION_MADE,
                level=observability.EventLevel.INFO,
                data={
                    "estimated_time": estimated_time,
                    "threshold_seconds": threshold_seconds,
                    "decision": "async" if should_async else "sync",
                },
                description=f"Async decision: {estimated_time}s estimated, using {'async' if should_async else 'sync'}",
            )

            return should_async

        except Exception as e:
            # If estimation fails, default to sync
            observability.observe(
                event_type=observability.ConversationEvents.ASYNC_PROCESSING_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e)},
                description="Time estimation failed, defaulting to sync processing",
            )
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
        import asyncio
        from ..background.request_tracker import RequestStatus, RequestState

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

        # Create background task for async execution
        asyncio.create_task(
            self.overlord._execute_async_request(
                request_id=request_id,
                message=message,
                agent_name=agent_name,
                user_id=user_id,
            )
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
    ) -> str:
        """
        Process a chat request synchronously.

        Args:
            message: The user's message
            agent_name: Optional specific agent
            user_id: Optional user ID

        Returns:
            The response string
        """
        # Delegate to overlord's sync processing method
        return await self.overlord._process_sync_chat(
            message=message,
            agent_name=agent_name,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
        )

    async def _process_streaming_chat(
        self,
        message: str,
        agent_name: Optional[str],
        user_id: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Process a chat request with streaming.

        Args:
            message: The user's message
            agent_name: Optional specific agent
            user_id: Optional user ID

        Yields:
            Stream of response chunks
        """
        # Delegate to overlord's streaming processing method
        async for chunk in self.overlord._process_streaming_chat(
            message=message,
            agent_name=agent_name,
            user_id=user_id,
        ):
            yield chunk
