# src/muxi/formation/prompts/loader.py
from pathlib import Path
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class PromptLoader:
    """Load and format prompts from markdown files.

    Simple singleton that loads all prompts at startup and caches them.
    Fails fast if the prompts directory is missing or empty.
    """

    _prompts: Dict[str, str] = {}
    _prompts_dir = Path(__file__).parent
    _initialized = False

    @classmethod
    def initialize(cls) -> None:
        """Load all prompt files from the prompts directory.

        Should be called during formation initialization.
        Fails fast if no prompts found.

        Raises:
            FileNotFoundError: If prompts directory doesn't exist or is empty
            RuntimeError: If initialization fails
        """
        if cls._initialized:
            return

        if not cls._prompts_dir.exists():
            raise FileNotFoundError(f"Prompts directory not found: {cls._prompts_dir}")

        # Load all .md files in the prompts directory
        prompt_files = list(cls._prompts_dir.glob("*.md"))

        if not prompt_files:
            raise FileNotFoundError(f"No prompt files found in {cls._prompts_dir}")

        logger.info(f"Loading {len(prompt_files)} prompt files...")

        for prompt_path in prompt_files:
            try:
                # Use Path.read_text() for cleaner code
                cls._prompts[prompt_path.name] = prompt_path.read_text(encoding='utf-8')
                logger.debug(f"Loaded prompt: {prompt_path.name}")
            except Exception as e:
                logger.error(f"Failed to load {prompt_path.name}: {e}")
                raise RuntimeError(f"Failed to load prompt {prompt_path.name}: {e}")

        cls._initialized = True
        logger.info(f"PromptLoader initialized with {len(cls._prompts)} prompts")

    @classmethod
    def get(cls, filename: str, **kwargs) -> str:
        """Get a prompt and format with variables.

        Args:
            filename: Name of the prompt file (e.g., 'agent_planning.md')
            **kwargs: Variables to substitute in the prompt

        Returns:
            Formatted prompt string

        Raises:
            RuntimeError: If PromptLoader not initialized
            KeyError: If prompt not found or variable missing
        """
        if not cls._initialized:
            raise RuntimeError("PromptLoader not initialized. Call initialize() first.")

        if filename not in cls._prompts:
            raise KeyError(f"Prompt not found: {filename}. Available: {list(cls._prompts.keys())}")

        prompt = cls._prompts[filename]

        # Handle variable substitution
        if kwargs:
            try:
                prompt = prompt.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing required variable in {filename}: {e}")
                raise

        return prompt
