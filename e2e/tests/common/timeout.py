"""
Dynamic timeout management for E2E tests.
"""

from typing import Dict, List


class TestTimeouts:
    """Centralized timeout management based on test patterns."""

    # Known test duration patterns (in seconds)
    TIMEOUT_MAP: Dict[str, int] = {
        # Quick tests (10-30s)
        "greeting": 10,
        "simple_chat": 15,
        "memory_recall": 20,
        "clarification": 30,
        # Medium tests (30-60s)
        "mcp_tool_use": 45,
        "file_generation": 60,
        "knowledge_query": 45,
        "scheduling": 40,
        "agent_selection": 35,
        "sop_execution": 50,
        # Long tests (60-180s)
        "workflow_decomposition": 120,
        "multi_agent": 90,
        "large_document": 180,
        "video_processing": 300,
        "a2a_communication": 90,
        "complex_orchestration": 150,
        # Very long tests (3-5 minutes)
        "complex_workflow": 300,
        "recursive_clarification": 180,
        "batch_processing": 240,
        "full_pipeline": 300,
    }

    @classmethod
    def get_timeout(cls, test_type: str = None, message: str = None, files: List = None) -> int:
        """
        Get appropriate timeout based on test characteristics.

        Args:
            test_type: Specific test type if known
            message: Message content to analyze
            files: Files being processed (for size-based timeout)

        Returns:
            Timeout in seconds
        """
        # Check for known test types
        if test_type:
            # Try exact match
            if test_type in cls.TIMEOUT_MAP:
                return cls.TIMEOUT_MAP[test_type]

            # Try partial match
            for key in cls.TIMEOUT_MAP:
                if key in test_type.lower():
                    return cls.TIMEOUT_MAP[key]

        # Dynamic detection based on file size
        if files:
            total_size = sum(len(f.get("content", "")) for f in files)
            if total_size > 100_000_000:  # >100MB
                return 300
            elif total_size > 10_000_000:  # >10MB
                return 180
            elif total_size > 1_000_000:  # >1MB
                return 120

        # Check message complexity
        if message:
            msg_lower = message.lower()

            # Complex operations
            if any(
                keyword in msg_lower
                for keyword in ["analyze", "complex", "detailed", "comprehensive", "extensive"]
            ):
                return 120

            # Workflow operations
            elif any(
                keyword in msg_lower
                for keyword in ["workflow", "plan", "decompose", "steps", "orchestrate"]
            ):
                return 180

            # Multi-agent operations
            elif any(
                keyword in msg_lower for keyword in ["multi-agent", "collaborate", "coordinate"]
            ):
                return 90

            # File operations
            elif any(
                keyword in msg_lower
                for keyword in ["generate", "create", "write", "file", "document"]
            ):
                return 60

            # Simple queries
            elif any(
                keyword in msg_lower
                for keyword in ["hello", "hi", "simple", "basic", "what", "tell"]
            ):
                return 15

        # Default timeout
        return 60

    @classmethod
    def with_buffer(cls, base_timeout: int, buffer_percent: int = 20) -> int:
        """
        Add buffer to timeout for safety.

        Args:
            base_timeout: Base timeout in seconds
            buffer_percent: Percentage to add as buffer

        Returns:
            Timeout with buffer added
        """
        return int(base_timeout * (1 + buffer_percent / 100))

    @classmethod
    def for_environment(cls, base_timeout: int, env: str = "local") -> int:
        """
        Adjust timeout based on environment.

        Args:
            base_timeout: Base timeout in seconds
            env: Environment (local, ci, docker)

        Returns:
            Environment-adjusted timeout
        """
        multipliers = {
            "local": 1.0,
            "docker": 1.5,
            "ci": 2.0,  # CI runners can be slow
        }
        multiplier = multipliers.get(env, 1.0)
        return int(base_timeout * multiplier)

    @classmethod
    def get_test_timeout(
        cls, test_name: str, message: str = None, env: str = "local", with_buffer: bool = True
    ) -> int:
        """
        Get complete timeout for a test with all adjustments.

        Args:
            test_name: Name of the test
            message: Message being sent
            env: Environment the test is running in
            with_buffer: Whether to add safety buffer

        Returns:
            Final timeout in seconds
        """
        # Extract test type from test name
        # e.g., test_1a1_simple_chat -> simple_chat
        parts = test_name.split("_")
        test_type = "_".join(parts[2:]) if len(parts) > 2 else test_name

        # Get base timeout
        timeout = cls.get_timeout(test_type, message)

        # Adjust for environment
        timeout = cls.for_environment(timeout, env)

        # Add buffer if requested
        if with_buffer:
            timeout = cls.with_buffer(timeout)

        return timeout
