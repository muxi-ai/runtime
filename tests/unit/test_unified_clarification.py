"""
Unit tests for the UnifiedClarificationSystem
Tests the complete replacement of 15+ clarification components with one unified class
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, Optional

from src.muxi.formation.overlord.clarification import (
    UnifiedClarificationSystem,
    ClarificationResult
)


class MockBufferMemory:
    """Mock buffer memory for testing"""
    def __init__(self):
        self._data = {}
    
    async def set(self, key: str, value: Dict, **kwargs):
        self._data[key] = value
    
    async def get(self, key: str) -> Optional[Dict]:
        return self._data.get(key)
    
    async def delete(self, key: str):
        if key in self._data:
            del self._data[key]


class MockLLM:
    """Mock LLM for testing"""
    def __init__(self):
        self.responses = []
        self.call_count = 0
    
    async def chat(self, messages, temperature=0, max_tokens=200):
        self.call_count += 1
        response = Mock()
        
        # Determine response based on prompt content
        prompt = messages[0]["content"] if messages else ""
        
        if "Analyze this request to determine if clarification is needed" in prompt:
            # Initial clarification check
            response.content = '''{
                "needs_clarification": false,
                "reason": "clear",
                "mode": "direct",
                "question": null,
                "confidence": 0.9
            }'''
        elif "Determine if we need more clarification" in prompt:
            # Check if need more clarification
            response.content = '''{
                "needs_more": false,
                "question": null
            }'''
        elif "context switch" in prompt.lower():
            # Context switch detection
            response.content = "answering"
        elif "stop clarification" in prompt:
            # Stop intent detection
            response.content = "false"
        elif "Generate a question for selecting a credential" in prompt:
            # Credential question generation
            response.content = "Which GitHub account would you like to use?"
        else:
            response.content = "Default response"
        
        return response


class MockOverlord:
    """Mock overlord for testing"""
    def __init__(self):
        self.buffer_memory = MockBufferMemory()
        self.default_llm_model = MockLLM()
        
        # Mock clarification config object (new structure)
        self.clarification_config = Mock()
        self.clarification_config.max_questions = 3  # Old format for backward compatibility
        self.clarification_config.max_rounds = None  # New format not set by default
        self.clarification_config.timeout_seconds = 300
        self.clarification_config.style = Mock()
        self.clarification_config.style.value = 'conversational'
        
        self.formation = Mock()
        self.formation.mcp_servers = {"github": {}, "gitlab": {}}
        self.formation.agents = []


@pytest.fixture
def mock_overlord():
    """Create a mock overlord instance"""
    return MockOverlord()


@pytest.fixture
def unified_system(mock_overlord):
    """Create a UnifiedClarificationSystem instance"""
    return UnifiedClarificationSystem(mock_overlord)


@pytest.mark.asyncio
async def test_initialization(unified_system):
    """Test system initializes correctly"""
    assert unified_system is not None
    assert unified_system.max_questions == 3  # From mock config
    assert unified_system.max_rounds is None  # Not set in mock config
    assert unified_system.timeout == 300
    assert unified_system.style == 'conversational'
    assert unified_system.namespace == "clarification"


@pytest.mark.asyncio
async def test_no_clarification_needed(unified_system):
    """Test when clarification is not needed"""
    result = await unified_system.needs_clarification(
        message="List files in the current directory",
        request_id="test-123",
        session_id="session-456",
        context={"user_id": "user-789"}
    )
    
    assert result.action == "execute"
    assert result.request == "List files in the current directory"
    assert result.mode == "direct"


@pytest.mark.asyncio
async def test_clarification_needed(unified_system):
    """Test when clarification is needed"""
    # Mock LLM to return needs_clarification = true
    unified_system.llm.chat = AsyncMock(return_value=Mock(content='''{
        "needs_clarification": true,
        "reason": "ambiguous",
        "mode": "direct",
        "question": "What type of files are you looking for?",
        "confidence": 0.7
    }'''))
    
    result = await unified_system.needs_clarification(
        message="Find something",
        request_id="test-124",
        session_id="session-457"
    )
    
    assert result.action == "clarify"
    assert result.question == "What type of files are you looking for?"
    assert result.mode == "direct"
    
    # Check state was stored
    state = await unified_system.get_state("test-124")
    assert state is not None
    assert state["original_request"] == "Find something"
    assert state["depth"] == 0
    assert state["mode"] == "direct"


@pytest.mark.asyncio
async def test_handle_response_continue_clarification(unified_system):
    """Test handling a response that needs more clarification"""
    # First set up an active clarification
    await unified_system._create_state(
        request_id="test-125",
        message="Help me with something",
        mode="direct",
        session_id="session-458"
    )
    
    # Mock LLM to need more clarification
    unified_system.llm.chat = AsyncMock(side_effect=[
        Mock(content="answering"),  # Context switch check
        Mock(content="false"),  # Stop intent check
        Mock(content='{"needs_more": true, "question": "Can you be more specific?"}')  # Need more check
    ])
    
    result = await unified_system.handle_response("test-125", "I need help")
    
    assert result.action == "clarify"
    assert result.question == "Can you be more specific?"
    
    # Check state was updated
    state = await unified_system.get_state("test-125")
    assert state["depth"] == 1
    assert "I need help" in state["collected_info"]


@pytest.mark.asyncio
async def test_handle_response_complete_clarification(unified_system):
    """Test handling a response that completes clarification"""
    # Set up an active clarification
    await unified_system._create_state(
        request_id="test-126",
        message="Help me with Python",
        mode="direct",
        session_id="session-459"
    )
    
    # Mock LLM to complete clarification
    unified_system.llm.chat = AsyncMock(side_effect=[
        Mock(content="answering"),  # Context switch check
        Mock(content="false"),  # Stop intent check
        Mock(content='{"needs_more": false, "question": null}')  # Complete
    ])
    
    result = await unified_system.handle_response("test-126", "I need to parse JSON")
    
    assert result.action == "execute"
    assert "Help me with Python" in result.request
    assert "parse JSON" in result.request
    
    # Check state was cleaned up
    state = await unified_system.get_state("test-126")
    assert state is None


@pytest.mark.asyncio
async def test_max_depth_circuit_breaker(unified_system):
    """Test that max depth prevents infinite loops"""
    # Set up clarification at max depth - 1
    state = {
        "depth": 2,  # Max is 3, so next will hit limit
        "original_request": "Complex request",
        "collected_info": ["info1", "info2"],
        "max_depth": 3,
        "mode": "direct",
        "context": {},
        "started_at": time.time(),
        "request_id": "test-127",
        "session_id": "session-460"
    }
    await unified_system._store_state("test-127", state)
    
    result = await unified_system.handle_response("test-127", "more info")
    
    assert result.action == "execute"
    assert "Complex request" in result.request
    
    # Check state was cleaned up
    state = await unified_system.get_state("test-127")
    assert state is None


@pytest.mark.asyncio
async def test_timeout_handling(unified_system):
    """Test timeout prevents stuck clarifications"""
    # Set up clarification with old timestamp
    state = {
        "depth": 1,
        "original_request": "Old request",
        "collected_info": [],
        "max_depth": 3,
        "mode": "direct",
        "context": {},
        "started_at": time.time() - 400,  # Started 400 seconds ago, timeout is 300
        "request_id": "test-128",
        "session_id": "session-461"
    }
    await unified_system._store_state("test-128", state)
    
    result = await unified_system.handle_response("test-128", "late response")
    
    assert result.action == "execute"
    assert result.context.get("timeout") is True
    
    # Check state was cleaned up
    state = await unified_system.get_state("test-128")
    assert state is None


@pytest.mark.asyncio
async def test_context_switch_detection(unified_system):
    """Test detecting when user switches context"""
    # Set up active clarification
    await unified_system._create_state(
        request_id="test-129",
        message="List my repositories",
        mode="direct",
        session_id="session-462"
    )
    
    # Mock LLM to detect context switch
    unified_system.llm.chat = AsyncMock(return_value=Mock(content="different"))
    
    result = await unified_system.handle_response("test-129", "tell me a joke")
    
    assert result.action == "execute"
    assert result.request == "tell me a joke"  # Process new request
    assert result.context.get("clarification_cancelled") is True
    assert result.context.get("reason") == "context_switch"
    
    # Check state was cleaned up
    state = await unified_system.get_state("test-129")
    assert state is None


@pytest.mark.asyncio
async def test_stop_intent_detection(unified_system):
    """Test detecting when user wants to stop clarification"""
    # Set up active clarification
    await unified_system._create_state(
        request_id="test-130",
        message="Help with something",
        mode="direct",
        session_id="session-463"
    )
    
    # Mock LLM to detect stop intent
    unified_system.llm.chat = AsyncMock(side_effect=[
        Mock(content="answering"),  # No context switch
        Mock(content="true")  # Stop intent detected
    ])
    
    result = await unified_system.handle_response("test-130", "never mind, just do it")
    
    assert result.action == "execute"
    assert "Help with something" in result.request
    assert result.context.get("user_stopped") is True
    
    # Check state was cleaned up
    state = await unified_system.get_state("test-130")
    assert state is None


@pytest.mark.asyncio
async def test_credential_clarification(unified_system):
    """Test handling credential selection"""
    # Mock credential error
    mock_error = Mock()
    mock_error.service = "github"
    mock_error.available_credentials = [
        {"name": "personal-account"},
        {"name": "work-account"}
    ]
    mock_error.original_request = "List my repos"
    
    result = await unified_system.handle_credential_error(
        error=mock_error,
        request_id="test-131"
    )
    
    assert result.action == "clarify"
    assert "GitHub" in result.question or "github" in result.question.lower()
    assert result.mode == "credential"
    
    # Check state was stored
    state = await unified_system.get_state("test-131")
    assert state is not None
    assert state["mode"] == "credential"
    assert state["max_depth"] == 1  # Credential only gets one round


@pytest.mark.asyncio
async def test_mode_detection(unified_system):
    """Test different mode detection"""
    # Test brainstorm mode
    unified_system.llm.chat = AsyncMock(return_value=Mock(content='''{
        "needs_clarification": true,
        "reason": "ambiguous",
        "mode": "brainstorm",
        "question": "What kind of app are you thinking about?",
        "confidence": 0.8
    }'''))
    
    result = await unified_system.needs_clarification(
        message="Help me design an app",
        request_id="test-132",
        session_id="session-464"
    )
    
    assert result.mode == "brainstorm"
    
    # Check max depth for brainstorm mode
    state = await unified_system.get_state("test-132")
    assert state["max_depth"] == 10  # Brainstorm gets more rounds


@pytest.mark.asyncio
async def test_planning_mode(unified_system):
    """Test planning mode detection and handling"""
    unified_system.llm.chat = AsyncMock(return_value=Mock(content='''{
        "needs_clarification": true,
        "reason": "planning_needed",
        "mode": "planning",
        "question": "What are the main requirements?",
        "confidence": 0.9
    }'''))
    
    result = await unified_system.needs_clarification(
        message="Help me plan a project",
        request_id="test-133",
        session_id="session-465"
    )
    
    assert result.mode == "planning"
    
    state = await unified_system.get_state("test-133")
    assert state["max_depth"] == 7  # Planning gets 7 rounds


@pytest.mark.asyncio
async def test_enhanced_request_building(unified_system):
    """Test building enhanced requests from collected info"""
    # Direct mode
    state = {
        "mode": "direct",
        "original_request": "Find files",
        "collected_info": ["in the src directory", "with .py extension"]
    }
    enhanced = unified_system._build_enhanced_request(state)
    assert "Find files" in enhanced
    assert "src directory" in enhanced
    assert ".py extension" in enhanced
    
    # Brainstorm mode
    state = {
        "mode": "brainstorm",
        "original_request": "Design an app",
        "collected_info": ["for task management", "with collaboration features"]
    }
    enhanced = unified_system._build_enhanced_request(state)
    assert "Goal: Design an app" in enhanced
    assert "Discussion:" in enhanced
    assert "task management" in enhanced
    
    # Credential mode
    state = {
        "mode": "credential",
        "original_request": "List repos",
        "collected_info": ["work-account"]
    }
    enhanced = unified_system._build_enhanced_request(state)
    assert enhanced == "work-account"  # Returns selection directly


@pytest.mark.asyncio
async def test_concurrent_requests(unified_system):
    """Test handling multiple concurrent clarification sessions"""
    # Start multiple clarifications
    tasks = []
    for i in range(5):
        task = unified_system._create_state(
            request_id=f"concurrent-{i}",
            message=f"Request {i}",
            mode="direct",
            session_id=f"session-{i}"
        )
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    
    # Verify all states were created
    for i in range(5):
        state = await unified_system.get_state(f"concurrent-{i}")
        assert state is not None
        assert state["original_request"] == f"Request {i}"
    
    # Clean up one
    await unified_system.cancel_clarification("concurrent-2")
    state = await unified_system.get_state("concurrent-2")
    assert state is None
    
    # Others should still exist
    state = await unified_system.get_state("concurrent-1")
    assert state is not None


@pytest.mark.asyncio
async def test_request_id_vs_session_id(unified_system):
    """Test that request_id is used for state, session_id only for stats"""
    result = await unified_system.needs_clarification(
        message="Test message",
        request_id="req-001",
        session_id="sess-001",
        context={"user_id": "user-001"}
    )
    
    # State should be keyed by request_id
    state = await unified_system.get_state("req-001")
    if state:  # Only if clarification was needed
        assert state["request_id"] == "req-001"
        assert state["session_id"] == "sess-001"
        
        # Verify storage key uses request_id
        key = f"clarification:req-001"
        stored = await unified_system.buffer_memory.get(key)
        assert stored is not None


@pytest.mark.asyncio
async def test_style_configuration(unified_system):
    """Test that style configuration is used in question generation"""
    # Test conversational style (default)
    assert unified_system.style == "conversational"
    
    # Create system with technical style
    mock_overlord = MockOverlord()
    mock_overlord.config['clarification']['style'] = 'technical'
    tech_system = UnifiedClarificationSystem(mock_overlord)
    assert tech_system.style == 'technical'
    
    # Create system with brief style
    mock_overlord.config['clarification']['style'] = 'brief'
    brief_system = UnifiedClarificationSystem(mock_overlord)
    assert brief_system.style == 'brief'


@pytest.mark.asyncio
async def test_execution_mode(unified_system):
    """Test execution mode for clarifying execution details"""
    unified_system.llm.chat = AsyncMock(return_value=Mock(content='''{
        "needs_clarification": true,
        "reason": "execution_details",
        "mode": "execution",
        "question": "Should I include hidden files?",
        "confidence": 0.8
    }'''))
    
    result = await unified_system.needs_clarification(
        message="List all files",
        request_id="test-134",
        session_id="session-466"
    )
    
    assert result.mode == "execution"
    
    state = await unified_system.get_state("test-134")
    assert state["max_depth"] == 2  # Execution gets 2 rounds


@pytest.mark.asyncio
async def test_cleanup_on_completion(unified_system):
    """Test explicit cleanup when clarification completes"""
    # Create a clarification
    await unified_system._create_state(
        request_id="test-cleanup",
        message="Test request",
        mode="direct"
    )
    
    # Verify it exists
    state = await unified_system.get_state("test-cleanup")
    assert state is not None
    assert "test-cleanup" in unified_system.active_requests
    
    # Clean it up
    await unified_system._cleanup_state("test-cleanup")
    
    # Verify it's gone
    state = await unified_system.get_state("test-cleanup")
    assert state is None
    assert "test-cleanup" not in unified_system.active_requests


@pytest.mark.asyncio
async def test_no_pattern_matching(unified_system):
    """Verify system uses LLM for all decisions, no pattern matching"""
    # Check that the system doesn't have any regex patterns
    import inspect
    source = inspect.getsource(UnifiedClarificationSystem)
    
    # These would indicate pattern matching
    assert "re.match" not in source
    assert "re.search" not in source
    assert "regex" not in source.lower()
    
    # Verify LLM is called for decisions
    call_count_before = unified_system.llm.call_count
    
    await unified_system.needs_clarification(
        message="Test",
        request_id="test-no-pattern",
        session_id="test-session"
    )
    
    # LLM should have been called
    assert unified_system.llm.call_count > call_count_before


@pytest.mark.asyncio
async def test_max_rounds_configuration():
    """Test new max_rounds configuration structure"""
    # Mock overlord with max_rounds configuration
    overlord = Mock()
    overlord.buffer_memory = MockBufferMemory()
    overlord.default_llm_model = MockLLM()
    
    # Mock clarification config with max_rounds
    config = Mock()
    config.max_questions = 5  # Backward compatibility
    config.max_rounds = {
        "direct": 2,
        "brainstorm": 15,
        "planning": 5,
        "execution": 1,
        "other": 4
    }
    config.timeout_seconds = 300
    config.style = Mock()
    config.style.value = "conversational"
    
    overlord.clarification_config = config
    
    # Create system
    system = UnifiedClarificationSystem(overlord)
    
    # Test mode-specific limits
    assert system._get_max_depth("direct") == 2
    assert system._get_max_depth("brainstorm") == 15
    assert system._get_max_depth("planning") == 5
    assert system._get_max_depth("execution") == 1
    assert system._get_max_depth("unknown_mode") == 4  # Uses "other"


@pytest.mark.asyncio
async def test_backward_compatibility_max_questions():
    """Test backward compatibility with old max_questions format"""
    # Mock overlord with old max_questions configuration
    overlord = Mock()
    overlord.buffer_memory = MockBufferMemory()
    overlord.default_llm_model = MockLLM()
    
    # Mock clarification config with only max_questions (old format)
    config = Mock()
    config.max_questions = 7  # Old configuration
    config.max_rounds = None  # New configuration not set
    config.timeout_seconds = 300
    config.style = Mock()
    config.style.value = "formal"
    
    overlord.clarification_config = config
    
    # Create system
    system = UnifiedClarificationSystem(overlord)
    
    # All modes should use max_questions as fallback
    assert system._get_max_depth("direct") == 7
    assert system._get_max_depth("brainstorm") == 7
    assert system._get_max_depth("planning") == 7
    assert system._get_max_depth("execution") == 7
    assert system._get_max_depth("credential") == 7  # Even credential uses fallback


@pytest.mark.asyncio
async def test_configuration_hierarchy_priority():
    """Test the 4-level configuration hierarchy priority"""
    overlord = Mock()
    overlord.buffer_memory = MockBufferMemory()
    overlord.default_llm_model = MockLLM()
    
    # Test 1: max_rounds takes priority over max_questions
    config = Mock()
    config.max_questions = 10  # Should be ignored
    config.max_rounds = {"direct": 3, "other": 5}
    config.timeout_seconds = 300
    config.style = Mock()
    config.style.value = "brief"
    
    overlord.clarification_config = config
    system = UnifiedClarificationSystem(overlord)
    
    assert system._get_max_depth("direct") == 3  # Uses max_rounds.direct
    assert system._get_max_depth("brainstorm") == 5  # Uses max_rounds.other
    
    # Test 2: max_questions used when max_rounds missing
    config.max_rounds = None
    system = UnifiedClarificationSystem(overlord)
    
    assert system._get_max_depth("direct") == 10  # Uses max_questions
    assert system._get_max_depth("brainstorm") == 10  # Uses max_questions


@pytest.mark.asyncio
async def test_sensible_defaults_fallback():
    """Test sensible defaults when no configuration available"""
    # Mock overlord with no clarification config
    overlord = Mock()
    overlord.buffer_memory = MockBufferMemory()
    overlord.default_llm_model = MockLLM()
    overlord.clarification_config = None  # No configuration
    
    # Create system
    system = UnifiedClarificationSystem(overlord)
    
    # Should use sensible defaults
    assert system._get_max_depth("direct") == 3
    assert system._get_max_depth("brainstorm") == 10
    assert system._get_max_depth("planning") == 7
    assert system._get_max_depth("execution") == 3
    assert system._get_max_depth("credential") == 2  # Updated from 1 to 2
    assert system._get_max_depth("unknown_mode") == 3  # Uses defaults["other"]


@pytest.mark.asyncio
async def test_credential_mode_updated_to_2_rounds():
    """Test that credential mode now uses 2 rounds instead of 1"""
    overlord = Mock()
    overlord.buffer_memory = MockBufferMemory()
    overlord.default_llm_model = MockLLM()
    overlord.clarification_config = None  # Use defaults
    
    system = UnifiedClarificationSystem(overlord)
    
    # Credential mode should now use 2 rounds instead of 1
    assert system._get_max_depth("credential") == 2
    
    # Test with configuration that doesn't specify credential mode
    config = Mock()
    config.max_questions = 5
    config.max_rounds = {"direct": 3}  # Doesn't specify credential
    config.timeout_seconds = 300
    config.style = Mock()
    config.style.value = "conversational"
    
    overlord.clarification_config = config
    system = UnifiedClarificationSystem(overlord)
    
    # Should still use default of 2 for credential mode
    assert system._get_max_depth("credential") == 5  # Uses max_questions fallback
    
    # But if we remove max_questions, should use sensible default
    config.max_questions = None
    system = UnifiedClarificationSystem(overlord)
    assert system._get_max_depth("credential") == 2  # Uses sensible default


@pytest.mark.asyncio
async def test_partial_max_rounds_configuration():
    """Test configuration with only some modes specified in max_rounds"""
    overlord = Mock()
    overlord.buffer_memory = MockBufferMemory()
    overlord.default_llm_model = MockLLM()
    
    # Config with partial max_rounds and max_questions fallback
    config = Mock()
    config.max_questions = 6  # Fallback for unspecified modes
    config.max_rounds = {
        "direct": 2,
        "planning": 8
        # brainstorm, execution, credential not specified
    }
    config.timeout_seconds = 300
    config.style = Mock()
    config.style.value = "conversational"
    
    overlord.clarification_config = config
    system = UnifiedClarificationSystem(overlord)
    
    # Specified modes use max_rounds
    assert system._get_max_depth("direct") == 2
    assert system._get_max_depth("planning") == 8
    
    # Unspecified modes fall back to max_questions
    assert system._get_max_depth("brainstorm") == 6
    assert system._get_max_depth("execution") == 6
    assert system._get_max_depth("credential") == 6


@pytest.mark.asyncio
async def test_max_rounds_limit_validation():
    """Test that max_rounds values are limited to prevent abuse"""
    from src.muxi.formation.initialization import initialize_clarification_config, MAX_CLARIFICATION_ROUNDS
    from src.muxi.formation.formation import Formation
    
    # Test valid configuration within limit
    formation = Formation()
    formation.config = {
        'clarification': {
            'max_rounds': {
                'direct': MAX_CLARIFICATION_ROUNDS,  # Should be allowed
                'brainstorm': 10
            }
        }
    }
    formation._setup_clarification_config()
    
    # Should not raise an error
    initialize_clarification_config(formation)
    assert formation._clarification_config_obj.max_rounds['direct'] == MAX_CLARIFICATION_ROUNDS
    
    # Test invalid configuration exceeding limit
    formation_invalid = Formation()
    formation_invalid.config = {
        'clarification': {
            'max_rounds': {
                'direct': MAX_CLARIFICATION_ROUNDS + 1,  # Should be rejected
                'brainstorm': 10
            }
        }
    }
    formation_invalid._setup_clarification_config()
    
    # Should raise ValueError
    with pytest.raises(ValueError, match=f"max_rounds.direct must be integer 1-{MAX_CLARIFICATION_ROUNDS}"):
        initialize_clarification_config(formation_invalid)
    
    # Test ridiculously high value
    formation_abuse = Formation()
    formation_abuse.config = {
        'clarification': {
            'max_rounds': {
                'brainstorm': 1000  # Should be rejected
            }
        }
    }
    formation_abuse._setup_clarification_config()
    
    with pytest.raises(ValueError, match=f"max_rounds.brainstorm must be integer 1-{MAX_CLARIFICATION_ROUNDS}"):
        initialize_clarification_config(formation_abuse)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])