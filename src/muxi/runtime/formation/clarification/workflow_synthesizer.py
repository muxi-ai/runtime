"""
Workflow Synthesizer for Phase 4B

Synthesizes tool execution results into decision-relevant insights for planning workflows.
Converts raw data into structured options, trade-offs, and recommendations.
"""

import json
from typing import Any, Dict, List

from .datatypes import (
    ToolExecutionResult,
    WorkflowSynthesis,
    PlanningWorkflowType,
    PlanningWorkflowRequest,
)


class WorkflowSynthesizer:
    """
    Synthesizes tool execution results into planning insights.

    Takes raw tool data and creates:
    - Key insights and takeaways
    - Structured options for decision-making
    - Trade-offs and recommendations
    - Follow-up questions for planning continuation
    """

    def __init__(self, model=None):
        """
        Initialize workflow synthesizer.

        Args:
            model: AI model for intelligent synthesis (optional)
        """
        self.model = model
        self._setup_synthesis_rules()

    def _setup_synthesis_rules(self):
        """Set up rules for synthesizing different types of tool results"""

        # Synthesis rules for different workflow types
        self.synthesis_rules = {
            PlanningWorkflowType.TRAVEL_PLANNING: {
                "key_factors": ["cost", "weather", "availability", "duration", "convenience"],
                "comparison_dimensions": ["price", "timing", "quality", "location"],
                "decision_criteria": ["budget", "time preferences", "weather preferences"],
                "common_trade_offs": [
                    "cost vs convenience",
                    "weather vs price",
                    "timing vs availability",
                ],
            },
            PlanningWorkflowType.INVESTMENT_PLANNING: {
                "key_factors": ["returns", "risk", "volatility", "market trends", "timing"],
                "comparison_dimensions": ["ROI", "risk level", "timeframe", "liquidity"],
                "decision_criteria": ["risk tolerance", "investment timeline", "target returns"],
                "common_trade_offs": [
                    "risk vs returns",
                    "liquidity vs growth",
                    "diversification vs concentration",
                ],
            },
            PlanningWorkflowType.PRODUCT_SELECTION: {
                "key_factors": ["price", "features", "quality", "reviews", "warranty"],
                "comparison_dimensions": ["cost", "performance", "reliability", "support"],
                "decision_criteria": ["budget", "feature requirements", "brand preferences"],
                "common_trade_offs": [
                    "price vs features",
                    "quality vs cost",
                    "new vs proven technology",
                ],
            },
            PlanningWorkflowType.BUSINESS_PLANNING: {
                "key_factors": ["market size", "competition", "costs", "regulations", "timing"],
                "comparison_dimensions": ["opportunity", "barriers", "resources", "timing"],
                "decision_criteria": ["capital", "expertise", "market conditions"],
                "common_trade_offs": [
                    "growth vs risk",
                    "market size vs competition",
                    "speed vs thoroughness",
                ],
            },
            PlanningWorkflowType.EVENT_PLANNING: {
                "key_factors": ["venue", "catering", "cost", "availability", "capacity"],
                "comparison_dimensions": ["price", "location", "amenities", "timing"],
                "decision_criteria": ["budget", "guest count", "date preferences"],
                "common_trade_offs": [
                    "cost vs quality",
                    "location vs price",
                    "date vs availability",
                ],
            },
            PlanningWorkflowType.GENERAL_PLANNING: {
                "key_factors": ["cost", "time", "quality", "risk", "convenience"],
                "comparison_dimensions": ["value", "effort", "outcome", "timing"],
                "decision_criteria": ["priorities", "constraints", "preferences"],
                "common_trade_offs": ["cost vs quality", "speed vs thoroughness", "risk vs reward"],
            },
        }

    async def synthesize(
        self, workflow_request: PlanningWorkflowRequest, tool_results: List[ToolExecutionResult]
    ) -> WorkflowSynthesis:
        """
        Synthesize tool results into planning insights.

        Args:
            workflow_request: Original planning workflow request
            tool_results: Results from executed tools

        Returns:
            WorkflowSynthesis with insights, options, and recommendations
        """

        if not tool_results:
            return self._create_empty_synthesis(workflow_request)

        # Use AI synthesis if model available, otherwise rule-based
        if self.model:
            synthesis = await self._synthesize_with_ai(workflow_request, tool_results)
        else:
            synthesis = self._synthesize_with_rules(workflow_request, tool_results)

        # Enhance with structured options
        synthesis.options = self._create_planning_options(workflow_request, tool_results, synthesis)

        return synthesis

    async def _synthesize_with_ai(
        self, workflow_request: PlanningWorkflowRequest, tool_results: List[ToolExecutionResult]
    ) -> WorkflowSynthesis:
        """Use AI model for intelligent synthesis"""

        # Prepare tool results summary
        results_summary = self._format_tool_results_for_ai(tool_results)

        prompt = f"""
        Analyze these tool results to help a user with their planning decision.

        Planning Goal: {workflow_request.planning_goal}
        Workflow Type: {workflow_request.workflow_type.value}

        Tool Results:
        {results_summary}

        Provide a JSON synthesis with:
        {{
            "key_insights": ["List of 3-5 main takeaways from the data"],
            "trade_offs": ["List of key trade-offs the user should consider"],
            "recommendations": ["List of 2-3 specific recommendations based on data"],
            "follow_up_questions": ["List of 2-3 questions to help user decide"],
            "confidence_score": 0.0-1.0
        }}

        Focus on actionable insights that help with decision-making.
        Be specific and reference the actual data provided.
        """

        try:
            response = await self.model.generate(prompt, temperature=0.3, max_tokens=500)
            result = json.loads(response.strip())

            return WorkflowSynthesis(
                planning_goal=workflow_request.planning_goal,
                tool_results=tool_results,
                key_insights=result.get("key_insights", []),
                options=[],  # Will be filled separately
                trade_offs=result.get("trade_offs", []),
                recommendations=result.get("recommendations", []),
                follow_up_questions=result.get("follow_up_questions", []),
                confidence_score=result.get("confidence_score", 0.7),
            )

        except Exception as e:
            #  Warning - TODO: add observability
            _ = e  # remove this after implementing observability
            return self._synthesize_with_rules(workflow_request, tool_results)

    def _synthesize_with_rules(
        self, workflow_request: PlanningWorkflowRequest, tool_results: List[ToolExecutionResult]
    ) -> WorkflowSynthesis:
        """Rule-based synthesis when AI model not available"""

        workflow_type = workflow_request.workflow_type
        rules = self.synthesis_rules.get(
            workflow_type, self.synthesis_rules[PlanningWorkflowType.GENERAL_PLANNING]
        )

        # Extract key insights from tool results
        key_insights = self._extract_key_insights(tool_results, rules["key_factors"])

        # Identify trade-offs
        trade_offs = self._identify_trade_offs(tool_results, rules["common_trade_offs"])

        # Generate recommendations
        recommendations = self._generate_recommendations(tool_results, workflow_type)

        # Create follow-up questions
        follow_up_questions = self._generate_follow_up_questions(
            workflow_request, tool_results, rules["decision_criteria"]
        )

        return WorkflowSynthesis(
            planning_goal=workflow_request.planning_goal,
            tool_results=tool_results,
            key_insights=key_insights,
            options=[],  # Will be filled separately
            trade_offs=trade_offs,
            recommendations=recommendations,
            follow_up_questions=follow_up_questions,
            confidence_score=0.8,
        )

    def _extract_key_insights(
        self, tool_results: List[ToolExecutionResult], key_factors: List[str]
    ) -> List[str]:
        """Extract key insights from tool results"""
        insights = []

        for result in tool_results:
            if result.success and result.result:
                # Extract relevant information based on key factors
                result_text = str(result.result).lower()

                for factor in key_factors:
                    if factor in result_text:
                        insight = f"{result.tool_name} shows relevant {factor} information"
                        if insight not in insights:
                            insights.append(insight)

        # Add general insights about data availability
        successful_tools = [r for r in tool_results if r.success]
        if len(successful_tools) > 1:
            insights.append(f"Gathered data from {len(successful_tools)} sources for comparison")

        failed_tools = [r for r in tool_results if not r.success]
        if failed_tools:
            insights.append(f"Could not retrieve data from {len(failed_tools)} sources")

        return insights[:5]  # Limit to 5 insights

    def _identify_trade_offs(
        self, tool_results: List[ToolExecutionResult], common_trade_offs: List[str]
    ) -> List[str]:
        """Identify trade-offs from tool results"""
        trade_offs = []

        # Look for conflicting or competing factors in results
        if len(tool_results) >= 2:
            trade_offs.extend(common_trade_offs[:3])  # Use predefined trade-offs

        # Add specific trade-offs based on result patterns
        has_cost_data = any(
            "cost" in str(r.result).lower() or "price" in str(r.result).lower()
            for r in tool_results
            if r.success
        )
        has_quality_data = any(
            "quality" in str(r.result).lower() or "rating" in str(r.result).lower()
            for r in tool_results
            if r.success
        )

        if has_cost_data and has_quality_data:
            trade_offs.append("Consider balancing cost against quality requirements")

        return trade_offs[:4]  # Limit to 4 trade-offs

    def _generate_recommendations(
        self, tool_results: List[ToolExecutionResult], workflow_type: PlanningWorkflowType
    ) -> List[str]:
        """Generate recommendations based on tool results"""
        recommendations = []

        successful_results = [r for r in tool_results if r.success]

        if not successful_results:
            recommendations.append("Consider alternative information sources for your decision")
            return recommendations

        # General recommendations based on workflow type
        if workflow_type == PlanningWorkflowType.TRAVEL_PLANNING:
            recommendations.append("Compare the weather and pricing data to find optimal timing")
            recommendations.append("Consider booking flexibility vs cost savings")

        elif workflow_type == PlanningWorkflowType.INVESTMENT_PLANNING:
            recommendations.append("Review risk-return profiles before deciding")
            recommendations.append("Consider diversification across different options")

        elif workflow_type == PlanningWorkflowType.PRODUCT_SELECTION:
            recommendations.append("Compare feature sets against your specific needs")
            recommendations.append("Factor in total cost of ownership beyond initial price")

        else:
            recommendations.append("Prioritize your most important criteria")
            recommendations.append("Consider both short-term and long-term implications")

        return recommendations[:3]  # Limit to 3 recommendations

    def _generate_follow_up_questions(
        self,
        workflow_request: PlanningWorkflowRequest,
        tool_results: List[ToolExecutionResult],
        decision_criteria: List[str],
    ) -> List[str]:
        """Generate follow-up questions for planning continuation"""

        questions = []

        # Questions based on available data
        if tool_results:
            questions.append("Which factors are most important to you in making this decision?")

            if len(tool_results) > 1:
                questions.append("Would you like me to help you compare these options in detail?")

        # Questions based on decision criteria
        for criterion in decision_criteria[:2]:
            questions.append(f"What are your preferences regarding {criterion}?")

        # Workflow-specific questions
        workflow_type = workflow_request.workflow_type
        if workflow_type == PlanningWorkflowType.TRAVEL_PLANNING:
            questions.append("Do you have flexible dates or preferred timing?")

        elif workflow_type == PlanningWorkflowType.INVESTMENT_PLANNING:
            questions.append("What's your risk tolerance for this investment?")

        elif workflow_type == PlanningWorkflowType.PRODUCT_SELECTION:
            questions.append("Are there specific features that are must-haves vs nice-to-haves?")

        return questions[:3]  # Limit to 3 questions

    def _create_planning_options(
        self,
        workflow_request: PlanningWorkflowRequest,
        tool_results: List[ToolExecutionResult],
        synthesis: WorkflowSynthesis,
    ) -> List[Dict[str, Any]]:
        """Create structured planning options from tool results"""

        options = []

        # Create options from successful tool results
        for i, result in enumerate([r for r in tool_results if r.success]):
            option = {
                "id": f"option_{i+1}",
                "title": f"Option based on {result.tool_name}",
                "description": result.planning_relevance or str(result.result)[:200],
                "source_tool": result.tool_name,
                "data": result.result,
                "confidence": 0.8 if result.success else 0.3,
            }
            options.append(option)

        return options[:5]  # Limit to 5 options

    def _format_tool_results_for_ai(self, tool_results: List[ToolExecutionResult]) -> str:
        """Format tool results for AI consumption"""

        formatted_results = []

        for result in tool_results:
            status = "SUCCESS" if result.success else "FAILED"
            result_text = str(result.result)[:300] if result.result else "No data"

            formatted_results.append(
                f"Tool: {result.tool_name}\n"
                f"Status: {status}\n"
                f"Result: {result_text}\n"
                f"Planning Context: {result.planning_relevance}\n"
            )

        return "\n".join(formatted_results)

    def _create_empty_synthesis(
        self, workflow_request: PlanningWorkflowRequest
    ) -> WorkflowSynthesis:
        """Create empty synthesis when no tool results available"""

        return WorkflowSynthesis(
            planning_goal=workflow_request.planning_goal,
            tool_results=[],
            key_insights=["No data was successfully retrieved"],
            options=[],
            trade_offs=["Unable to analyze trade-offs without data"],
            recommendations=["Consider alternative approaches to gather information"],
            follow_up_questions=["How would you like to proceed without this data?"],
            confidence_score=0.1,
        )
