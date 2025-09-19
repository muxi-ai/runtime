"""Tests for PromptLoader utility."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from muxi.formation.prompts.loader import PromptLoader


class TestPromptLoader:
    """Test cases for PromptLoader."""

    def setup_method(self):
        """Reset PromptLoader state before each test."""
        PromptLoader._prompts.clear()
        PromptLoader._initialized = False

    def test_initialize_with_valid_prompts(self):
        """Test initialization with valid prompt files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test prompt files
            (temp_path / "test1.md").write_text("Test prompt 1", encoding='utf-8')
            (temp_path / "test2.md").write_text("Test prompt 2 with {variable}", encoding='utf-8')

            # Mock the prompts directory
            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                PromptLoader.initialize()

                assert PromptLoader._initialized is True
                assert len(PromptLoader._prompts) == 2
                assert "test1.md" in PromptLoader._prompts
                assert "test2.md" in PromptLoader._prompts
                assert PromptLoader._prompts["test1.md"] == "Test prompt 1"
                assert PromptLoader._prompts["test2.md"] == "Test prompt 2 with {variable}"

    def test_initialize_missing_directory(self):
        """Test initialization with missing prompts directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "nonexistent"

            with patch.object(PromptLoader, '_prompts_dir', missing_path):
                with pytest.raises(FileNotFoundError, match="Prompts directory not found"):
                    PromptLoader.initialize()

    def test_initialize_empty_directory(self):
        """Test initialization with empty prompts directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                with pytest.raises(FileNotFoundError, match="No prompt files found"):
                    PromptLoader.initialize()

    def test_initialize_only_once(self):
        """Test that initialize only runs once."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "test.md").write_text("Test prompt", encoding='utf-8')

            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                PromptLoader.initialize()
                first_prompts = PromptLoader._prompts.copy()

                # Add another file and initialize again
                (temp_path / "test2.md").write_text("Test prompt 2", encoding='utf-8')
                PromptLoader.initialize()

                # Should not reload
                assert PromptLoader._prompts == first_prompts

    def test_get_prompt_without_variables(self):
        """Test getting a prompt without variable substitution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "simple.md").write_text("Simple prompt", encoding='utf-8')

            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                PromptLoader.initialize()
                result = PromptLoader.get("simple.md")
                assert result == "Simple prompt"

    def test_get_prompt_with_variables(self):
        """Test getting a prompt with variable substitution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "variable.md").write_text("Hello {name}, your age is {age}", encoding='utf-8')

            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                PromptLoader.initialize()
                result = PromptLoader.get("variable.md", name="Alice", age=30)
                assert result == "Hello Alice, your age is 30"

    def test_get_prompt_not_initialized(self):
        """Test getting a prompt when not initialized."""
        with pytest.raises(RuntimeError, match="PromptLoader not initialized"):
            PromptLoader.get("test.md")

    def test_get_prompt_not_found(self):
        """Test getting a non-existent prompt."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "exists.md").write_text("Exists", encoding='utf-8')

            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                PromptLoader.initialize()

                with pytest.raises(KeyError, match="Prompt not found: missing.md"):
                    PromptLoader.get("missing.md")

    def test_get_prompt_missing_variable(self):
        """Test getting a prompt with missing variable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "variable.md").write_text("Hello {name} and {other}", encoding='utf-8')

            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                PromptLoader.initialize()

                with pytest.raises(KeyError):
                    PromptLoader.get("variable.md", name="Alice")  # Missing 'other' variable

    def test_get_prompt_error_message_shows_available(self):
        """Test that error messages show available prompts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "prompt1.md").write_text("Prompt 1", encoding='utf-8')
            (temp_path / "prompt2.md").write_text("Prompt 2", encoding='utf-8')

            with patch.object(PromptLoader, '_prompts_dir', temp_path):
                PromptLoader.initialize()

                try:
                    PromptLoader.get("missing.md")
                except KeyError as e:
                    error_msg = str(e)
                    assert "prompt1.md" in error_msg
                    assert "prompt2.md" in error_msg
