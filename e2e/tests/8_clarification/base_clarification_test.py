#!/usr/bin/env python3
"""Base test class for Area 8 Clarification tests with standardized patterns."""

import sys
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import json
import uuid

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402

# Import from common module (centralized e2e/tests/common)
from common import BaseE2ETest  # noqa: E402
from common import TestOutputFormatter  # noqa: E402
from common import FormationManager  # noqa: E402


class BaseClarificationTest(BaseE2ETest):
    """Base class for Clarification tests."""

    # Shared formation directory for all clarification tests
    FORMATION_DIR = Path(__file__).parent / "formations" / "formation-clarification"

    # Clarification trigger patterns
    CLARIFICATION_INDICATORS = [
        "what",
        "which",
        "how",
        "clarify",
        "specific",
        "more information",
        "could you",
        "can you specify",
        "need more details",
        "ambiguous",
        "unclear",
        "help me understand",
        "what do you mean",
    ]

    # Ambiguous request categories for testing
    AMBIGUOUS_REQUESTS = {
        "vague_action": [
            "Build it",
            "Make this",
            "Create something",
            "Fix the issue",
            "Implement that",
        ],
        "incomplete_context": [
            "Add authentication",
            "Optimize performance",
            "Update the database",
            "Deploy to production",
            "Run the tests",
        ],
        "multiple_interpretations": [
            "Set up monitoring",
            "Create a report",
            "Integrate the API",
            "Configure the server",
            "Update dependencies",
        ],
        "missing_parameters": [
            "Send an email",
            "Generate a chart",
            "Create a user",
            "Schedule a meeting",
            "Backup the data",
        ],
    }

    # Response patterns that indicate clarification
    CLARIFICATION_PATTERNS = {
        "questions": ["what", "which", "how", "where", "when", "why"],
        "requests": ["could you", "can you", "please specify", "need to know"],
        "uncertainty": ["unclear", "ambiguous", "not sure", "need clarification"],
        "options": ["would you like", "do you want", "should I", "shall I"],
    }

    def __init__(self):
        """Initialize base clarification test."""
        super().__init__()
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None
        self.clarification_sessions = []

    async def setup_formation(self, formation_name: str = "formation-clarification") -> Formation:
        """Setup formation with clarification capabilities.

        Args:
            formation_name: Name of the formation directory (default: formation-clarification)

        Returns:
            Configured Formation instance
        """
        formation_path = self.FORMATION_DIR / "formation.yaml"

        self.formation = Formation()
        await self.formation.load(str(formation_path))

        # Store overlord reference
        self.overlord = await self.formation.start_overlord()

        return self.formation
    
    async def setup_clarification_formation(self) -> Formation:
        """Legacy method name - calls setup_formation for backward compatibility."""
        return await self.setup_formation()

    def create_unique_session(self, base_name: str = "test") -> Tuple[str, str]:
        """Create unique user_id and session_id for isolation.

        Args:
            base_name: Base name for the session

        Returns:
            Tuple of (user_id, session_id)
        """
        unique_id = str(uuid.uuid4())[:8]
        user_id = f"{base_name}_user_{unique_id}"
        session_id = f"{base_name}_session_{unique_id}"
        return user_id, session_id

    async def send_clarification_request(
        self,
        request: str,
        user_id: str = "test_user",
        session_id: str = "test_session",
        agent_name: Optional[str] = None,
    ) -> Tuple[bool, Any]:
        """Send a request and capture response for clarification analysis.

        Args:
            request: Request text
            user_id: User ID for the request
            session_id: Session ID for the request
            agent_name: Specific agent to target

        Returns:
            Tuple of (success, response)
        """
        try:
            # Execute through overlord
            response = await self.overlord.chat(
                request,
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                use_async=False,
                stream=False,
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
                # Create mock response object for compatibility
                response = type("MockResponse", (), {"content": response_text, "metadata": {}})()

            success = True
            return success, response

        except Exception as e:
            return False, f"Clarification request error: {str(e)}"

    def detect_clarification_request(self, response: Any) -> Dict[str, Any]:
        """Detect if response is asking for clarification.

        Args:
            response: Response object to analyze

        Returns:
            Dictionary with clarification analysis
        """
        analysis = {
            "is_clarification": False,
            "confidence": 0.0,
            "detected_patterns": [],
            "question_count": 0,
            "clarification_type": "none",
        }

        if not response:
            return analysis

        # Extract content
        if isinstance(response, str):
            content = response
            metadata = {}
        else:
            content = response.content if hasattr(response, "content") else str(response)
            metadata = getattr(response, "metadata", {})

        content_lower = content.lower()

        # Check for explicit clarification flag in metadata
        if metadata.get("clarification"):
            analysis["is_clarification"] = True
            analysis["confidence"] = 1.0
            analysis["clarification_type"] = "explicit"
            return analysis

        # Count clarification indicators
        indicator_count = 0
        for indicator in self.CLARIFICATION_INDICATORS:
            if indicator in content_lower:
                indicator_count += 1
                analysis["detected_patterns"].append(indicator)

        # Count question marks and question words
        question_count = content.count("?")
        analysis["question_count"] = question_count

        # Check for clarification patterns
        pattern_matches = 0
        for pattern_type, patterns in self.CLARIFICATION_PATTERNS.items():
            for pattern in patterns:
                if pattern in content_lower:
                    pattern_matches += 1
                    analysis["detected_patterns"].append(f"{pattern_type}:{pattern}")

        # Calculate confidence
        total_signals = indicator_count + (question_count * 2) + pattern_matches
        analysis["confidence"] = min(total_signals / 5.0, 1.0)  # Normalize to 0-1

        # Determine if it's a clarification
        analysis["is_clarification"] = analysis["confidence"] > 0.3

        # Classify clarification type
        if analysis["is_clarification"]:
            if question_count > 0:
                analysis["clarification_type"] = "question"
            elif any("option" in pattern for pattern in analysis["detected_patterns"]):
                analysis["clarification_type"] = "options"
            elif any("specific" in pattern for pattern in analysis["detected_patterns"]):
                analysis["clarification_type"] = "specification"
            else:
                analysis["clarification_type"] = "general"

        return analysis

    async def test_ambiguous_request_clarification(
        self, ambiguous_request: str, category: str = "vague_action"
    ) -> Tuple[bool, Dict[str, Any]]:
        """Test that ambiguous requests trigger clarification.

        Args:
            ambiguous_request: Ambiguous request to test
            category: Category of ambiguity

        Returns:
            Tuple of (success, clarification_details)
        """
        user_id, session_id = self.create_unique_session("ambiguous")

        success, response = await self.send_clarification_request(
            ambiguous_request, user_id=user_id, session_id=session_id
        )

        clarification_details = {
            "request": ambiguous_request,
            "category": category,
            "user_id": user_id,
            "session_id": session_id,
            "response_received": success,
            "clarification_analysis": {},
        }

        if not success:
            clarification_details["error"] = response
            return False, clarification_details

        analysis = self.detect_clarification_request(response)
        clarification_details["clarification_analysis"] = analysis

        # Store session for potential follow-up
        self.clarification_sessions.append((user_id, session_id, ambiguous_request, response))

        return analysis["is_clarification"], clarification_details

    async def test_clarification_follow_up(
        self, user_id: str, session_id: str, clarifying_response: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Test follow-up after clarification.

        Args:
            user_id: User ID from original session
            session_id: Session ID from original session
            clarifying_response: User's clarifying response

        Returns:
            Tuple of (success, follow_up_details)
        """
        success, response = await self.send_clarification_request(
            clarifying_response, user_id=user_id, session_id=session_id
        )

        follow_up_details = {
            "clarifying_response": clarifying_response,
            "user_id": user_id,
            "session_id": session_id,
            "response_received": success,
            "continued_clarification": False,
            "task_execution": False,
        }

        if not success:
            follow_up_details["error"] = response
            return False, follow_up_details

        # Check if system continues asking for clarification or starts execution
        clarification_analysis = self.detect_clarification_request(response)
        follow_up_details["continued_clarification"] = clarification_analysis["is_clarification"]

        # Check for task execution indicators
        content = response.content if hasattr(response, "content") else str(response)
        execution_indicators = [
            "proceeding",
            "starting",
            "implementing",
            "creating",
            "building",
            "I'll",
            "I will",
            "let me",
            "here's",
            "I've created",
        ]

        follow_up_details["task_execution"] = any(
            indicator in content.lower() for indicator in execution_indicators
        )

        # Success if either clarification continues appropriately or task execution begins
        success_criteria = (
            follow_up_details["continued_clarification"] or follow_up_details["task_execution"]
        )

        return success_criteria, follow_up_details

    async def test_multi_turn_clarification(
        self, initial_request: str, clarification_turns: List[str]
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """Test multi-turn clarification conversation.

        Args:
            initial_request: Initial ambiguous request
            clarification_turns: List of user responses for clarification

        Returns:
            Tuple of (success, turn_results)
        """
        user_id, session_id = self.create_unique_session("multi_turn")
        turn_results = []

        # Send initial request
        success, response = await self.send_clarification_request(
            initial_request, user_id=user_id, session_id=session_id
        )

        initial_analysis = self.detect_clarification_request(response) if success else {}
        turn_results.append(
            {
                "turn": 0,
                "message": initial_request,
                "response_received": success,
                "clarification_analysis": initial_analysis,
                "is_clarification": initial_analysis.get("is_clarification", False),
            }
        )

        if not success:
            return False, turn_results

        # Process clarification turns
        for i, clarifying_message in enumerate(clarification_turns, 1):
            success, follow_up_details = await self.test_clarification_follow_up(
                user_id, session_id, clarifying_message
            )

            turn_results.append(
                {
                    "turn": i,
                    "message": clarifying_message,
                    "follow_up_details": follow_up_details,
                    "success": success,
                }
            )

            # Short delay between turns
            await asyncio.sleep(0.5)

        # Overall success if we got appropriate responses throughout
        overall_success = all(turn["success"] for turn in turn_results[1:])  # Skip initial
        return overall_success, turn_results

    async def test_context_preservation(
        self, base_request: str, context_references: List[str]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Test that clarification preserves context across turns.

        Args:
            base_request: Base request to establish context
            context_references: References to previous context

        Returns:
            Tuple of (success, context_details)
        """
        user_id, session_id = self.create_unique_session("context")

        # Send base request
        success, initial_response = await self.send_clarification_request(
            base_request, user_id=user_id, session_id=session_id
        )

        context_details = {
            "base_request": base_request,
            "context_tests": [],
            "context_preserved": False,
        }

        if not success:
            context_details["error"] = "Initial request failed"
            return False, context_details

        # Test context references
        for reference in context_references:
            success, response = await self.send_clarification_request(
                reference, user_id=user_id, session_id=session_id
            )

            content = response.content if hasattr(response, "content") else str(response)

            # Check if response shows understanding of context
            context_understanding = any(
                word in content.lower()
                for word in ["previous", "earlier", "mentioned", "that", "it", "the"]
            )

            context_details["context_tests"].append(
                {
                    "reference": reference,
                    "success": success,
                    "context_understanding": context_understanding,
                    "response_preview": content[:100] + "..." if len(content) > 100 else content,
                }
            )

            await asyncio.sleep(0.5)

        # Overall context preservation
        context_details["context_preserved"] = any(
            test["context_understanding"] for test in context_details["context_tests"]
        )

        return context_details["context_preserved"], context_details

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None
        self.clarification_sessions = []

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

    def save_test_results(
        self, test_name: str, success: bool, sessions: List, details: Dict = None
    ):
        """Save test results to JSON file for analysis.

        Args:
            test_name: Name of the test
            success: Whether test passed
            sessions: List of clarification sessions
            details: Additional test details
        """
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{test_name}.json"

        result_data = {
            "test": test_name,
            "status": "PASSED" if success else "FAILED",
            "timestamp": time.time(),
            "sessions_count": len(sessions),
            "sessions": [
                {
                    "user_id": session[0],
                    "session_id": session[1],
                    "request": session[2],
                    "response_preview": (
                        session[3].content[:200]
                        if hasattr(session[3], "content")
                        else str(session[3])[:200]
                    ),
                }
                for session in sessions
            ],
        }

        if details:
            result_data.update(details)

        with open(output_file, "w") as f:
            json.dump(result_data, f, indent=2)

        print(f"💾 Results saved to: {output_file}")
