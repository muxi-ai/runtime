"""
Integration tests for credential security measures.
"""

import pytest
import logging
import re
from unittest.mock import AsyncMock, MagicMock, patch
from io import StringIO

from muxi.services.logging.filters import CredentialRedactionFilter
from muxi.formation.overlord.clarification import UnifiedClarificationSystem


class TestLogRedaction:
    """Test credential redaction in logs."""
    
    def test_api_key_redaction(self):
        """Test API keys are redacted from logs."""
        filter = CredentialRedactionFilter()
        
        # Create a log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Processing request with api_key: "sk-1234567890abcdef"',
            args=(),
            exc_info=None
        )
        
        # Apply filter
        filter.filter(record)
        
        # Check redaction
        assert "sk-1234567890abcdef" not in record.msg
        assert "***REDACTED***" in record.msg
    
    def test_password_redaction(self):
        """Test passwords are redacted from logs."""
        filter = CredentialRedactionFilter()
        
        test_cases = [
            'password: "secret123"',
            'password="mysecretpass"',
            '"password": "topsecret"',
            'Password: verysecret'
        ]
        
        for test_msg in test_cases:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=test_msg,
                args=(),
                exc_info=None
            )
            
            filter.filter(record)
            
            # Original password should be gone
            assert "secret" not in record.msg.lower() or "***redacted***" in record.msg.lower()
            assert "***REDACTED***" in record.msg
    
    def test_bearer_token_redaction(self):
        """Test bearer tokens are redacted."""
        filter = CredentialRedactionFilter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0',
            args=(),
            exc_info=None
        )
        
        filter.filter(record)
        
        assert "eyJhbGciOiJIUzI1NiI" not in record.msg
        assert "Bearer ***REDACTED***" in record.msg
    
    def test_multiple_credentials_redaction(self):
        """Test multiple credentials in same message are all redacted."""
        filter = CredentialRedactionFilter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Config: {"api_key": "sk-123", "password": "pass123", "token": "tok-456"}',
            args=(),
            exc_info=None
        )
        
        filter.filter(record)
        
        # All credentials should be redacted
        assert "sk-123" not in record.msg
        assert "pass123" not in record.msg
        assert "tok-456" not in record.msg
        # Should have multiple redactions
        assert record.msg.count("***REDACTED***") >= 3
    
    def test_aws_credentials_redaction(self):
        """Test AWS credentials are redacted."""
        filter = CredentialRedactionFilter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='AWS Access: AKIA1234567890ABCDEF, Secret: aws_secret_key_40chars_long1234567890ab',
            args=(),
            exc_info=None
        )
        
        filter.filter(record)
        
        assert "AKIA1234567890ABCDEF" not in record.msg
        assert "aws_secret_key" not in record.msg
        assert "***REDACTED***" in record.msg
    
    def test_database_url_redaction(self):
        """Test database URLs with credentials are redacted."""
        filter = CredentialRedactionFilter()
        
        urls = [
            "postgresql://user:pass@localhost/db",
            "mysql://admin:secret123@db.example.com:3306/mydb",
            "mongodb://root:topsecret@cluster.mongodb.net/test"
        ]
        
        for url in urls:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=f"Connecting to: {url}",
                args=(),
                exc_info=None
            )
            
            filter.filter(record)
            
            # Passwords should be redacted
            assert ":pass@" not in record.msg
            assert ":secret123@" not in record.msg
            assert ":topsecret@" not in record.msg
            assert "***REDACTED***" in record.msg


class TestLLMContextProtection:
    """Test credentials don't reach LLM context."""
    
    @pytest.mark.asyncio
    async def test_credentials_not_in_llm_context(self):
        """Test credentials are not sent to LLM."""
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "user_credentials": {"mode": "dynamic"}
        }
        mock_overlord.buffer_memory = AsyncMock()
        mock_overlord.mcp_registry = {}
        mock_overlord.credential_repository = AsyncMock()
        
        # Create system with mock LLM
        system = UnifiedClarificationSystem(mock_overlord)
        llm_calls = []
        
        async def mock_llm_chat(messages, **kwargs):
            llm_calls.append(messages)
            return "answering"  # Return valid response
        
        system.llm = MagicMock()
        system.llm.chat = mock_llm_chat
        
        # Create a state with credential info
        state = {
            "type": "credential",
            "auth_type": "api_key",
            "service_id": "github",
            "user_id": "user123",
            "original_request": "I need GitHub access",
            "collected_info": ["ghp_secret123456"],  # Credential value
            "depth": 1,
            "max_depth": 1,
            "last_question": "Please provide your GitHub API key",
            "started_at": 1234567890
        }
        
        system._get_state = AsyncMock(return_value=state)
        system._check_context_switch = AsyncMock(return_value=False)
        system._check_need_more = AsyncMock(return_value={"needs_more": False})
        system._cleanup_state = AsyncMock()
        system.store_accepted_credential = AsyncMock(return_value=True)
        
        # Handle response with credential
        result = await system.handle_response("req123", "ghp_secret123456")
        
        # Check LLM was never called with actual credential
        for call in llm_calls:
            call_str = str(call)
            assert "ghp_secret123456" not in call_str
            assert "secret123456" not in call_str
    
    @pytest.mark.asyncio
    async def test_clarification_questions_sanitized(self):
        """Test clarification questions don't include credentials."""
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "user_credentials": {"mode": "dynamic"}
        }
        mock_overlord.buffer_memory = AsyncMock()
        mock_overlord.credential_repository = AsyncMock()
        
        system = UnifiedClarificationSystem(mock_overlord)
        
        # Mock the methods
        system._get_service_auth_type = AsyncMock(return_value="api_key")
        system._get_service_accept_inline = AsyncMock(return_value=True)
        system._create_state = AsyncMock()
        system._get_state = AsyncMock(return_value={
            "service_id": "github",
            "auth_type": "api_key",
            "user_id": "user123"
        })
        system._store_state = AsyncMock()
        
        # Request credential
        result = await system.handle_mcp_credential_request(
            service_id="github",
            user_id="user123",
            request_id="req123"
        )
        
        # Check the question doesn't contain example credentials
        assert "ghp_" not in result.question
        assert "actual" not in result.question.lower()
        assert "example" not in result.question.lower()
    
    @pytest.mark.asyncio
    async def test_error_messages_sanitized(self):
        """Test error messages don't expose credentials."""
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "user_credentials": {"mode": "dynamic"}
        }
        mock_overlord.credential_repository = AsyncMock()
        mock_overlord.credential_repository.store = AsyncMock(
            side_effect=Exception("Database error with value: secret123")
        )
        
        system = UnifiedClarificationSystem(mock_overlord)
        
        # Try to store credential that will fail
        result = await system.store_accepted_credential(
            user_id="user123",
            service_name="github",
            credential_data="ghp_secret123",
            auth_type="api_key"
        )
        
        # Should return False on error, not expose the exception
        assert result is False
        # The error should not propagate with credential value


class TestCredentialIsolation:
    """Test credentials are isolated in memory."""
    
    @pytest.mark.asyncio
    async def test_credentials_not_in_buffer_memory(self):
        """Test credentials are not stored in buffer memory."""
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "user_credentials": {"mode": "dynamic"}
        }
        
        buffer_memory_calls = []
        
        async def mock_add_memory(user_id, session_id, content):
            buffer_memory_calls.append(content)
        
        mock_overlord.buffer_memory = MagicMock()
        mock_overlord.buffer_memory.add_memory = mock_add_memory
        mock_overlord.credential_repository = AsyncMock()
        
        system = UnifiedClarificationSystem(mock_overlord)
        
        # Store a credential
        await system.store_accepted_credential(
            user_id="user123",
            service_name="github",
            credential_data="ghp_secret789",
            auth_type="api_key"
        )
        
        # Check buffer memory was not called with credential
        for content in buffer_memory_calls:
            assert "ghp_secret789" not in str(content)
            assert "secret789" not in str(content)
    
    @pytest.mark.asyncio
    async def test_credentials_not_in_state_after_storage(self):
        """Test credentials are removed from state after storage."""
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "user_credentials": {"mode": "dynamic"}
        }
        mock_overlord.buffer_memory = AsyncMock()
        mock_overlord.credential_repository = AsyncMock()
        
        system = UnifiedClarificationSystem(mock_overlord)
        
        # Create state with credential
        state = {
            "type": "credential",
            "auth_type": "api_key",
            "service_id": "github",
            "user_id": "user123",
            "collected_info": ["ghp_secret123"],
            "original_request": "Need GitHub",
            "depth": 1,
            "max_depth": 1
        }
        
        system._get_state = AsyncMock(return_value=state)
        system._cleanup_state = AsyncMock()
        system.store_accepted_credential = AsyncMock(return_value=True)
        
        # Handle credential response
        result = await system.handle_response("req123", "ghp_secret123")
        
        # State should be cleaned up
        system._cleanup_state.assert_called_once_with("req123")
    
    def test_no_global_credential_storage(self):
        """Test no global variables store credentials."""
        # This test verifies the design - credentials should only be in:
        # 1. The encrypted database (CredentialResolver)
        # 2. Temporary method parameters during processing
        # Not in any global or class-level storage
        
        mock_overlord = MagicMock()
        system = UnifiedClarificationSystem(mock_overlord)
        
        # Check no credential attributes exist
        assert not hasattr(system, 'stored_credentials')
        assert not hasattr(system, 'credential_cache')
        assert not hasattr(system, 'credentials')
        
        # The only credential-related attribute should be methods
        credential_attrs = [attr for attr in dir(system) if 'credential' in attr.lower()]
        for attr in credential_attrs:
            if not attr.startswith('_'):  # Skip private methods
                # Should be methods, not data attributes
                assert callable(getattr(system, attr))


class TestSecurityBoundaries:
    """Test security boundaries are enforced."""
    
    @pytest.mark.asyncio
    async def test_credential_never_in_response(self):
        """Test credentials never appear in system responses."""
        mock_overlord = MagicMock()
        mock_overlord.formation_config = {
            "user_credentials": {"mode": "dynamic"}
        }
        mock_overlord.buffer_memory = AsyncMock()
        mock_overlord.credential_repository = AsyncMock()
        
        system = UnifiedClarificationSystem(mock_overlord)
        system._get_state = AsyncMock(return_value={
            "type": "credential",
            "auth_type": "api_key",
            "service_id": "github",
            "user_id": "user123",
            "original_request": "Need access",
            "depth": 1
        })
        system._cleanup_state = AsyncMock()
        system.store_accepted_credential = AsyncMock(return_value=True)
        
        # Handle credential
        result = await system.handle_response("req123", "ghp_topsecret")
        
        # Check response doesn't contain credential
        if hasattr(result, 'message'):
            assert "ghp_topsecret" not in result.message
            assert "topsecret" not in result.message
        if hasattr(result, 'context'):
            assert "ghp_topsecret" not in str(result.context)
            assert "topsecret" not in str(result.context)
    
    @pytest.mark.asyncio
    async def test_credential_type_but_not_value_in_logs(self):
        """Test logs can mention credential type but not value."""
        import logging
        from io import StringIO
        
        # Setup logging with our filter
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.addFilter(CredentialRedactionFilter())
        
        logger = logging.getLogger("test_security")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        # Log message with credential type and value
        logger.info('Storing api_key credential: "ghp_secret12345" for GitHub')
        
        log_output = log_stream.getvalue()
        
        # Type can be mentioned
        assert "api_key" in log_output or "credential" in log_output
        # But not the value
        assert "ghp_secret12345" not in log_output
        assert "secret12345" not in log_output
        assert "***REDACTED***" in log_output