#!/usr/bin/env python3
"""Unit tests for pending clarification buffer memory migration."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any, Optional

# Import the Overlord class
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.overlord.overlord import Overlord


class TestPendingClarificationMigration:
    """Test suite for pending clarification buffer memory migration."""

    @pytest.fixture
    def mock_buffer_memory(self):
        """Create a mock buffer memory with KV store methods."""
        buffer_memory = MagicMock()
        buffer_memory.kv_get = AsyncMock(return_value=None)
        buffer_memory.kv_set = AsyncMock(return_value=True)
        buffer_memory.kv_delete = AsyncMock(return_value=True)
        return buffer_memory

    @pytest.fixture
    def overlord_with_buffer(self, mock_buffer_memory):
        """Create an Overlord instance with mocked buffer memory."""
        # Mock the observability manager
        mock_observability_manager = MagicMock()
        
        # Provide configured services with observability manager
        configured_services = {
            "observability_manager": mock_observability_manager
        }
        
        overlord = Overlord(
            configured_services=configured_services,
            buffer_memory=mock_buffer_memory
        )
        overlord.pending_clarification_namespace = "pending_clarification"
        return overlord

    @pytest.mark.asyncio
    async def test_get_pending_clarification_success(self, overlord_with_buffer, mock_buffer_memory):
        """Test successful retrieval of pending clarification."""
        # Setup
        session_id = "test_session_123"
        expected_data = {
            "request_id": "req_456",
            "type": "clarification",
            "timestamp": 1234567890
        }
        mock_buffer_memory.kv_get.return_value = expected_data

        # Execute
        result = await overlord_with_buffer._get_pending_clarification(session_id)

        # Assert
        assert result == expected_data
        mock_buffer_memory.kv_get.assert_called_once_with(
            key=session_id,
            namespace="pending_clarification"
        )

    @pytest.mark.asyncio
    async def test_get_pending_clarification_not_found(self, overlord_with_buffer, mock_buffer_memory):
        """Test retrieval when no pending clarification exists."""
        # Setup
        session_id = "test_session_123"
        mock_buffer_memory.kv_get.return_value = None

        # Execute
        result = await overlord_with_buffer._get_pending_clarification(session_id)

        # Assert
        assert result is None
        mock_buffer_memory.kv_get.assert_called_once_with(
            key=session_id,
            namespace="pending_clarification"
        )

    @pytest.mark.asyncio
    async def test_get_pending_clarification_no_session(self, overlord_with_buffer, mock_buffer_memory):
        """Test retrieval with no session ID."""
        # Execute
        result = await overlord_with_buffer._get_pending_clarification(None)

        # Assert
        assert result is None
        mock_buffer_memory.kv_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_pending_clarification_no_buffer(self, overlord_with_buffer):
        """Test retrieval when buffer memory is not available."""
        # Setup
        overlord_with_buffer.buffer_memory = None

        # Execute
        result = await overlord_with_buffer._get_pending_clarification("test_session")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_pending_clarification_error_handling(self, overlord_with_buffer, mock_buffer_memory):
        """Test error handling during retrieval."""
        # Setup
        session_id = "test_session_123"
        mock_buffer_memory.kv_get.side_effect = Exception("KV store error")

        # Execute
        result = await overlord_with_buffer._get_pending_clarification(session_id)

        # Assert
        assert result is None
        mock_buffer_memory.kv_get.assert_called_once()

    def test_set_pending_clarification_success(self, overlord_with_buffer, mock_buffer_memory):
        """Test successful storage of pending clarification."""
        # Setup
        session_id = "test_session_123"
        data = {
            "request_id": "req_456",
            "type": "workflow_approval",
            "timestamp": 1234567890
        }

        # Execute
        with patch('asyncio.create_task') as mock_create_task:
            overlord_with_buffer._set_pending_clarification(session_id, data)

            # Assert
            mock_create_task.assert_called_once()
            # Get the coroutine that was passed to create_task
            coro = mock_create_task.call_args[0][0]
            # Run it to verify it calls the right method
            asyncio.run(coro)

        mock_buffer_memory.kv_set.assert_called_once_with(
            key=session_id,
            value=data,
            ttl=None,
            namespace="pending_clarification"
        )

    def test_set_pending_clarification_no_session(self, overlord_with_buffer, mock_buffer_memory):
        """Test storage with no session ID."""
        # Setup
        data = {"request_id": "req_456"}

        # Execute
        with patch('asyncio.create_task') as mock_create_task:
            overlord_with_buffer._set_pending_clarification(None, data)

            # Assert
            mock_create_task.assert_not_called()

    def test_set_pending_clarification_no_buffer(self, overlord_with_buffer):
        """Test storage when buffer memory is not available."""
        # Setup
        overlord_with_buffer.buffer_memory = None
        session_id = "test_session_123"
        data = {"request_id": "req_456"}

        # Execute
        with patch('asyncio.create_task') as mock_create_task:
            overlord_with_buffer._set_pending_clarification(session_id, data)

            # Assert
            mock_create_task.assert_not_called()

    def test_delete_pending_clarification_success(self, overlord_with_buffer, mock_buffer_memory):
        """Test successful deletion of pending clarification."""
        # Setup
        session_id = "test_session_123"

        # Execute
        with patch('asyncio.create_task') as mock_create_task:
            overlord_with_buffer._delete_pending_clarification(session_id)

            # Assert
            mock_create_task.assert_called_once()
            # Get the coroutine that was passed to create_task
            coro = mock_create_task.call_args[0][0]
            # Run it to verify it calls the right method
            asyncio.run(coro)

        mock_buffer_memory.kv_delete.assert_called_once_with(
            key=session_id,
            namespace="pending_clarification"
        )

    def test_delete_pending_clarification_no_session(self, overlord_with_buffer, mock_buffer_memory):
        """Test deletion with no session ID."""
        # Execute
        with patch('asyncio.create_task') as mock_create_task:
            overlord_with_buffer._delete_pending_clarification(None)

            # Assert
            mock_create_task.assert_not_called()

    def test_delete_pending_clarification_no_buffer(self, overlord_with_buffer):
        """Test deletion when buffer memory is not available."""
        # Setup
        overlord_with_buffer.buffer_memory = None
        session_id = "test_session_123"

        # Execute
        with patch('asyncio.create_task') as mock_create_task:
            overlord_with_buffer._delete_pending_clarification(session_id)

            # Assert
            mock_create_task.assert_not_called()

    def test_namespace_constant_exists(self, overlord_with_buffer):
        """Test that the namespace constant is properly set."""
        assert hasattr(overlord_with_buffer, 'pending_clarification_namespace')
        assert overlord_with_buffer.pending_clarification_namespace == "pending_clarification"

    def test_no_dict_attribute(self):
        """Test that the old dict attribute is not present."""
        # Mock the observability manager
        mock_observability_manager = MagicMock()
        
        # Provide configured services with observability manager
        configured_services = {
            "observability_manager": mock_observability_manager
        }
        
        overlord = Overlord(configured_services=configured_services)
        # The _pending_clarifications dict should not exist
        assert not hasattr(overlord, '_pending_clarifications')

    @pytest.mark.asyncio
    async def test_fire_and_forget_optimization(self, overlord_with_buffer, mock_buffer_memory):
        """Test that set and delete operations are fire-and-forget."""
        # Setup
        session_id = "test_session_123"
        data = {"request_id": "req_456"}

        # Test set operation
        with patch('asyncio.create_task') as mock_create_task:
            # Call should return immediately without awaiting
            result = overlord_with_buffer._set_pending_clarification(session_id, data)
            assert result is None  # Should return None, not a coroutine
            mock_create_task.assert_called_once()

        # Test delete operation
        with patch('asyncio.create_task') as mock_create_task:
            # Call should return immediately without awaiting
            result = overlord_with_buffer._delete_pending_clarification(session_id)
            assert result is None  # Should return None, not a coroutine
            mock_create_task.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])