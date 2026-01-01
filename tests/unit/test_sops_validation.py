"""
Unit tests for SOP endpoint validation and safety.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import Request
from fastapi.responses import JSONResponse

from muxi.runtime.formation.server.routes.client.sops import get_sop_details, _extract_agents_from_sop


def test_is_numbered_line_safe_with_empty_lines():
    """Test that step counting handles empty lines safely."""
    # Define the same helper function used in the endpoint
    def is_numbered_line(line: str) -> bool:
        stripped = line.strip()
        return len(stripped) > 0 and stripped[0].isdigit()

    # Test cases
    assert is_numbered_line("1. First step") is True
    assert is_numbered_line("  2. Second step  ") is True
    assert is_numbered_line("") is False
    assert is_numbered_line("   ") is False  # Whitespace only
    assert is_numbered_line("\t\n") is False  # Tabs and newlines
    assert is_numbered_line("Not a numbered line") is False
    assert is_numbered_line("- Bullet point") is False


def test_step_counting_with_mixed_content():
    """Test step counting with realistic SOP content."""
    def is_numbered_line(line: str) -> bool:
        stripped = line.strip()
        return len(stripped) > 0 and stripped[0].isdigit()

    content = """
# My SOP

This is an introduction.

1. First step
2. Second step

Some notes here.

3. Third step

"""

    steps = sum(1 for line in content.split("\n") if is_numbered_line(line))
    assert steps == 3


@pytest.mark.asyncio
async def test_sop_name_validation_prevents_path_traversal():
    """Test that sop_name parameter rejects path traversal attempts."""
    # Mock request and formation
    request = MagicMock(spec=Request)
    request.app.state.formation = MagicMock()
    request.state.request_id = "test_request"

    # Test invalid sop_names (path traversal attempts)
    invalid_names = [
        "../etc/passwd",
        "../../secret",
        "sop/../../../etc",
        "sop/with/slash",
        "sop.with.dots",
        "sop with spaces",
        "sop;with;semicolons",
        "sop'with'quotes",
        "sop\\with\\backslash",
    ]

    for invalid_name in invalid_names:
        response = await get_sop_details(request, invalid_name)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 400

        # Check response content
        content = response.body.decode()
        assert "Invalid SOP name" in content
        assert "letters, numbers, hyphens, and underscores" in content


@pytest.mark.asyncio
async def test_sop_name_validation_allows_valid_names():
    """Test that sop_name parameter accepts valid names."""
    # Mock request and formation with SOP system
    request = MagicMock(spec=Request)
    formation = MagicMock()
    overlord = MagicMock()
    sop_system = MagicMock()

    # Setup mock SOP
    sop_system.sops = {
        "valid-sop_name123": {
            "metadata": {"title": "Valid SOP"},
            "content": "1. Step one\n2. Step two"
        }
    }

    overlord.sop_system = sop_system
    formation._overlord = overlord
    request.app.state.formation = formation
    request.state.request_id = "test_request"

    # Test valid sop_names
    valid_names = [
        "my-sop",
        "my_sop",
        "MySOP",
        "sop123",
        "sop-with-dashes",
        "sop_with_underscores",
        "SOP-MixedCase_123",
    ]

    for valid_name in valid_names:
        # Add to mock SOPs
        sop_system.sops[valid_name] = {
            "metadata": {"title": f"SOP {valid_name}"},
            "content": "1. Step one"
        }

        response = await get_sop_details(request, valid_name)
        assert isinstance(response, JSONResponse)
        # Should not be 400 (validation error)
        assert response.status_code in [200, 404]  # 200 if found, 404 if not configured


def test_extract_agents_from_sop_handles_empty_content():
    """Test that agent extraction handles empty/malformed content."""
    # Empty content
    agents = _extract_agents_from_sop({}, "")
    assert agents == []

    # Whitespace only
    agents = _extract_agents_from_sop({}, "   \n\n  \t  ")
    assert agents == []

    # Content without agents
    agents = _extract_agents_from_sop({}, "This is some content without agents")
    assert agents == []


def test_extract_agents_from_metadata():
    """Test that agent extraction prefers metadata over content parsing."""
    metadata = {
        "agents": ["agent1", "agent2", "agent3"]
    }
    content = "agent: agent4\nagent: agent5"  # These should be ignored

    agents = _extract_agents_from_sop(metadata, content)
    assert agents == ["agent1", "agent2", "agent3"]


def test_extract_agents_from_content_fallback():
    """Test that agent extraction falls back to content parsing when no metadata."""
    content = """
# SOP
agent: researcher
agent: writer

Some text here.
  agent: reviewer
"""

    agents = _extract_agents_from_sop({}, content)
    assert "researcher" in agents
    assert "writer" in agents
    assert "reviewer" in agents
