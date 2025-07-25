"""
Clarification Mode Manager

This module manages different conversation modes for proactive clarification,
switching between reactive and proactive questioning based on user needs.
"""

import time
from typing import Dict, Optional, List

from ...datatypes.clarification import (
    ClarificationMode,
    ClarificationSession,
    ProactiveRequest,
    ProactiveRequestType,
    GoalContext,
    PlanAnalysis,
    ClarificationError,
)


class ClarificationModeManager:
    """Manages different conversation modes and session state"""

    def __init__(self, overlord):
        """
        Initialize the mode manager

        Args:
            overlord: Reference to the overlord for coordination
        """
        self.overlord = overlord
        self.active_sessions: Dict[str, ClarificationSession] = {}
        self._user_to_session: Dict[str, str] = {}  # user_id -> session_id mapping

    async def enter_proactive_mode(
        self, user_id: str, agent_id: str, proactive_request: ProactiveRequest
    ) -> ClarificationSession:
        """
        Switch to proactive questioning mode with specific goal

        Args:
            user_id: ID of the user
            agent_id: ID of the agent
            proactive_request: The proactive request that triggered this mode

        Returns:
            ClarificationSession for tracking the proactive conversation
        """
        try:
            #  Info - TODO: add observability

            # Cancel any existing session for this user
            await self._cancel_existing_session(user_id)

            # Determine the appropriate mode based on request type
            mode = self._determine_mode_from_request(proactive_request)

            # Create goal context for goal-driven modes
            goal_context = None
            if mode in [
                ClarificationMode.PROACTIVE_QUESTIONING,
                ClarificationMode.GOAL_ACHIEVEMENT,
            ]:
                goal_context = await self._create_goal_context(proactive_request)

            # Create new clarification session
            session = ClarificationSession(
                session_id="",  # Will be auto-generated
                user_id=user_id,
                agent_id=agent_id,
                mode=mode,
                proactive_request=proactive_request,
                goal_context=goal_context,
                max_questions=proactive_request.max_questions,
            )

            # Store the session
            self.active_sessions[session.session_id] = session
            self._user_to_session[user_id] = session.session_id

            #  Info - TODO: add observability
            return session

        except Exception as e:
            #  Error - TODO: add observability
            raise ClarificationError(f"Failed to enter proactive mode: {e}")

    async def enter_plan_analysis_mode(
        self, user_id: str, agent_id: str, plan_analysis: PlanAnalysis
    ) -> ClarificationSession:
        """
        Switch to plan analysis mode for multi-step planning assistance

        Args:
            user_id: ID of the user
            agent_id: ID of the agent
            plan_analysis: Analysis of the user's multi-step plan

        Returns:
            ClarificationSession for tracking the plan analysis conversation
        """
        try:
            #  Info - TODO: add observability

            # Cancel any existing session for this user
            await self._cancel_existing_session(user_id)

            # Create new clarification session for plan analysis
            session = ClarificationSession(
                session_id="",  # Will be auto-generated
                user_id=user_id,
                agent_id=agent_id,
                mode=ClarificationMode.PLAN_ANALYSIS,
                plan_analysis=plan_analysis,
                max_questions=len(plan_analysis.clarification_questions) + 3,  # Flexible limit
            )

            # Store the session
            self.active_sessions[session.session_id] = session
            self._user_to_session[user_id] = session.session_id

            #  Info - TODO: add observability
            return session

        except Exception as e:
            #  Error - TODO: add observability
            raise ClarificationError(f"Failed to enter plan analysis mode: {e}")

    async def get_active_session(self, user_id: str) -> Optional[ClarificationSession]:
        """
        Get the active clarification session for a user

        Args:
            user_id: ID of the user

        Returns:
            Active ClarificationSession if exists, None otherwise
        """
        session_id = self._user_to_session.get(user_id)
        if session_id:
            return self.active_sessions.get(session_id)
        return None

    async def update_session_progress(
        self, session_id: str, collected_info: Dict[str, any] = None, questions_asked: int = None
    ) -> bool:
        """
        Update session progress with new information

        Args:
            session_id: ID of the session to update
            collected_info: Information collected in this turn
            questions_asked: Number of questions asked so far

        Returns:
            True if session updated successfully, False otherwise
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                return False

            # Update session state
            session.updated_at = time.time()

            if questions_asked is not None:
                session.questions_asked = questions_asked

            # Update goal context if in goal-driven mode
            if session.goal_context and collected_info:
                await self._update_goal_context(session, collected_info)

            # Check completion criteria
            await self._check_completion_criteria(session)

            #  Debug - TODO: add observability
            return True

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            return False

    async def complete_session(self, session_id: str) -> Dict[str, any]:
        """
        Complete a clarification session and return collected information

        Args:
            session_id: ID of the session to complete

        Returns:
            Dictionary containing all collected information
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ClarificationError("Session not found")

            # Compile final results
            complete_info = {}

            if session.goal_context:
                complete_info.update(session.goal_context.collected_info)
                complete_info["goal_achievement"] = {
                    "goal": session.goal_context.goal,
                    "completion_percentage": session.goal_context.completion_percentage,
                    "goal_type": session.goal_context.goal_type,
                }

            if session.plan_analysis:
                complete_info["plan_analysis"] = {
                    "overall_feasibility": session.plan_analysis.overall_feasibility,
                    "recommendations": session.plan_analysis.recommendations,
                    "steps_analyzed": len(session.plan_analysis.step_analyses),
                }

            # Clean up the session
            self._cleanup_session(session_id)

            #  Info - TODO: add observability
            return complete_info

        except Exception as e:
            #  Error - TODO: add observability
            raise ClarificationError(f"Failed to complete session: {e}")

    async def cancel_session(self, session_id: str) -> bool:
        """
        Cancel an active clarification session

        Args:
            session_id: ID of the session to cancel

        Returns:
            True if session was cancelled, False if not found
        """
        try:
            if session_id in self.active_sessions:
                self._cleanup_session(session_id)
                #  Info - TODO: add observability
                return True
            return False

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            return False

    def _determine_mode_from_request(
        self, proactive_request: ProactiveRequest
    ) -> ClarificationMode:
        """Determine the appropriate clarification mode from the request type"""
        mode_mapping = {
            ProactiveRequestType.GUIDED_QUESTIONING: ClarificationMode.PROACTIVE_QUESTIONING,
            ProactiveRequestType.PLAN_FEEDBACK: ClarificationMode.PLAN_ANALYSIS,
            ProactiveRequestType.CONTEXT_FIRST: ClarificationMode.CONTEXT_BUILDING,
            ProactiveRequestType.STEP_BY_STEP: ClarificationMode.GOAL_ACHIEVEMENT,
            ProactiveRequestType.COMPREHENSIVE_ADVICE: ClarificationMode.GOAL_ACHIEVEMENT,
        }
        return mode_mapping.get(
            proactive_request.request_type, ClarificationMode.PROACTIVE_QUESTIONING
        )

    async def _create_goal_context(self, proactive_request: ProactiveRequest) -> GoalContext:
        """Create goal context for goal-driven clarification"""
        goal_type = self._determine_goal_type(proactive_request.goal)
        required_info_areas = self._determine_required_info_areas(goal_type, proactive_request.goal)

        return GoalContext(
            goal=proactive_request.goal,
            goal_type=goal_type,
            required_info_areas=required_info_areas,
            collected_info={},
            completion_percentage=0.0,
        )

    def _determine_goal_type(self, goal: str) -> str:
        """Determine the type of goal based on content analysis"""
        goal_lower = goal.lower()

        if any(word in goal_lower for word in ["invest", "financial", "portfolio", "money"]):
            return "investment_advice"
        elif any(word in goal_lower for word in ["business", "startup", "company", "entrepreneur"]):
            return "business_planning"
        elif any(word in goal_lower for word in ["career", "job", "position", "work"]):
            return "career_guidance"
        elif any(word in goal_lower for word in ["learn", "study", "education", "skill"]):
            return "learning_guidance"
        elif any(word in goal_lower for word in ["health", "fitness", "wellness", "medical"]):
            return "health_guidance"
        elif any(word in goal_lower for word in ["travel", "trip", "vacation", "journey"]):
            return "travel_planning"
        else:
            return "general_assistance"

    def _determine_required_info_areas(self, goal_type: str, goal: str) -> List[str]:
        """Determine what information areas are needed for the goal"""
        common_areas = ["background", "preferences", "constraints", "timeline"]

        goal_specific_areas = {
            "investment_advice": [
                "risk_tolerance",
                "financial_situation",
                "investment_timeline",
                "investment_goals",
            ],
            "business_planning": [
                "business_idea",
                "market_research",
                "funding_needs",
                "experience",
            ],
            "career_guidance": [
                "current_situation",
                "career_goals",
                "skills",
                "industry_preferences",
            ],
            "learning_guidance": ["current_knowledge", "learning_style", "available_time", "goals"],
            "health_guidance": ["current_health", "goals", "limitations", "preferences"],
            "travel_planning": ["destination_preferences", "budget", "travel_dates", "group_size"],
            "general_assistance": ["specific_needs", "context", "goals", "preferences"],
        }

        specific_areas = goal_specific_areas.get(goal_type, [])
        return common_areas + specific_areas

    async def _update_goal_context(
        self, session: ClarificationSession, collected_info: Dict[str, any]
    ):
        """Update goal context with newly collected information"""
        if not session.goal_context:
            return

        # Update collected information
        session.goal_context.collected_info.update(collected_info)

        # Calculate completion percentage
        total_areas = len(session.goal_context.required_info_areas)
        covered_areas = sum(
            1
            for area in session.goal_context.required_info_areas
            if any(
                area.lower() in key.lower() for key in session.goal_context.collected_info.keys()
            )
        )

        session.goal_context.completion_percentage = (
            (covered_areas / total_areas) if total_areas > 0 else 1.0
        )

        # Determine next focus area
        for area in session.goal_context.required_info_areas:
            if not any(
                area.lower() in key.lower() for key in session.goal_context.collected_info.keys()
            ):
                session.goal_context.next_focus_area = area
                break
        else:
            session.goal_context.next_focus_area = None

    async def _check_completion_criteria(self, session: ClarificationSession):
        """Check if session completion criteria have been met"""
        if session.proactive_request:
            criteria = session.proactive_request.completion_criteria

            # Check goal-based completion
            if session.goal_context and session.goal_context.completion_percentage >= 0.8:
                session.completion_criteria_met = True

            # Check question limit
            elif session.questions_asked >= session.max_questions:
                session.completion_criteria_met = True

            # Check custom criteria
            elif criteria and "sufficient information" in criteria.lower():
                if session.goal_context and session.goal_context.completion_percentage >= 0.7:
                    session.completion_criteria_met = True

    async def _cancel_existing_session(self, user_id: str):
        """Cancel any existing session for a user"""
        existing_session_id = self._user_to_session.get(user_id)
        if existing_session_id:
            await self.cancel_session(existing_session_id)

    def _cleanup_session(self, session_id: str):
        """Clean up session resources"""
        session = self.active_sessions.get(session_id)
        if session:
            # Remove from user mapping
            if session.user_id in self._user_to_session:
                del self._user_to_session[session.user_id]

            # Remove from active sessions
            del self.active_sessions[session_id]
