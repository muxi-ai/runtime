"""
Pytest configuration and fixtures for MUXI Runtime tests.

This module provides common fixtures used across all test files.
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil
from typing import AsyncGenerator, Generator
import os
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from muxi.runtime.formation import Formation
from muxi.runtime.services.secrets import SecretsManager


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_formations_dir() -> Path:
    """Return the path to test formations directory."""
    return Path(__file__).parent.parent / "test-formations"


@pytest.fixture
async def temp_formation_dir() -> AsyncGenerator[Path, None]:
    """Create a temporary formation directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="muxi_test_formation_")
    temp_path = Path(temp_dir)
    
    # Create standard formation subdirectories
    (temp_path / "agents").mkdir()
    (temp_path / "mcp").mkdir()
    (temp_path / "a2a").mkdir()
    (temp_path / "knowledge").mkdir()
    
    yield temp_path
    
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
async def formation_with_secrets(temp_formation_dir: Path) -> AsyncGenerator[Path, None]:
    """Create a formation directory with initialized secrets."""
    # Initialize secrets
    secrets_manager = SecretsManager(temp_formation_dir)
    await secrets_manager.initialize_encryption()
    
    # Add test secrets
    await secrets_manager.store_secret("TEST_API_KEY", "test-key-value")
    await secrets_manager.store_secret("TEST_SECRET", "test-secret-value")
    
    yield temp_formation_dir


@pytest.fixture
def basic_formation_yaml(temp_formation_dir: Path) -> Path:
    """Create a basic formation.yaml file for testing."""
    formation_yaml = temp_formation_dir / "formation.yaml"
    formation_yaml.write_text("""
version: "1.0"
name: "test-formation"
description: "Basic test formation"

agents:
  - id: "assistant"
    name: "Test Assistant"
    model: "gpt-4"
    role: "general"
    provider: "openai"
    
memory:
  buffer:
    enabled: true
    max_messages: 50
    
observability:
  level: "info"
  output: "stdout"
""")
    return formation_yaml


@pytest.fixture
def multi_agent_formation_yaml(temp_formation_dir: Path) -> Path:
    """Create a multi-agent formation.yaml file for testing."""
    formation_yaml = temp_formation_dir / "formation.yaml"
    formation_yaml.write_text("""
version: "1.0"
name: "multi-agent-test"
description: "Multi-agent test formation"

agents:
  - id: "researcher"
    name: "Research Agent"
    model: "gpt-4"
    role: "research"
    provider: "openai"
    specialties:
      - "data analysis"
      - "web research"
      
  - id: "writer"
    name: "Writing Agent"
    model: "claude-3-opus-20240229"
    role: "writing"
    provider: "anthropic"
    specialties:
      - "technical writing"
      - "documentation"
      
memory:
  buffer:
    enabled: true
    max_messages: 100
    
a2a:
  enabled: true
  internal_communication: true
""")
    return formation_yaml


@pytest.fixture
def file_generation_formation_yaml(temp_formation_dir: Path) -> Path:
    """Create a formation.yaml with file generation MCP enabled."""
    formation_yaml = temp_formation_dir / "formation.yaml"
    formation_yaml.write_text("""
version: "1.0"
name: "file-generation-test"
description: "Test formation with file generation MCP"

agents:
  - id: "generator"
    name: "File Generator"
    model: "gpt-4"
    role: "general"
    provider: "openai"
    
mcp_servers:
  - id: "file_generation"
    type: "builtin"
    builtin_name: "file_generation"
    config:
      allowed_directories:
        - "./output"
      max_file_size: 10485760  # 10MB
      
memory:
  buffer:
    enabled: true
    max_messages: 50
""")
    return formation_yaml


@pytest.fixture
async def mock_formation(basic_formation_yaml: Path) -> AsyncGenerator[Formation, None]:
    """Create a mock Formation instance for testing."""
    formation = Formation(basic_formation_yaml.parent)
    await formation.initialize()
    yield formation
    # Cleanup if needed
    pass


@pytest.fixture
def mock_openai_api_key(monkeypatch):
    """Mock OpenAI API key for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-123")


@pytest.fixture
def mock_anthropic_api_key(monkeypatch):
    """Mock Anthropic API key for testing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-123")


@pytest.fixture
def suppress_observability(monkeypatch):
    """Suppress observability logs during tests."""
    monkeypatch.setenv("LOGURU_LEVEL", "ERROR")
    monkeypatch.setenv("MUXI_OBSERVABILITY_SILENT", "true")


# Async test marker
def pytest_collection_modifyitems(config, items):
    """Add asyncio marker to all async tests."""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)