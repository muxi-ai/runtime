#!/usr/bin/env python3
"""Base test class for Area 7 Orchestration tests with standardized patterns."""

import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import json

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402

# Import from common module
from common import BaseE2ETest  # noqa: E402
from common import TestOutputFormatter  # noqa: E402


class BaseOrchestrationTest(BaseE2ETest):
    """Base class for Orchestration tests."""

    # Shared formation directory for all orchestration tests
    FORMATION_DIR = Path(__file__).parent / "formations" / "formation-multi-agent"

    # Complexity thresholds for workflow triggers
    COMPLEXITY_THRESHOLDS = {
        "simple": 3.0,  # Simple single-agent requests
        "moderate": 5.0,  # Multi-step but single-agent
        "complex": 7.0,  # Multi-agent or multi-step workflows
        "very_complex": 9.0,  # Advanced orchestration with approval
    }

    # Workflow patterns to detect in responses
    WORKFLOW_PATTERNS = {
        "task_decomposition": ["task", "step", "phase", "breakdown", "decompos", "workflow"],
        "agent_coordination": ["coordinating", "routing", "delegating", "agent", "specialist"],
        "approval_requested": [
            "approve",
            "approval",
            "confirm",
            "proceed",
            "does this approach work",
            "proposed approach",
            "plan look good",
        ],
        "sop_execution": ["sop", "standard operating procedure", "following procedure", "protocol"],
        "multi_step": ["first", "next", "then", "finally", "step 1", "step 2", "phase"],
    }

    # Agent capabilities for orchestration testing
    AGENT_CAPABILITIES = {
        "research": ["researcher", "web", "search", "analysis"],
        "coding": ["developer", "code", "programming", "implementation"],
        "content": ["writer", "content", "documentation", "summary"],
        "data": ["analyst", "data", "processing", "visualization"],
        "project": ["manager", "coordination", "planning", "organization"],
    }

    def __init__(self):
        """Initialize base orchestration test."""
        super().__init__()
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None
        self.workflow_interactions = []

    async def setup_orchestration_formation(self) -> Formation:
        """Setup formation with multi-agent orchestration capabilities.

        Returns:
            Configured Formation instance
        """
        formation_path = self.FORMATION_DIR / "formation.yaml"

        self.formation = Formation()
        await self.formation.load(str(formation_path))

        # Store overlord reference
        self.overlord = await self.formation.start_overlord()

        return self.formation

    async def send_orchestration_request(
        self,
        request: str,
        user_id: str = "test_user",
        session_id: str = "test_session",
        agent_name: Optional[str] = None,
        stream: bool = False,
    ) -> Tuple[bool, Any]:
        """Send an orchestration request and capture response.

        Args:
            request: Natural language request
            user_id: User ID for the request
            session_id: Session ID for the request
            agent_name: Specific agent to target (None for overlord routing)
            stream: Whether to use streaming response

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
                stream=stream,
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
                # Create mock response object for compatibility
                response = type("MockResponse", (), {"content": response_text})()

            success = True
            self.workflow_interactions.append((request, response))

            return success, response

        except Exception as e:
            return False, f"Orchestration request error: {str(e)}"

    def analyze_workflow_complexity(self, request: str) -> Dict[str, Any]:
        """Analyze request complexity to predict workflow behavior.

        Args:
            request: Request text to analyze

        Returns:
            Dictionary with complexity analysis
        """
        analysis = {
            "estimated_complexity": 1.0,
            "triggers_workflow": False,
            "expected_agents": [],
            "multi_step": False,
            "requires_approval": False,
        }

        request_lower = request.lower()

        # Count complexity indicators
        complexity_score = 1.0

        # Multi-verb complexity
        action_verbs = [
            "research",
            "analyze",
            "create",
            "write",
            "build",
            "develop",
            "implement",
            "test",
        ]
        verb_count = sum(1 for verb in action_verbs if verb in request_lower)
        complexity_score += verb_count * 1.5

        # Multi-domain complexity
        domains = ["data", "code", "content", "analysis", "visualization", "document"]
        domain_count = sum(1 for domain in domains if domain in request_lower)
        complexity_score += domain_count * 1.0

        # Coordination words
        coordination_words = ["and", "then", "after", "coordinate", "combine", "integrate"]
        coordination_count = sum(1 for word in coordination_words if word in request_lower)
        complexity_score += coordination_count * 0.5

        # Length factor
        word_count = len(request.split())
        if word_count > 20:
            complexity_score += 1.0
        if word_count > 40:
            complexity_score += 2.0

        analysis["estimated_complexity"] = complexity_score
        analysis["triggers_workflow"] = complexity_score >= self.COMPLEXITY_THRESHOLDS["complex"]
        analysis["multi_step"] = verb_count > 2 or coordination_count > 1
        analysis["requires_approval"] = (
            complexity_score >= self.COMPLEXITY_THRESHOLDS["very_complex"]
        )

        # Predict required agents based on keywords
        for capability, keywords in self.AGENT_CAPABILITIES.items():
            if any(keyword in request_lower for keyword in keywords):
                analysis["expected_agents"].append(capability)

        return analysis

    def analyze_response_patterns(self, response: Any) -> Dict[str, bool]:
        """Analyze response for orchestration patterns.

        Args:
            response: Response object to analyze

        Returns:
            Dictionary of detected patterns
        """
        patterns = {
            "workflow_triggered": False,
            "task_decomposition": False,
            "agent_coordination": False,
            "approval_requested": False,
            "sop_execution": False,
            "multi_step_execution": False,
        }

        if not response:
            return patterns

        content = response.content if hasattr(response, "content") else str(response)
        content_lower = content.lower()

        # Check each pattern
        for pattern_name, keywords in self.WORKFLOW_PATTERNS.items():
            patterns[pattern_name] = any(keyword in content_lower for keyword in keywords)

        # Workflow triggered if any orchestration pattern is detected
        patterns["workflow_triggered"] = any(
            [
                patterns["task_decomposition"],
                patterns["agent_coordination"],
                patterns["sop_execution"],
                patterns["multi_step_execution"],
            ]
        )

        return patterns

    async def test_simple_routing(self, request: str, expected_capability: str) -> Tuple[bool, str]:
        """Test simple agent routing for single-capability requests.

        Args:
            request: Request that should route to specific capability
            expected_capability: Expected agent capability

        Returns:
            Tuple of (success, details)
        """
        success, response = await self.send_orchestration_request(request)

        if not success:
            return False, f"Failed to process request: {response}"

        patterns = self.analyze_response_patterns(response)
        content = response.content if hasattr(response, "content") else str(response)

        # Simple routing should NOT trigger complex workflows
        if patterns["workflow_triggered"]:
            return False, "Simple request incorrectly triggered workflow"

        # Check if response indicates correct capability
        capability_keywords = self.AGENT_CAPABILITIES.get(expected_capability, [])
        if any(keyword in content.lower() for keyword in capability_keywords):
            return True, f"Successfully routed to {expected_capability} capability"

        return False, f"Response doesn't indicate {expected_capability} capability"

    async def test_workflow_decomposition(
        self, complex_request: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Test workflow decomposition for complex requests.

        Args:
            complex_request: Complex request that should trigger workflow

        Returns:
            Tuple of (success, workflow_details)
        """
        analysis = self.analyze_workflow_complexity(complex_request)
        success, response = await self.send_orchestration_request(complex_request)

        workflow_details = {
            "complexity_analysis": analysis,
            "response_patterns": {},
            "workflow_triggered": False,
            "approval_requested": False,
        }

        if not success:
            workflow_details["error"] = response
            return False, workflow_details

        patterns = self.analyze_response_patterns(response)
        workflow_details["response_patterns"] = patterns
        workflow_details["workflow_triggered"] = patterns["workflow_triggered"]
        workflow_details["approval_requested"] = patterns["approval_requested"]

        # For complex requests, expect workflow to be triggered
        expected_workflow = analysis["triggers_workflow"]
        actual_workflow = patterns["workflow_triggered"]

        if expected_workflow and actual_workflow:
            return True, workflow_details
        elif not expected_workflow and not actual_workflow:
            return True, workflow_details  # Correctly didn't trigger workflow
        else:
            return False, workflow_details  # Mismatch between expected and actual

    async def test_approval_workflow(self, high_complexity_request: str) -> Tuple[bool, List[str]]:
        """Test approval workflow for high-complexity requests.

        Args:
            high_complexity_request: Request that should require approval

        Returns:
            Tuple of (success, interaction_log)
        """
        interaction_log = []

        # Send initial request
        success, response = await self.send_orchestration_request(high_complexity_request)
        if not success:
            return False, [f"Initial request failed: {response}"]

        content = response.content if hasattr(response, "content") else str(response)
        interaction_log.append(f"Request: {high_complexity_request}")
        interaction_log.append(f"Response: {content[:200]}...")

        patterns = self.analyze_response_patterns(response)

        if patterns["approval_requested"]:
            interaction_log.append("✅ Approval requested as expected")

            # Send approval
            approval_response = await self.send_orchestration_request(
                "Yes, please proceed with the plan",
                session_id="test_session",  # Same session for context
            )

            if approval_response[0]:
                approval_content = (
                    approval_response[1].content
                    if hasattr(approval_response[1], "content")
                    else str(approval_response[1])
                )
                interaction_log.append(f"Approval response: {approval_content[:200]}...")
                return True, interaction_log
            else:
                interaction_log.append("❌ Approval response failed")
                return False, interaction_log
        else:
            interaction_log.append("❌ No approval requested for high-complexity request")
            return False, interaction_log

    async def test_multi_agent_coordination(self, multi_domain_request: str) -> Tuple[bool, Dict]:
        """Test multi-agent coordination for requests spanning multiple domains.

        Args:
            multi_domain_request: Request requiring multiple agent capabilities

        Returns:
            Tuple of (success, coordination_details)
        """
        analysis = self.analyze_workflow_complexity(multi_domain_request)
        success, response = await self.send_orchestration_request(multi_domain_request)

        coordination_details = {
            "expected_agents": analysis["expected_agents"],
            "detected_coordination": False,
            "workflow_elements": [],
        }

        if not success:
            coordination_details["error"] = response
            return False, coordination_details

        patterns = self.analyze_response_patterns(response)
        content = response.content if hasattr(response, "content") else str(response)

        # Check for coordination indicators
        coordination_details["detected_coordination"] = patterns["agent_coordination"]

        # Look for workflow elements
        if patterns["task_decomposition"]:
            coordination_details["workflow_elements"].append("task_decomposition")
        if patterns["multi_step_execution"]:
            coordination_details["workflow_elements"].append("multi_step_execution")
        if patterns["sop_execution"]:
            coordination_details["workflow_elements"].append("sop_execution")

        # Check if multiple expected agents are mentioned
        agents_mentioned = 0
        for capability in analysis["expected_agents"]:
            capability_keywords = self.AGENT_CAPABILITIES.get(capability, [])
            if any(keyword in content.lower() for keyword in capability_keywords):
                agents_mentioned += 1

        coordination_details["agents_mentioned"] = agents_mentioned
        success_criteria = len(analysis["expected_agents"]) > 1 and (
            coordination_details["detected_coordination"]
            or len(coordination_details["workflow_elements"]) > 0
        )

        return success_criteria, coordination_details

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None
        self.workflow_interactions = []

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
        self, test_name: str, success: bool, interactions: List, details: Dict = None
    ):
        """Save test results to JSON file for analysis.

        Args:
            test_name: Name of the test
            success: Whether test passed
            interactions: List of workflow interactions
            details: Additional test details
        """
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{test_name}.json"

        result_data = {
            "test": test_name,
            "status": "PASSED" if success else "FAILED",
            "timestamp": time.time(),
            "interactions_count": len(interactions),
            "interactions": [
                {
                    "request": interaction[0],
                    "response_preview": (
                        interaction[1].content[:200]
                        if hasattr(interaction[1], "content")
                        else str(interaction[1])[:200]
                    ),
                }
                for interaction in interactions
            ],
        }

        if details:
            result_data.update(details)

        with open(output_file, "w") as f:
            json.dump(result_data, f, indent=2)

        print(f"💾 Results saved to: {output_file}")
