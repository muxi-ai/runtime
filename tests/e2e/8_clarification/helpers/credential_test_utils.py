"""
Test utilities for credential handling scenarios.

Provides helper functions for setting up test environments, mocking services,
and validating credential handling behavior across all test scenarios.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from muxi.formation.formation import Formation
from muxi.formation.overlord.overlord import Overlord
from muxi.formation.overlord.clarification import UnifiedClarificationSystem, ClarificationResponse
from muxi.formation.credentials.resolver import CredentialResolver
from muxi.services.logging.filters import CredentialRedactionFilter


class MockMCPService:
    """Mock MCP service for testing credential flows."""
    
    def __init__(self, service_id: str, auth_type: str, accept_inline: bool = False):
        self.id = service_id
        self.name = service_id.replace("_", " ").title()
        self.auth_type = auth_type
        self.accept_inline = accept_inline
        self.calls = []
        
    def record_call(self, method: str, **kwargs):
        """Record a call to this service."""
        self.calls.append({
            "method": method,
            "timestamp": datetime.now(),
            "kwargs": kwargs
        })
        
    def get_call_count(self, method: str = None) -> int:
        """Get number of calls to this service."""
        if method:
            return len([call for call in self.calls if call["method"] == method])
        return len(self.calls)


class CredentialTestEnvironment:
    """Test environment for credential handling scenarios."""
    
    def __init__(self, formation_config: Dict[str, Any]):
        self.formation_config = formation_config
        self.formation = None
        self.overlord = None
        self.clarification_system = None
        self.mock_services = {}
        self.credential_storage = {}
        self.log_captures = []
        
    async def setup(self):
        """Set up the test environment."""
        # Create formation
        self.formation = Formation(config=self.formation_config)
        
        # Create overlord with mocked dependencies
        self.overlord = Overlord(self.formation)
        await self._mock_overlord_dependencies()
        
        # Create clarification system
        self.clarification_system = UnifiedClarificationSystem(self.overlord)
        await self._mock_clarification_dependencies()
        
    async def _mock_overlord_dependencies(self):
        """Mock overlord dependencies for testing."""
        # Mock credential repository
        self.overlord.credential_repository = AsyncMock()
        self.overlord.credential_repository.store = AsyncMock(side_effect=self._store_credential)
        self.overlord.credential_repository.get = AsyncMock(side_effect=self._get_credential)
        
        # Mock buffer memory
        self.overlord.buffer_memory = AsyncMock()
        self.overlord.buffer_memory.add_memory = AsyncMock()
        self.overlord.buffer_memory.get_context = AsyncMock(return_value=[])
        
        # Mock MCP registry and coordinator
        self.overlord.mcp_registry = {}
        self.overlord.mcp_coordinator = MagicMock()
        self.overlord.mcp_coordinator.servers = {}
        
        # Mock LLM
        self.overlord.llm = AsyncMock()
        self.overlord.llm.chat = AsyncMock(side_effect=self._mock_llm_response)
        
    async def _mock_clarification_dependencies(self):
        """Mock clarification system dependencies."""
        # Override service discovery methods
        self.clarification_system._get_service_auth_type = AsyncMock(side_effect=self._get_service_auth_type)
        self.clarification_system._get_service_accept_inline = AsyncMock(side_effect=self._get_service_accept_inline)
        
        # Mock state management
        self.clarification_system._create_state = AsyncMock()
        self.clarification_system._store_state = AsyncMock()
        self.clarification_system._cleanup_state = AsyncMock()
        
    async def _store_credential(self, user_id: str, service: str, credentials: Dict[str, Any]):
        """Mock credential storage."""
        key = f"{user_id}:{service}"
        self.credential_storage[key] = {
            "credentials": credentials,
            "stored_at": datetime.now(),
            "last_used": None
        }
        
    async def _get_credential(self, user_id: str, service: str) -> Optional[Dict[str, Any]]:
        """Mock credential retrieval."""
        key = f"{user_id}:{service}"
        record = self.credential_storage.get(key)
        if record:
            record["last_used"] = datetime.now()
            return record["credentials"]
        return None
        
    async def _get_service_auth_type(self, service_id: str) -> str:
        """Mock service auth type discovery."""
        if service_id in self.mock_services:
            return self.mock_services[service_id].auth_type
        return "unknown"
        
    async def _get_service_accept_inline(self, service_id: str) -> bool:
        """Mock service inline acceptance discovery."""
        if service_id in self.mock_services:
            return self.mock_services[service_id].accept_inline
        return False
        
    async def _mock_llm_response(self, messages: List[Dict], **kwargs) -> str:
        """Mock LLM response for testing."""
        # Simple response based on last message content
        last_message = messages[-1].get("content", "") if messages else ""
        
        if "clarification" in last_message.lower():
            return "I need more information to help you."
        elif "credential" in last_message.lower():
            return "Please provide your credentials securely."
        else:
            return "I understand your request."
            
    def add_mock_service(self, service_id: str, auth_type: str, accept_inline: bool = False):
        """Add a mock MCP service."""
        service = MockMCPService(service_id, auth_type, accept_inline)
        self.mock_services[service_id] = service
        self.overlord.mcp_registry[service_id] = service
        return service
        
    async def simulate_credential_request(self, service_id: str, user_id: str) -> ClarificationResponse:
        """Simulate a credential request."""
        if service_id not in self.mock_services:
            raise ValueError(f"Service {service_id} not configured")
            
        request_id = f"req_{service_id}_{user_id}_{datetime.now().isoformat()}"
        
        # Mock get_state to return appropriate state
        mock_state = {
            "type": "credential",
            "service_id": service_id,
            "auth_type": self.mock_services[service_id].auth_type,
            "user_id": user_id,
            "original_request": f"Need access to {service_id}",
            "depth": 1,
            "max_depth": 1,
            "started_at": datetime.now().timestamp()
        }
        self.clarification_system._get_state = AsyncMock(return_value=mock_state)
        
        response = await self.clarification_system.handle_mcp_credential_request(
            service_id=service_id,
            user_id=user_id,
            request_id=request_id
        )
        
        return response
        
    async def provide_credential(self, user_id: str, service: str, credential_data: str, auth_type: str):
        """Simulate providing a credential."""
        # Parse credential based on auth type
        if auth_type == "basic":
            if ":" not in credential_data:
                raise ValueError("Basic auth must be in format username:password")
            username, password = credential_data.split(":", 1)
            credentials = {"username": username, "password": password, "type": "basic"}
        elif auth_type == "bearer":
            token = credential_data.replace("Bearer ", "")
            credentials = {"token": token, "type": "bearer"}
        else:  # api_key, oauth, etc.
            credentials = {"api_key": credential_data, "type": auth_type}
            
        await self._store_credential(user_id, service, credentials)
        
    async def cleanup(self):
        """Clean up test environment."""
        if self.overlord:
            # Clean up any async resources
            pass


class LogCapture:
    """Capture and filter logs for security testing."""
    
    def __init__(self, apply_filters: bool = True):
        self.records = []
        self.handler = None
        self.filter = CredentialRedactionFilter() if apply_filters else None
        
    def __enter__(self):
        self.handler = logging.Handler()
        self.handler.emit = self._capture_record
        
        # Add to all relevant loggers
        loggers = [
            logging.getLogger(),
            logging.getLogger("muxi"),
            logging.getLogger("muxi.formation"),
            logging.getLogger("muxi.services")
        ]
        
        for logger in loggers:
            logger.addHandler(self.handler)
            
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.handler:
            loggers = [
                logging.getLogger(),
                logging.getLogger("muxi"),
                logging.getLogger("muxi.formation"),
                logging.getLogger("muxi.services")
            ]
            
            for logger in loggers:
                logger.removeHandler(self.handler)
                
    def _capture_record(self, record):
        """Capture a log record, optionally applying filters."""
        if self.filter:
            # Apply credential redaction filter
            self.filter.filter(record)
        self.records.append(record)
        
    def get_messages(self) -> List[str]:
        """Get all captured log messages."""
        return [record.getMessage() for record in self.records]
        
    def contains_credential(self, credential: str) -> bool:
        """Check if any log contains the given credential."""
        messages = self.get_messages()
        return any(credential in msg for msg in messages)
        
    def contains_redaction(self) -> bool:
        """Check if logs contain redaction markers."""
        messages = self.get_messages()
        return any("***REDACTED***" in msg for msg in messages)


class SecurityValidator:
    """Validate security aspects of credential handling."""
    
    @staticmethod
    def assert_no_credentials_in_logs(logs: LogCapture, credentials: List[str]):
        """Assert that no credentials appear in logs."""
        messages = logs.get_messages()
        for credential in credentials:
            for message in messages:
                assert credential not in message, f"Credential '{credential}' found in log: {message}"
                
    @staticmethod
    def assert_redaction_applied(logs: LogCapture):
        """Assert that credential redaction was applied."""
        assert logs.contains_redaction(), "No credential redaction markers found in logs"
        
    @staticmethod
    def assert_no_credentials_in_llm_context(llm_calls: List[List], credentials: List[str]):
        """Assert that no credentials were sent to LLM."""
        for call_args in llm_calls:
            call_str = str(call_args)
            for credential in credentials:
                assert credential not in call_str, f"Credential '{credential}' found in LLM call"
                
    @staticmethod
    def assert_user_isolation(storage: Dict[str, Any], user1: str, user2: str):
        """Assert that users cannot access each other's credentials."""
        user1_keys = [key for key in storage.keys() if key.startswith(f"{user1}:")]
        user2_keys = [key for key in storage.keys() if key.startswith(f"{user2}:")]
        
        # Each user should only have their own credentials
        assert all(not key.startswith(f"{user2}:") for key in user1_keys)
        assert all(not key.startswith(f"{user1}:") for key in user2_keys)


class ResponseValidator:
    """Validate credential handling responses."""
    
    @staticmethod
    def assert_is_redirect(response: ClarificationResponse):
        """Assert response is a redirect."""
        assert response.action == "redirect"
        redirect_indicators = ["outside", "browser", "external", "portal", "configure"]
        assert any(indicator in response.message.lower() for indicator in redirect_indicators)
        
    @staticmethod
    def assert_requests_inline(response: ClarificationResponse):
        """Assert response requests inline credential entry."""
        assert response.action == "clarify"
        assert hasattr(response, 'question')
        credential_indicators = ["provide", "enter", "credential", "key", "token", "password"]
        assert any(indicator in response.question.lower() for indicator in credential_indicators)
        
    @staticmethod
    def assert_contains_security_warning(response: ClarificationResponse):
        """Assert response contains appropriate security warning."""
        if hasattr(response, 'question'):
            warning_indicators = ["⚠️", "warning", "caution", "security", "careful"]
            assert any(indicator in response.question.lower() for indicator in warning_indicators)
            
    @staticmethod
    def assert_no_credential_echo(response: ClarificationResponse, credentials: List[str]):
        """Assert response doesn't echo back any credentials."""
        response_text = ""
        if hasattr(response, 'message'):
            response_text += response.message
        if hasattr(response, 'question'):
            response_text += response.question
            
        for credential in credentials:
            assert credential not in response_text, f"Credential '{credential}' echoed in response"


# Utility functions for common test patterns

async def create_test_environment(mode: str = "dynamic", **kwargs) -> CredentialTestEnvironment:
    """Create a test environment with specified mode."""
    from .fixtures.credential_test_formations import get_formation_template
    
    if mode == "redirect":
        config = get_formation_template("redirect_mode")
    elif mode == "dynamic":
        config = get_formation_template("dynamic_mode")
    else:
        config = get_formation_template("minimal")
        
    # Apply any overrides
    if kwargs:
        config.update(kwargs)
        
    env = CredentialTestEnvironment(config)
    await env.setup()
    return env


def create_mock_llm_tracer():
    """Create a tracer for LLM calls to detect credential leakage."""
    calls = []
    
    async def mock_chat(*args, **kwargs):
        calls.append({
            "args": args,
            "kwargs": kwargs,
            "timestamp": datetime.now()
        })
        return "Mock LLM response"
        
    return mock_chat, calls


@asynccontextmanager
async def isolated_test_run():
    """Context manager for isolated test execution."""
    # Set up test isolation
    original_state = {}
    
    try:
        yield
    finally:
        # Clean up test state
        pass


def generate_test_credentials() -> Dict[str, str]:
    """Generate test credentials for different auth types."""
    return {
        "api_key": "sk-test-1234567890abcdef",
        "basic": "testuser:testpass123",
        "bearer": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "oauth": "oauth-token-abcdef123456",
        "github": "ghp_1234567890abcdef123456789012345678",
        "openai": "sk-proj-abcdefghijklmnop1234567890",
        "slack": "xoxb-1234567890-abcdefghijklmnopqrstuvwx"
    }


def assert_credential_format(credential: str, auth_type: str):
    """Assert credential matches expected format for auth type."""
    patterns = {
        "api_key": r"^[a-zA-Z0-9-_]{20,}$",
        "github": r"^ghp_[a-zA-Z0-9]{36}$",
        "openai": r"^sk-[a-zA-Z0-9-]{20,}$",
        "bearer": r"^[a-zA-Z0-9-._~+/]+=*$"
    }
    
    if auth_type in patterns:
        import re
        assert re.match(patterns[auth_type], credential), f"Invalid {auth_type} format: {credential}"


class TestMetrics:
    """Collect metrics during test execution."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.credential_requests = 0
        self.redirects = 0
        self.inline_acceptances = 0
        self.security_warnings = 0
        self.llm_calls = 0
        
    def start(self):
        """Start metrics collection."""
        self.start_time = datetime.now()
        
    def stop(self):
        """Stop metrics collection."""
        self.end_time = datetime.now()
        
    def record_credential_request(self):
        """Record a credential request."""
        self.credential_requests += 1
        
    def record_redirect(self):
        """Record a redirect response."""
        self.redirects += 1
        
    def record_inline_acceptance(self):
        """Record an inline acceptance."""
        self.inline_acceptances += 1
        
    def record_security_warning(self):
        """Record a security warning."""
        self.security_warnings += 1
        
    def record_llm_call(self):
        """Record an LLM call."""
        self.llm_calls += 1
        
    def get_duration(self) -> Optional[timedelta]:
        """Get test duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
        
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        return {
            "duration": self.get_duration(),
            "credential_requests": self.credential_requests,
            "redirects": self.redirects,
            "inline_acceptances": self.inline_acceptances,
            "security_warnings": self.security_warnings,
            "llm_calls": self.llm_calls
        }