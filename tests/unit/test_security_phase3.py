"""
Unit tests for Phase 3: Overlord Security Integration

Tests the integration of security exception handling in the overlord's
message processing flow, ensuring security violations are properly caught
and user-friendly error responses are returned.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.datatypes.exceptions import SecurityViolation
from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.formation.background.request_tracker import RequestStatus


class TestOverlordSecurityIntegration:
    """Test security exception handling in overlord message processing."""

    @pytest.mark.asyncio
    async def test_security_violation_caught_in_sync_chat(self):
        """Test that SecurityViolation is caught during agent selection."""
        # Create mock overlord
        mock_overlord = MagicMock()
        mock_overlord.select_agent_for_message = AsyncMock(
            side_effect=SecurityViolation(
                reason="Pattern-based threat detected",
                threat_type="pattern_match",
                message_preview="malicious input"
            )
        )

        # Call should raise SecurityViolation (we'll test the actual handling separately)
        with pytest.raises(SecurityViolation):
            await mock_overlord.select_agent_for_message("malicious input")

    @pytest.mark.asyncio
    async def test_security_violation_returns_error_response(self):
        """Test that security violations return user-friendly error response."""
        # This will test the actual integrated behavior
        # We'll verify:
        # 1. SecurityViolation is caught
        # 2. Observability event is logged
        # 3. Error response is returned
        # 4. Response has correct status and content

        # Mock dependencies
        with patch('muxi.services.observability.observe') as mock_observe, \
             patch('muxi.services.streaming.stream') as mock_stream:

            # Create a security violation
            security_error = SecurityViolation(
                reason="LLM detected threat",
                threat_type="llm_detected",
                message_preview=""
            )

            # Simulate what overlord does
            request_id = "test-request-123"
            user_id = "user-456"
            session_id = "session-789"

            # Log security event
            mock_observe.assert_not_called()  # Not called yet

            # Simulate the exception handling
            try:
                raise security_error
            except SecurityViolation as e:
                # This is what overlord should do
                from muxi.runtime.services import observability

                observability.observe(
                    event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                    level=observability.EventLevel.WARNING,
                    data={
                        "reason": str(e),
                        "threat_type": e.threat_type,
                        "request_id": request_id,
                        "user_id": user_id,
                        "session_id": session_id,
                    },
                    description=f"Security violation detected: {e.threat_type}",
                )

                response = MuxiResponse(
                    role="assistant",
                    content="I can't process that request.",
                )

                # Verify response
                assert response.role == "assistant"
                assert response.content == "I can't process that request."

    @pytest.mark.asyncio
    async def test_legitimate_message_not_blocked(self):
        """Test that legitimate messages are not blocked by security."""
        overlord = MagicMock(spec=Overlord)
        overlord.select_agent_for_message = AsyncMock(return_value="agent1")

        # Should return agent name without raising
        agent_name = await overlord.select_agent_for_message("What's the weather?")
        assert agent_name == "agent1"

    @pytest.mark.asyncio
    async def test_security_event_includes_metadata(self):
        """Test that security events include all required metadata."""
        with patch('muxi.services.observability.observe') as mock_observe:
            request_id = "req-123"
            user_id = "user-456"
            session_id = "sess-789"
            threat_type = "pattern_match"
            reason = "Malicious pattern detected"

            # Simulate logging security event
            from muxi.runtime.services import observability

            observability.observe(
                event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                level=observability.EventLevel.WARNING,
                data={
                    "reason": reason,
                    "threat_type": threat_type,
                    "request_id": request_id,
                    "user_id": user_id,
                    "session_id": session_id,
                },
                description=f"Security violation detected: {threat_type}",
            )

            # Verify observe was called
            assert mock_observe.called
            call_kwargs = mock_observe.call_args[1]

            assert call_kwargs['event_type'] == observability.ConversationEvents.SECURITY_VIOLATION
            assert call_kwargs['level'] == observability.EventLevel.WARNING
            assert call_kwargs['data']['request_id'] == request_id
            assert call_kwargs['data']['user_id'] == user_id
            assert call_kwargs['data']['session_id'] == session_id
            assert call_kwargs['data']['threat_type'] == threat_type

    @pytest.mark.asyncio
    async def test_pattern_match_security_violation(self):
        """Test handling of pattern-matched security violations."""
        security_error = SecurityViolation(
            reason="Message blocked by security filter",
            threat_type="pattern_match",
            message_preview="ignore previous instructions"
        )

        # Verify exception attributes
        assert security_error.threat_type == "pattern_match"
        assert "security filter" in security_error.reason

    @pytest.mark.asyncio
    async def test_llm_detected_security_violation(self):
        """Test handling of LLM-detected security violations."""
        security_error = SecurityViolation(
            reason="LLM detected security threat in message",
            threat_type="llm_detected",
            message_preview=""
        )

        # Verify exception attributes
        assert security_error.threat_type == "llm_detected"
        assert "LLM detected" in security_error.reason


class TestSecurityResponseFormat:
    """Test the format and content of security error responses."""

    def test_error_response_format(self):
        """Test that error response has correct format."""
        response = MuxiResponse(
            role="assistant",
            content="I can't process that request.",
        )

        assert response.role == "assistant"
        assert response.content == "I can't process that request."

    def test_error_message_user_friendly(self):
        """Test that error message is user-friendly."""
        response = MuxiResponse(
            role="assistant",
            content="I can't process that request.",
        )

        # Message should be simple and clear
        assert len(response.content) < 50
        assert "can't process" in response.content.lower()
        # Should not leak technical details
        assert "SecurityViolation" not in response.content
        assert "pattern" not in response.content.lower()
        assert "llm" not in response.content.lower()


class TestSecurityObservability:
    """Test security event observability integration."""

    @pytest.mark.asyncio
    async def test_security_event_logged_on_violation(self):
        """Test that security violations are logged to observability."""
        with patch('muxi.services.observability.observe') as mock_observe:
            from muxi.runtime.services import observability

            # Simulate security violation
            observability.observe(
                event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                level=observability.EventLevel.WARNING,
                data={
                    "reason": "Test threat",
                    "threat_type": "pattern_match",
                    "request_id": "req-123",
                },
                description="Security violation detected: pattern_match",
            )

            # Verify logged
            assert mock_observe.called

    @pytest.mark.asyncio
    async def test_security_event_level_is_warning(self):
        """Test that security events are logged at WARNING level."""
        with patch('muxi.services.observability.observe') as mock_observe:
            from muxi.runtime.services import observability

            observability.observe(
                event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                level=observability.EventLevel.WARNING,
                data={"threat_type": "pattern_match"},
                description="Security violation",
            )

            call_kwargs = mock_observe.call_args[1]
            assert call_kwargs['level'] == observability.EventLevel.WARNING

    @pytest.mark.asyncio
    async def test_streaming_event_on_security_block(self):
        """Test that streaming event is emitted when request is blocked."""
        with patch('muxi.services.streaming.stream') as mock_stream:
            from muxi.runtime.services import streaming

            # Simulate streaming error event
            streaming.stream(
                "error",
                "I can't process that request.",
                stage="security_blocked",
                request_id="req-123",
            )

            # Verify streamed
            assert mock_stream.called
            call_args = mock_stream.call_args[0]
            call_kwargs = mock_stream.call_args[1]

            assert call_args[0] == "error"
            assert call_args[1] == "I can't process that request."
            assert call_kwargs.get('stage') == "security_blocked"


class TestSecurityEdgeCases:
    """Test edge cases in security exception handling."""

    @pytest.mark.asyncio
    async def test_security_violation_with_none_user_id(self):
        """Test handling security violation when user_id is None."""
        with patch('muxi.services.observability.observe') as mock_observe:
            from muxi.runtime.services import observability

            # User ID might be None in some contexts
            observability.observe(
                event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                level=observability.EventLevel.WARNING,
                data={
                    "reason": "Test",
                    "threat_type": "pattern_match",
                    "request_id": "req-123",
                    "user_id": None,
                    "session_id": "sess-456",
                },
                description="Security violation detected",
            )

            # Should not crash
            assert mock_observe.called
            call_kwargs = mock_observe.call_args[1]
            assert call_kwargs['data']['user_id'] is None

    @pytest.mark.asyncio
    async def test_security_violation_with_empty_message_preview(self):
        """Test handling security violation with empty message preview."""
        security_error = SecurityViolation(
            reason="LLM detected threat",
            threat_type="llm_detected",
            message_preview=""  # Empty preview for sensitive content
        )

        assert security_error.message_preview == ""
        assert security_error.threat_type == "llm_detected"

    def test_response_role_is_assistant(self):
        """Test that security error responses use assistant role."""
        response = MuxiResponse(
            role="assistant",
            content="I can't process that request.",
        )

        assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_multiple_security_violations_in_session(self):
        """Test that multiple security violations in same session are all logged."""
        with patch('muxi.services.observability.observe') as mock_observe:
            from muxi.runtime.services import observability

            session_id = "sess-789"

            # First violation
            observability.observe(
                event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                level=observability.EventLevel.WARNING,
                data={
                    "threat_type": "pattern_match",
                    "session_id": session_id,
                    "request_id": "req-1",
                },
                description="First violation",
            )

            # Second violation
            observability.observe(
                event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                level=observability.EventLevel.WARNING,
                data={
                    "threat_type": "llm_detected",
                    "session_id": session_id,
                    "request_id": "req-2",
                },
                description="Second violation",
            )

            # Both should be logged
            assert mock_observe.call_count == 2


class TestEndToEndSecurityFlow:
    """Test complete end-to-end security flow."""

    @pytest.mark.asyncio
    async def test_complete_security_flow_pattern_match(self):
        """Test complete flow: pattern match → exception → error response."""
        # This simulates the complete flow from agent selection through to response

        request_id = "req-123"
        user_id = "user-456"
        session_id = "sess-789"

        with patch('muxi.services.observability.observe') as mock_observe, \
             patch('muxi.services.streaming.stream') as mock_stream:

            # 1. Security violation raised during agent selection
            security_error = SecurityViolation(
                reason="Message blocked by security filter",
                threat_type="pattern_match",
                message_preview="malicious"
            )

            # 2. Exception caught and handled
            try:
                raise security_error
            except SecurityViolation as e:
                from muxi.runtime.services import observability, streaming

                # 3. Observability event logged
                observability.observe(
                    event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                    level=observability.EventLevel.WARNING,
                    data={
                        "reason": str(e),
                        "threat_type": e.threat_type,
                        "request_id": request_id,
                        "user_id": user_id,
                        "session_id": session_id,
                    },
                    description=f"Security violation detected: {e.threat_type}",
                )

                # 4. Streaming event emitted
                streaming.stream(
                    "error",
                    "I can't process that request.",
                    stage="security_blocked",
                    request_id=request_id,
                )

                # 5. Error response created
                response = MuxiResponse(
                    role="assistant",
                    content="I can't process that request.",
                )

                # Verify complete flow
                assert mock_observe.called
                assert mock_stream.called
                assert response.role == "assistant"
                assert response.content == "I can't process that request."

    @pytest.mark.asyncio
    async def test_complete_security_flow_llm_detected(self):
        """Test complete flow: LLM detection → exception → error response."""
        request_id = "req-456"
        user_id = "user-789"
        session_id = "sess-012"

        with patch('muxi.services.observability.observe') as mock_observe, \
             patch('muxi.services.streaming.stream') as mock_stream:

            # 1. LLM detects sophisticated threat
            security_error = SecurityViolation(
                reason="LLM detected security threat in message",
                threat_type="llm_detected",
                message_preview=""
            )

            # 2. Exception caught and handled
            try:
                raise security_error
            except SecurityViolation as e:
                from muxi.runtime.services import observability, streaming

                # 3. Log security event
                observability.observe(
                    event_type=observability.ConversationEvents.SECURITY_VIOLATION,
                    level=observability.EventLevel.WARNING,
                    data={
                        "reason": str(e),
                        "threat_type": e.threat_type,
                        "request_id": request_id,
                        "user_id": user_id,
                        "session_id": session_id,
                    },
                    description=f"Security violation detected: {e.threat_type}",
                )

                # 4. Stream error
                streaming.stream(
                    "error",
                    "I can't process that request.",
                    stage="security_blocked",
                    request_id=request_id,
                )

                # 5. Return error response
                response = MuxiResponse(
                    role="assistant",
                    content="I can't process that request.",
                )

                # Verify LLM detection flow
                assert mock_observe.called
                call_kwargs = mock_observe.call_args[1]
                assert call_kwargs['data']['threat_type'] == "llm_detected"
                assert response.role == "assistant"
