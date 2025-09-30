#!/usr/bin/env python3
"""Base test class for Area 2 Memory tests with standardized patterns."""

import sys
import asyncio
from pathlib import Path
from typing import Tuple, List

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402

# Import from common module
from common import BaseE2ETest  # noqa: E402
from common import TestOutputFormatter  # noqa: E402


class BaseMemoryTest(BaseE2ETest):
    """Base class for memory system tests with Pattern 2 support."""

    # Shared formation directory for all memory tests
    FORMATION_DIR = Path(__file__).parent / "formations" / "formation-memory"

    # Memory configuration mapping
    MEMORY_CONFIGS = {
        "buffer_local": "formation-buffer-local.yaml",
        "buffer_remote": "formation-buffer-remote.yaml",
        "sqlite": "formation-sqlite.yaml",
        "postgres": "formation-postgres.yaml",
        "postgres_faissx": "formation-postgres-and-faissx.yaml",
        "postgres_faissx_auth": "formation-postgres-and-faissx-with-auth.yaml",
        "auto_extract": "formation-auto-extract.yaml",
        "memory_limits": "formation-memory-limits.yaml",
        "basic": "formation-basic.yaml",
    }

    def __init__(self):
        """Initialize base memory test."""
        super().__init__(
            test_name="memory_test",
            test_description="Memory system test",
            test_area="2_memory"
        )
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None

    async def setup_memory_formation(self, memory_type: str = "basic") -> Formation:
        """Setup formation with specific memory configuration.

        Args:
            memory_type: One of the MEMORY_CONFIGS keys

        Returns:
            Configured Formation instance
        """
        if memory_type not in self.MEMORY_CONFIGS:
            raise ValueError(
                f"Unknown memory type: {memory_type}. Use one of {list(self.MEMORY_CONFIGS.keys())}"
            )

        yaml_file = self.MEMORY_CONFIGS[memory_type]
        formation_path = self.FORMATION_DIR / yaml_file

        self.formation = Formation()
        await self.formation.load(str(formation_path))

        # Store overlord reference
        self.overlord = await self.formation.start_overlord()

        return self.formation

    async def test_memory_retention(self, user_id: str = "test_user") -> Tuple[bool, str]:
        """Test basic memory retention across messages.

        Args:
            user_id: User ID for memory isolation

        Returns:
            Tuple of (success, details)
        """
        try:
            # First message with information to remember
            await self.overlord.chat(
                "My name is Alice and I work at TechCorp.",
                user_id=user_id,
                use_async=False,
                stream=False,
            )

            # Wait for memory storage
            await asyncio.sleep(3)

            # Query for retained information
            response = await self.overlord.chat(
                "What did I just tell you about myself?",
                user_id=user_id,
                use_async=False,
                stream=False,
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
            else:
                response_text = response.content if hasattr(response, "content") else str(response)

            # Check retention
            retained = "alice" in response_text.lower() or "techcorp" in response_text.lower()

            return retained, response_text[:200]

        except Exception as e:
            return False, f"Error: {str(e)}"

    async def test_multi_user_isolation(self) -> Tuple[bool, str]:
        """Test memory isolation between different users.

        Returns:
            Tuple of (success, details)
        """
        try:
            # User 1 stores information
            await self.overlord.chat(
                "I am Bob and I like pizza.", user_id="user1", use_async=False, stream=False
            )

            # User 2 stores different information
            await self.overlord.chat(
                "I am Carol and I like sushi.", user_id="user2", use_async=False, stream=False
            )

            await asyncio.sleep(3)

            # User 1 queries their info
            response1 = await self.overlord.chat(
                "What is my name and what do I like?",
                user_id="user1",
                use_async=False,
                stream=False,
            )

            # User 2 queries their info
            response2 = await self.overlord.chat(
                "What is my name and what do I like?",
                user_id="user2",
                use_async=False,
                stream=False,
            )

            # Extract text
            if hasattr(response1, "__aiter__"):
                text1 = ""
                async for chunk in response1:
                    text1 += chunk
            else:
                text1 = response1.content if hasattr(response1, "content") else str(response1)

            if hasattr(response2, "__aiter__"):
                text2 = ""
                async for chunk in response2:
                    text2 += chunk
            else:
                text2 = response2.content if hasattr(response2, "content") else str(response2)

            # Check isolation
            user1_correct = "bob" in text1.lower() and "pizza" in text1.lower()
            user2_correct = "carol" in text2.lower() and "sushi" in text2.lower()
            no_cross_contamination = (
                "carol" not in text1.lower()
                and "sushi" not in text1.lower()
                and "bob" not in text2.lower()
                and "pizza" not in text2.lower()
            )

            success = user1_correct and user2_correct and no_cross_contamination
            details = f"User1 correct: {user1_correct}, User2 correct: {user2_correct}, No contamination: {no_cross_contamination}"  # noqa: E501

            return success, details

        except Exception as e:
            return False, f"Error: {str(e)}"

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None

    def print_test_header(self, test_name: str, description: str):
        """Print standardized test header."""
        self.formatter.print_test_header(test_name, description)

    def print_test_result(
        self,
        test_name: str,
        success: bool,
        checks: List[str],
        transcript: List[Tuple[str, str]],
        duration: float,
    ):
        """Print standardized test result."""
        self.formatter.print_test_result(test_name, success, checks, transcript, duration)
