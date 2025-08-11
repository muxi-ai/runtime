"""
Utility functions for Area 8 clarification tests.

Provides common functionality for test isolation and setup.
"""

import uuid


def generate_test_user_id(prefix: str = "test_user") -> str:
    """
    Generate a unique user ID for test isolation.

    This ensures each test run has a completely fresh context
    with no buffer memory contamination from previous runs.

    Args:
        prefix: Optional prefix for the user ID

    Returns:
        Unique user ID like "test_user_a1b2c3d4"
    """
    unique_suffix = str(uuid.uuid4())[:8]
    return f"{prefix}_{unique_suffix}"


def generate_test_session_id(prefix: str = "test_session") -> str:
    """
    Generate a unique session ID for test isolation.

    Args:
        prefix: Optional prefix for the session ID

    Returns:
        Unique session ID like "test_session_e5f6g7h8"
    """
    unique_suffix = str(uuid.uuid4())[:8]
    return f"{prefix}_{unique_suffix}"


class TestContext:
    """
    Helper class to manage test context with unique IDs.

    Usage:
        ctx = TestContext("test_8a1")
        response = await overlord.chat(
            message="Build it",
            user_id=ctx.user_id,
            session_id=ctx.session_id
        )
    """

    def __init__(self, test_name: str):
        """
        Initialize a test context with unique IDs.

        Args:
            test_name: Name of the test for ID prefixing
        """
        self.test_name = test_name
        self.user_id = generate_test_user_id(f"{test_name}_user")
        self.session_id = generate_test_session_id(f"{test_name}_session")

    def new_session(self) -> str:
        """Generate a new session ID while keeping the same user."""
        self.session_id = generate_test_session_id(f"{self.test_name}_session")
        return self.session_id

    def new_user(self) -> tuple[str, str]:
        """Generate new user and session IDs."""
        self.user_id = generate_test_user_id(f"{self.test_name}_user")
        self.session_id = generate_test_session_id(f"{self.test_name}_session")
        return self.user_id, self.session_id
