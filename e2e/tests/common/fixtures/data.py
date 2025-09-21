"""
Test data fixtures and generators.
"""

from typing import List, Dict, Any
import json
import uuid
from datetime import datetime
class TestDataGenerator:
    """Generate consistent test data for reproducible tests."""

    @staticmethod
    def create_test_documents(count: int = 10, prefix: str = "test") -> List[Dict]:
        """Generate consistent test documents for knowledge tests."""
        docs = []
        for i in range(count):
            docs.append(
                {
                    "id": f"{prefix}_doc_{i}",
                    "title": f"Test Document {i}",
                    "content": f"This is test content for document {i}. " * 10,
                    "metadata": {
                        "created_at": datetime.utcnow().isoformat(),
                        "tags": ["test", f"category_{i % 3}"],
                        "version": "1.0",
                    },
                }
            )
        return docs

    @staticmethod
    async def seed_memory_data(overlord, user_id: str, conversations: int = 5):
        """Pre-populate memory with test conversations for recall tests."""
        test_exchanges = [
            ("What's the capital of France?", "The capital of France is Paris."),
            ("Tell me about Python", "Python is a high-level programming language."),
            ("What's 2+2?", "2+2 equals 4."),
            ("Hello", "Hello! How can I help you today?"),
            ("Goodbye", "Goodbye! Have a great day!"),
        ]

        for i in range(min(conversations, len(test_exchanges))):
            user_msg, _ = test_exchanges[i]
            # Simulate conversation to populate memory
            await overlord.chat(user_msg, user_id=user_id)

    @staticmethod
    def create_test_files(file_types: List[str] = None) -> Dict[str, str]:
        """Create test files for multimodal and artifact tests."""
        if file_types is None:
            file_types = ["txt", "json", "md"]

        files = {}
        for file_type in file_types:
            if file_type == "txt":
                files["test.txt"] = "This is a test text file.\n" * 5
            elif file_type == "json":
                files["test.json"] = json.dumps({"test": True, "data": [1, 2, 3]}, indent=2)
            elif file_type == "md":
                files["test.md"] = "# Test Markdown\n\n- Item 1\n- Item 2\n"
            elif file_type == "py":
                files["test.py"] = "def hello():\n    return 'Hello, World!'\n"
            elif file_type == "yaml":
                files["test.yaml"] = "test: true\ndata:\n  - item1\n  - item2\n"

        return files

    @staticmethod
    def generate_unique_id(prefix: str = "test") -> str:
        """Generate unique ID for test isolation."""
        timestamp = int(datetime.now().timestamp())
        unique = uuid.uuid4().hex[:8]
        return f"{prefix}_{timestamp}_{unique}"

    @staticmethod
    def create_test_user(prefix: str = "test_user") -> Dict[str, str]:
        """Create test user data."""
        unique_id = TestDataGenerator.generate_unique_id(prefix)
        return {
            "user_id": unique_id,
            "session_id": f"session_{unique_id}",
            "name": f"Test User {unique_id}",
        }

    @staticmethod
    def create_schedule_data() -> List[Dict[str, Any]]:
        """Create test scheduling data."""
        return [
            {
                "schedule": "daily at 9am",
                "task": "Check emails",
                "expected": "scheduled successfully",
            },
            {
                "schedule": "every Monday at 2pm",
                "task": "Team meeting",
                "expected": "scheduled successfully",
            },
            {
                "schedule": "tomorrow at 3pm",
                "task": "Review documents",
                "expected": "scheduled successfully",
            },
        ]

    @staticmethod
    def create_mcp_test_data() -> Dict[str, Any]:
        """Create test data for MCP tests."""
        return {
            "filesystem": {
                "files": TestDataGenerator.create_test_files(),
                "directories": ["test_dir1", "test_dir2"],
            },
            "github": {
                "repo": "test-repo",
                "branch": "test-branch",
                "pr_title": "Test PR",
            },
            "linear": {
                "project": "Test Project",
                "issue": "Test Issue",
                "assignee": "test@example.com",
            },
        }
