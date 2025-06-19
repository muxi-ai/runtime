"""
Plan Analyzer

This module analyzes multi-step plans provided by users, evaluating
feasibility, identifying gaps, and generating clarification questions.
"""

from typing import List, Optional

from .datatypes import MultiStepPlan, PlanAnalysis, PlanStepAnalysis, ClarificationError


class PlanAnalyzer:
    """Analyzes multi-step plans and provides structured feedback"""

    def __init__(self, model=None):
        """
        Initialize the plan analyzer

        Args:
            model: Optional LLM model for advanced analysis
        """
        self.model = model

    async def analyze_plan(self, plan: MultiStepPlan) -> PlanAnalysis:
        """
        Analyze a multi-step plan and provide comprehensive feedback

        Args:
            plan: MultiStepPlan to analyze

        Returns:
            PlanAnalysis with detailed feedback and recommendations
        """
        try:
            #  Info - TODO: add observability

            # Analyze individual steps
            step_analyses = []
            for i, step in enumerate(plan.steps):
                step_analysis = await self._analyze_step(i, step, plan)
                step_analyses.append(step_analysis)

            # Calculate overall feasibility
            overall_feasibility = self._calculate_overall_feasibility(step_analyses)

            # Identify missing steps
            missing_steps = await self._identify_missing_steps(plan, step_analyses)

            # Generate clarification questions
            clarification_questions = self._generate_clarification_questions(
                plan, step_analyses, missing_steps
            )

            # Provide recommendations
            recommendations = self._generate_recommendations(
                plan, step_analyses, missing_steps, overall_feasibility
            )

            # Check if reordering is needed
            suggested_reordering = self._suggest_reordering(plan, step_analyses)

            analysis = PlanAnalysis(
                plan=plan,
                overall_feasibility=overall_feasibility,
                step_analyses=step_analyses,
                missing_steps=missing_steps,
                suggested_reordering=suggested_reordering,
                clarification_questions=clarification_questions,
                recommendations=recommendations,
            )

            #  Info - TODO: add observability
            return analysis

        except Exception as e:
            #  Error - TODO: add observability
            raise ClarificationError(f"Failed to analyze plan: {e}")

    async def _analyze_step(self, index: int, step: str, plan: MultiStepPlan) -> PlanStepAnalysis:
        """Analyze an individual step in the plan"""
        try:
            # Basic analysis based on step content
            feasibility_score = self._assess_step_feasibility(step, plan.goal)
            clarity_score = self._assess_step_clarity(step)
            requirements = self._identify_step_requirements(step)
            potential_issues = self._identify_potential_issues(step, plan.goal)
            suggested_clarifications = self._suggest_step_clarifications(step)

            # Determine dependencies based on step content and position
            dependencies = self._determine_step_dependencies(index, step, plan.steps)

            return PlanStepAnalysis(
                step_index=index,
                step_text=step,
                feasibility_score=feasibility_score,
                clarity_score=clarity_score,
                requirements=requirements,
                potential_issues=potential_issues,
                suggested_clarifications=suggested_clarifications,
                dependencies=dependencies,
            )

        except Exception as e:
            #  Warning - TODO: add observability
            _ = e  # remove this after implementing observability

            # Return basic analysis on error
            return PlanStepAnalysis(
                step_index=index,
                step_text=step,
                feasibility_score=0.5,
                clarity_score=0.5,
                requirements=[],
                potential_issues=["Analysis incomplete"],
                suggested_clarifications=[],
                dependencies=[],
            )

    def _assess_step_feasibility(self, step: str, goal: str) -> float:
        """Assess how feasible a step is to implement"""
        step_lower = step.lower()
        goal_lower = goal.lower()

        # Check for vague or unrealistic language
        vague_indicators = ["somehow", "maybe", "hopefully", "eventually", "magically"]
        if any(indicator in step_lower for indicator in vague_indicators):
            return 0.3

        # Check for complexity indicators
        complex_indicators = ["develop", "create", "build", "design", "implement"]
        simple_indicators = ["research", "contact", "find", "apply", "submit"]

        if any(indicator in step_lower for indicator in complex_indicators):
            feasibility = 0.6  # Complex but doable
        elif any(indicator in step_lower for indicator in simple_indicators):
            feasibility = 0.8  # Simple and straightforward
        else:
            feasibility = 0.7  # Neutral

        # Check for goal relevance
        if goal_lower in step_lower or any(
            word in step_lower for word in goal_lower.split() if len(word) > 3
        ):
            feasibility += 0.1

        return min(feasibility, 1.0)

    def _assess_step_clarity(self, step: str) -> float:
        """Assess how clear and specific a step is"""
        step_lower = step.lower()

        # Check for specific language
        specific_indicators = ["specific", "exactly", "precisely", "detailed"]
        vague_indicators = ["some", "various", "different", "general", "maybe"]

        clarity = 0.5  # Base clarity

        # Positive indicators
        if any(indicator in step_lower for indicator in specific_indicators):
            clarity += 0.2
        if any(char.isdigit() for char in step):  # Contains numbers
            clarity += 0.1
        if len(step.split()) > 8:  # Detailed description
            clarity += 0.1

        # Negative indicators
        if any(indicator in step_lower for indicator in vague_indicators):
            clarity -= 0.2
        if len(step.split()) < 4:  # Too brief
            clarity -= 0.1

        return max(0.1, min(clarity, 1.0))

    def _identify_step_requirements(self, step: str) -> List[str]:
        """Identify what's required to complete a step"""
        requirements = []
        step_lower = step.lower()

        # Common requirement patterns
        if any(word in step_lower for word in ["research", "find", "discover"]):
            requirements.append("Information gathering")
        if any(word in step_lower for word in ["contact", "call", "email", "reach out"]):
            requirements.append("Communication skills")
        if any(word in step_lower for word in ["money", "funding", "invest", "pay"]):
            requirements.append("Financial resources")
        if any(word in step_lower for word in ["time", "hours", "days", "weeks"]):
            requirements.append("Time commitment")
        if any(word in step_lower for word in ["skill", "knowledge", "experience"]):
            requirements.append("Specific expertise")
        if any(word in step_lower for word in ["legal", "lawyer", "attorney"]):
            requirements.append("Legal assistance")
        if any(word in step_lower for word in ["permit", "license", "approval"]):
            requirements.append("Official authorization")

        return requirements or ["Basic planning"]

    def _identify_potential_issues(self, step: str, goal: str) -> List[str]:
        """Identify potential problems with a step"""
        issues = []
        step_lower = step.lower()

        # Check for common issues
        if len(step.split()) < 4:
            issues.append("Step may be too vague")
        if "somehow" in step_lower or "maybe" in step_lower:
            issues.append("Approach unclear")
        if any(word in step_lower for word in ["expensive", "costly", "cheap"]):
            issues.append("Cost considerations needed")
        if any(word in step_lower for word in ["difficult", "hard", "challenging"]):
            issues.append("Complexity may be underestimated")
        if any(word in step_lower for word in ["quickly", "fast", "immediate"]):
            issues.append("Timeline may be unrealistic")

        return issues

    def _suggest_step_clarifications(self, step: str) -> List[str]:
        """Suggest clarifications for a step"""
        clarifications = []
        step_lower = step.lower()

        # Suggest specific clarifications based on content
        if any(word in step_lower for word in ["research", "find"]):
            clarifications.append("What specific information are you looking for?")
        if any(word in step_lower for word in ["contact", "reach out"]):
            clarifications.append("Who specifically will you contact?")
        if any(word in step_lower for word in ["create", "build", "develop"]):
            clarifications.append("What tools or resources will you use?")
        if "time" not in step_lower and "when" not in step_lower:
            clarifications.append("What's the timeline for this step?")
        if any(word in step_lower for word in ["money", "funding", "cost"]):
            clarifications.append("What's the estimated budget needed?")

        # Generic clarifications for vague steps
        if len(step.split()) < 5:
            clarifications.append("Could you provide more specific details?")

        return clarifications

    def _determine_step_dependencies(
        self, index: int, step: str, all_steps: List[str]
    ) -> List[int]:
        """Determine which previous steps this step depends on"""
        dependencies = []
        step_lower = step.lower()

        # Look for explicit dependency keywords
        dependency_keywords = ["after", "once", "when", "following", "based on", "using"]
        if any(keyword in step_lower for keyword in dependency_keywords):
            # For now, assume dependency on immediately previous step
            if index > 0:
                dependencies.append(index - 1)

        # Check for content-based dependencies
        for i, prev_step in enumerate(all_steps[:index]):
            prev_step_lower = prev_step.lower()

            # Look for related concepts
            if any(
                word in step_lower and word in prev_step_lower
                for word in ["business", "plan", "funding", "research", "contact"]
                if len(word) > 4
            ):
                dependencies.append(i)

        # Default dependency: each step depends on the previous one
        if not dependencies and index > 0:
            dependencies.append(index - 1)

        return dependencies

    def _calculate_overall_feasibility(self, step_analyses: List[PlanStepAnalysis]) -> float:
        """Calculate overall plan feasibility from step analyses"""
        if not step_analyses:
            return 0.0

        # Weight feasibility by step importance (earlier steps are more critical)
        total_weighted_feasibility = 0.0
        total_weight = 0.0

        for i, analysis in enumerate(step_analyses):
            # Earlier steps get higher weight
            weight = 1.0 / (1 + i * 0.1)
            total_weighted_feasibility += analysis.feasibility_score * weight
            total_weight += weight

        return total_weighted_feasibility / total_weight if total_weight > 0 else 0.0

    async def _identify_missing_steps(
        self, plan: MultiStepPlan, step_analyses: List[PlanStepAnalysis]
    ) -> List[str]:
        """Identify important steps that might be missing from the plan"""
        missing_steps = []
        goal_lower = plan.goal.lower()
        all_steps_text = " ".join(plan.steps).lower()

        # Common missing steps by goal type
        if "business" in goal_lower or "startup" in goal_lower:
            if "market research" not in all_steps_text:
                missing_steps.append("Conduct market research")
            if "business plan" not in all_steps_text:
                missing_steps.append("Create detailed business plan")
            if "legal" not in all_steps_text and "register" not in all_steps_text:
                missing_steps.append("Handle legal registration")

        if "invest" in goal_lower or "financial" in goal_lower:
            if "risk" not in all_steps_text:
                missing_steps.append("Assess risk tolerance")
            if "diversif" not in all_steps_text:
                missing_steps.append("Plan for diversification")

        if "career" in goal_lower or "job" in goal_lower:
            if "resume" not in all_steps_text and "cv" not in all_steps_text:
                missing_steps.append("Update resume/CV")
            if "network" not in all_steps_text:
                missing_steps.append("Build professional network")

        # Generic missing steps
        if "timeline" not in all_steps_text and "schedule" not in all_steps_text:
            missing_steps.append("Create detailed timeline")
        if "budget" not in all_steps_text and "cost" not in all_steps_text:
            missing_steps.append("Develop budget plan")

        return missing_steps

    def _generate_clarification_questions(
        self, plan: MultiStepPlan, step_analyses: List[PlanStepAnalysis], missing_steps: List[str]
    ) -> List[str]:
        """Generate questions to clarify the plan"""
        questions = []

        # Questions about overall plan
        questions.append(f"What's your target timeline for achieving '{plan.goal}'?")
        questions.append("What resources (time, money, skills) do you have available?")

        # Questions about specific steps with low clarity
        for analysis in step_analyses:
            if analysis.clarity_score < 0.6:
                for clarification in analysis.suggested_clarifications:
                    questions.append(f"Step {analysis.step_index + 1}: {clarification}")

        # Questions about missing steps
        if missing_steps:
            questions.append(
                f"Have you considered these additional steps: {', '.join(missing_steps[:3])}?"
            )

        # Questions about feasibility concerns
        low_feasibility_steps = [a for a in step_analyses if a.feasibility_score < 0.6]
        if low_feasibility_steps:
            questions.append(
                "Some steps may be challenging. Do you have experience with similar tasks?"
            )

        return questions[:8]  # Limit to avoid overwhelming

    def _generate_recommendations(
        self,
        plan: MultiStepPlan,
        step_analyses: List[PlanStepAnalysis],
        missing_steps: List[str],
        overall_feasibility: float,
    ) -> List[str]:
        """Generate recommendations for improving the plan"""
        recommendations = []

        # Overall plan recommendations
        if overall_feasibility < 0.6:
            recommendations.append(
                "Consider breaking down complex steps into smaller, more manageable tasks"
            )

        if len(plan.steps) < 3:
            recommendations.append("Your plan might benefit from more detailed steps")
        elif len(plan.steps) > 10:
            recommendations.append("Consider grouping related steps to simplify your plan")

        # Step-specific recommendations
        vague_steps = [a for a in step_analyses if a.clarity_score < 0.5]
        if vague_steps:
            recommendations.append(
                f"Steps {[a.step_index + 1 for a in vague_steps]} need more specific details"
            )

        # Missing steps recommendations
        if missing_steps:
            recommendations.append(f"Consider adding: {', '.join(missing_steps[:2])}")

        # Dependency recommendations
        complex_dependencies = any(len(a.dependencies) > 2 for a in step_analyses)
        if complex_dependencies:
            recommendations.append("Review step dependencies to optimize the sequence")

        return recommendations

    def _suggest_reordering(
        self, plan: MultiStepPlan, step_analyses: List[PlanStepAnalysis]
    ) -> Optional[List[int]]:
        """Suggest reordering steps if needed"""
        # For now, keep original order unless obvious issues
        # This could be enhanced with more sophisticated dependency analysis
        return None
