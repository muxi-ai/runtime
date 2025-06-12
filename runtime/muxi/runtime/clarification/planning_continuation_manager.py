"""
Planning Continuation Manager for Phase 4B

Manages the transition from information gathering to collaborative planning.
Tracks workflow state and generates contextual follow-up interactions.
"""

import logging
import time
from typing import Dict, Optional, List
from datetime import datetime

from .types import (
    PlanningWorkflowSession,
    PlanningWorkflowRequest,
    ToolExecutionResult,
    WorkflowState,
    WorkflowSynthesis
)

logger = logging.getLogger(__name__)


class PlanningContinuationManager:
    """
    Manages planning workflow sessions and state transitions.

    Handles:
    - Workflow state tracking
    - Session management
    - Planning continuation after tool execution
    - Context preservation across interactions
    """

    def __init__(self):
        """Initialize planning continuation manager."""
        self.active_sessions: Dict[str, PlanningWorkflowSession] = {}
        self.session_timeouts = {}
        self.default_timeout = 1800  # 30 minutes

    def create_session(
        self,
        user_id: str,
        agent_id: str,
        workflow_request: PlanningWorkflowRequest
    ) -> PlanningWorkflowSession:
        """
        Create a new planning workflow session.

        Args:
            user_id: User identifier
            agent_id: Agent identifier
            workflow_request: Planning workflow request

        Returns:
            New planning workflow session
        """
        session = PlanningWorkflowSession(
            session_id=f"planning_{user_id}_{int(time.time())}",
            user_id=user_id,
            agent_id=agent_id,
            workflow_request=workflow_request,
            current_state=WorkflowState.INFORMATION_GATHERING
        )

        self.active_sessions[session.session_id] = session
        self.session_timeouts[session.session_id] = time.time() + self.default_timeout

        logger.info(f"Created planning session {session.session_id} for workflow {workflow_request.workflow_type}")

        return session

    def get_session(self, session_id: str) -> Optional[PlanningWorkflowSession]:
        """Get an active planning session by ID."""
        return self.active_sessions.get(session_id)

    def add_tool_result(
        self,
        session_id: str,
        tool_result: ToolExecutionResult
    ) -> bool:
        """
        Add a tool execution result to a planning session.

        Args:
            session_id: Planning session ID
            tool_result: Result from tool execution

        Returns:
            True if added successfully, False otherwise
        """
        session = self.get_session(session_id)
        if not session:
            logger.warning(f"Planning session {session_id} not found")
            return False

        session.executed_tools.append(tool_result)
        session.updated_at = time.time()

        # Update state based on tool results
        if session.current_state == WorkflowState.INFORMATION_GATHERING:
            # Check if we have enough data to move to synthesis
            successful_tools = [r for r in session.executed_tools if r.success]
            if len(successful_tools) >= 1:
                session.current_state = WorkflowState.DATA_SYNTHESIS

        logger.debug(f"Added tool result to session {session_id}, state: {session.current_state}")

        return True

    def update_synthesis(
        self,
        session_id: str,
        synthesis: WorkflowSynthesis
    ) -> bool:
        """
        Update planning session with synthesis results.

        Args:
            session_id: Planning session ID
            synthesis: Workflow synthesis results

        Returns:
            True if updated successfully, False otherwise
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session.synthesis = synthesis
        session.current_state = WorkflowState.OPTION_PRESENTATION
        session.updated_at = time.time()

        logger.debug(f"Updated synthesis for session {session_id}")

        return True

    def advance_to_refinement(self, session_id: str) -> bool:
        """Advance session to decision refinement state."""
        session = self.get_session(session_id)
        if not session:
            return False

        session.current_state = WorkflowState.DECISION_REFINEMENT
        session.updated_at = time.time()

        return True

    def complete_session(self, session_id: str) -> bool:
        """Mark a planning session as complete."""
        session = self.get_session(session_id)
        if not session:
            return False

        session.current_state = WorkflowState.PLANNING_COMPLETE
        session.updated_at = time.time()

        logger.info(f"Completed planning session {session_id}")

        return True

    def should_continue_planning(self, session_id: str) -> bool:
        """
        Determine if planning workflow should continue.

        Args:
            session_id: Planning session ID

        Returns:
            True if planning should continue, False otherwise
        """
        session = self.get_session(session_id)
        if not session:
            return False

        # Check session timeout
        if time.time() > self.session_timeouts.get(session_id, 0):
            self.cleanup_session(session_id)
            return False

        # Continue if not complete
        return session.current_state != WorkflowState.PLANNING_COMPLETE

    def get_planning_response(self, session_id: str) -> Optional[str]:
        """
        Generate planning response based on current session state.

        Args:
            session_id: Planning session ID

        Returns:
            Planning response text or None
        """
        session = self.get_session(session_id)
        if not session:
            return None

        if session.current_state == WorkflowState.DATA_SYNTHESIS:
            return self._generate_synthesis_response(session)
        elif session.current_state == WorkflowState.OPTION_PRESENTATION:
            return self._generate_options_response(session)
        elif session.current_state == WorkflowState.DECISION_REFINEMENT:
            return self._generate_refinement_response(session)

        return None

    def _generate_synthesis_response(self, session: PlanningWorkflowSession) -> str:
        """Generate response for data synthesis state."""
        successful_tools = [r for r in session.executed_tools if r.success]

        if not successful_tools:
            return (f"I wasn't able to retrieve the information needed for your {session.workflow_request.planning_goal}. "
                   f"Would you like to try alternative approaches or proceed with what we know?")

        tool_names = [r.tool_name for r in successful_tools]
        return (f"I've gathered information from {len(successful_tools)} sources ({', '.join(tool_names)}) "
               f"for your {session.workflow_request.planning_goal}. "
               f"Let me analyze this data and present your options...")

    def _generate_options_response(self, session: PlanningWorkflowSession) -> str:
        """Generate response for option presentation state."""
        if not session.synthesis:
            return "I'm processing the data to create your options..."

        response_parts = [
            f"Based on the information gathered for your {session.workflow_request.planning_goal}, here's what I found:\n"
        ]

        # Add key insights
        if session.synthesis.key_insights:
            response_parts.append("**Key Insights:**")
            for insight in session.synthesis.key_insights:
                response_parts.append(f"• {insight}")
            response_parts.append("")

        # Add options if available
        if session.synthesis.options:
            response_parts.append("**Your Options:**")
            for i, option in enumerate(session.synthesis.options[:3], 1):
                response_parts.append(f"{i}. {option.get('title', 'Option')}: {option.get('description', '')}")
            response_parts.append("")

        # Add trade-offs
        if session.synthesis.trade_offs:
            response_parts.append("**Key Trade-offs to Consider:**")
            for trade_off in session.synthesis.trade_offs:
                response_parts.append(f"• {trade_off}")
            response_parts.append("")

        # Add follow-up questions
        if session.synthesis.follow_up_questions:
            response_parts.append("To help you decide:")
            for question in session.synthesis.follow_up_questions:
                response_parts.append(f"• {question}")

        return "\n".join(response_parts)

    def _generate_refinement_response(self, session: PlanningWorkflowSession) -> str:
        """Generate response for decision refinement state."""
        return (f"I'm here to help you refine your decision for {session.workflow_request.planning_goal}. "
               f"What aspects would you like to explore further, or do you have specific questions about the options?")

    def cleanup_session(self, session_id: str) -> None:
        """Clean up expired or completed session."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        if session_id in self.session_timeouts:
            del self.session_timeouts[session_id]

        logger.debug(f"Cleaned up planning session {session_id}")

    def cleanup_expired_sessions(self) -> None:
        """Clean up all expired sessions."""
        current_time = time.time()
        expired_sessions = [
            session_id for session_id, timeout_time in self.session_timeouts.items()
            if current_time > timeout_time
        ]

        for session_id in expired_sessions:
            self.cleanup_session(session_id)

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired planning sessions")

    def get_session_summary(self, session_id: str) -> Optional[Dict]:
        """Get summary of planning session state."""
        session = self.get_session(session_id)
        if not session:
            return None

        return {
            "session_id": session.session_id,
            "workflow_type": session.workflow_request.workflow_type.value,
            "planning_goal": session.workflow_request.planning_goal,
            "current_state": session.current_state.value,
            "tools_executed": len(session.executed_tools),
            "successful_tools": len([r for r in session.executed_tools if r.success]),
            "has_synthesis": session.synthesis is not None,
            "created_at": datetime.fromtimestamp(session.created_at).isoformat(),
            "updated_at": datetime.fromtimestamp(session.updated_at).isoformat()
        }
