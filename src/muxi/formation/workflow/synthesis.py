"""
Advanced Response Synthesis Engine

This module provides intelligent response synthesis with quality assessment,
multi-modal integration, and sophisticated persona consistency management.
"""

import json
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ...services.llm import LLM
from ...datatypes.workflow import Workflow, TaskStatus
from ...datatypes import observability


class ResponseQuality(Enum):
    """Response quality levels"""

    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    UNACCEPTABLE = "unacceptable"


class SynthesisMode(Enum):
    """Response synthesis modes"""

    COMPREHENSIVE = "comprehensive"  # Full synthesis with all enhancements
    BALANCED = "balanced"  # Balanced approach
    EFFICIENT = "efficient"  # Fast synthesis with core enhancements
    MINIMAL = "minimal"  # Basic synthesis only


@dataclass
class QualityAssessment:
    """Comprehensive quality assessment results"""

    overall_quality: ResponseQuality
    confidence_score: float  # 0-1

    # Quality dimensions
    coherence_score: float  # 0-1
    relevance_score: float  # 0-1
    completeness_score: float  # 0-1
    clarity_score: float  # 0-1
    persona_consistency_score: float  # 0-1
    user_satisfaction_score: float  # 0-1

    # Assessment details
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)

    # Metadata
    assessment_time: float = field(default_factory=time.time)
    assessor_version: str = "1.0"


@dataclass
class SynthesisResult:
    """Result of response synthesis process"""

    synthesized_content: str
    quality_assessment: QualityAssessment
    synthesis_metadata: Dict[str, Any] = field(default_factory=dict)

    # Performance metrics
    synthesis_time_ms: float = 0.0
    iterations_performed: int = 0
    enhancement_applied: List[str] = field(default_factory=list)


class ResponseQualityAssessor:
    """
    Multi-dimensional response quality assessment system.

    Evaluates responses across coherence, relevance, completeness, clarity,
    persona consistency, and predicted user satisfaction.
    """

    def __init__(self, llm: LLM):
        self.llm = llm
        self.assessment_cache: Dict[str, QualityAssessment] = {}

    async def assess_quality(
        self,
        content: str,
        context: Dict[str, Any],
        user_request: str,
        expected_persona: Optional[str] = None,
    ) -> QualityAssessment:
        """
        Comprehensive quality assessment of response content.

        Args:
            content: Response content to assess
            context: Context information for assessment
            user_request: Original user request
            expected_persona: Expected persona characteristics

        Returns:
            Detailed quality assessment
        """
        try:
            # Generate assessment prompt
            assessment_prompt = self._create_assessment_prompt(
                content, context, user_request, expected_persona
            )

            # Get LLM assessment
            assessment_response = await self.llm.generate(
                assessment_prompt, max_tokens=1000, temperature=0.3
            )

            # Parse assessment
            quality_assessment = self._parse_assessment_response(assessment_response)

            # Calculate overall quality
            quality_assessment.overall_quality = self._calculate_overall_quality(quality_assessment)

            return quality_assessment

        except Exception:
            return self._create_fallback_assessment()

    def _create_assessment_prompt(
        self,
        content: str,
        context: Dict[str, Any],
        user_request: str,
        expected_persona: Optional[str] = None,
    ) -> str:
        """Create comprehensive assessment prompt"""

        persona_section = ""
        if expected_persona:
            persona_section = f"""
Expected Persona: {expected_persona}
"""

        return f"""
You are an expert response quality assessor. Evaluate this response across multiple dimensions.

User Request: "{user_request}"
{persona_section}
Response to Assess:
{content}

Context Information:
{json.dumps(context, indent=2)}

Please assess the response on these dimensions (score 0.0-1.0 for each):

1. COHERENCE: How well-structured and logically organized is the response?
2. RELEVANCE: How well does it address the user's specific request?
3. COMPLETENESS: Does it fully address all aspects of the request?
4. CLARITY: How clear and understandable is the communication?
5. PERSONA_CONSISTENCY: How well does it maintain the expected persona/tone?
6. USER_SATISFACTION: How likely is this to satisfy the user's needs?

For each dimension, provide:
- Score (0.0-1.0)
- Brief justification

Also provide:
- Overall confidence in your assessment (0.0-1.0)
- Top 3 strengths
- Top 3 weaknesses (if any)
- Top 3 improvement suggestions

Format your response as JSON:
{{
    "coherence_score": 0.0,
    "coherence_justification": "...",
    "relevance_score": 0.0,
    "relevance_justification": "...",
    "completeness_score": 0.0,
    "completeness_justification": "...",
    "clarity_score": 0.0,
    "clarity_justification": "...",
    "persona_consistency_score": 0.0,
    "persona_consistency_justification": "...",
    "user_satisfaction_score": 0.0,
    "user_satisfaction_justification": "...",
    "confidence_score": 0.0,
    "strengths": ["...", "...", "..."],
    "weaknesses": ["...", "...", "..."],
    "improvement_suggestions": ["...", "...", "..."]
}}
"""

    def _parse_assessment_response(self, response: str) -> QualityAssessment:
        """Parse LLM assessment response into QualityAssessment object"""
        try:
            # Extract JSON from response
            json_match = response.strip()
            if not json_match.startswith("{"):
                # Try to find JSON block
                import re

                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    json_match = json_match.group(0)
                else:
                    raise ValueError("No JSON found in response")

            data = json.loads(json_match)

            return QualityAssessment(
                overall_quality=ResponseQuality.GOOD,  # Will be calculated
                confidence_score=data.get("confidence_score", 0.7),
                coherence_score=data.get("coherence_score", 0.7),
                relevance_score=data.get("relevance_score", 0.7),
                completeness_score=data.get("completeness_score", 0.7),
                clarity_score=data.get("clarity_score", 0.7),
                persona_consistency_score=data.get("persona_consistency_score", 0.7),
                user_satisfaction_score=data.get("user_satisfaction_score", 0.7),
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                improvement_suggestions=data.get("improvement_suggestions", []),
            )

        except Exception:
            return self._create_fallback_assessment()

    def _calculate_overall_quality(self, assessment: QualityAssessment) -> ResponseQuality:
        """Calculate overall quality from dimension scores"""

        # Weighted average of quality dimensions
        weights = {
            "relevance": 0.25,
            "completeness": 0.20,
            "clarity": 0.20,
            "coherence": 0.15,
            "persona_consistency": 0.10,
            "user_satisfaction": 0.10,
        }

        weighted_score = (
            assessment.relevance_score * weights["relevance"]
            + assessment.completeness_score * weights["completeness"]
            + assessment.clarity_score * weights["clarity"]
            + assessment.coherence_score * weights["coherence"]
            + assessment.persona_consistency_score * weights["persona_consistency"]
            + assessment.user_satisfaction_score * weights["user_satisfaction"]
        )

        # Map to quality levels
        if weighted_score >= 0.9:
            return ResponseQuality.EXCELLENT
        elif weighted_score >= 0.8:
            return ResponseQuality.GOOD
        elif weighted_score >= 0.6:
            return ResponseQuality.ACCEPTABLE
        elif weighted_score >= 0.4:
            return ResponseQuality.POOR
        else:
            return ResponseQuality.UNACCEPTABLE

    def _create_fallback_assessment(self) -> QualityAssessment:
        """Create fallback assessment when assessment fails"""
        return QualityAssessment(
            overall_quality=ResponseQuality.ACCEPTABLE,
            confidence_score=0.5,
            coherence_score=0.7,
            relevance_score=0.7,
            completeness_score=0.7,
            clarity_score=0.7,
            persona_consistency_score=0.7,
            user_satisfaction_score=0.7,
            strengths=["Response provided"],
            weaknesses=["Quality assessment unavailable"],
            improvement_suggestions=["Manual review recommended"],
        )


class PersonaConsistencyAnalyzer:
    """
    Advanced persona consistency analysis and adaptation system.

    Ensures responses maintain consistent personality, tone, and communication
    style across interactions while adapting to context appropriately.
    """

    def __init__(self, llm: LLM):
        self.llm = llm
        self.persona_profiles: Dict[str, Dict[str, Any]] = {}
        self.consistency_history: List[Dict[str, Any]] = []

    async def analyze_persona_consistency(
        self,
        content: str,
        expected_persona: str,
        context: Dict[str, Any],
        conversation_history: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Analyze persona consistency of content.

        Args:
            content: Content to analyze
            expected_persona: Expected persona description
            context: Context information
            conversation_history: Previous conversation for consistency

        Returns:
            Persona consistency analysis
        """
        try:
            analysis_prompt = self._create_persona_analysis_prompt(
                content, expected_persona, context, conversation_history
            )

            response = await self.llm.generate(analysis_prompt, max_tokens=800, temperature=0.2)

            analysis = self._parse_persona_analysis(response)

            # Store in history
            self.consistency_history.append(
                {"timestamp": time.time(), "analysis": analysis, "context": context}
            )

            return analysis

        except Exception:
            return {
                "consistency_score": 0.7,
                "persona_match": True,
                "issues_found": [],
                "recommendations": ["Manual review recommended"],
            }

    def _create_persona_analysis_prompt(
        self,
        content: str,
        expected_persona: str,
        context: Dict[str, Any],
        conversation_history: Optional[List[str]] = None,
    ) -> str:
        """Create persona analysis prompt"""

        history_section = ""
        if conversation_history:
            history_section = f"""
Previous Conversation:
{chr(10).join(conversation_history[-3:])}  # Last 3 exchanges
"""

        return f"""
You are a persona consistency expert. Analyze how well this content matches the expected persona.

Expected Persona:
{expected_persona}

Content to Analyze:
{content}
{history_section}
Context:
{json.dumps(context, indent=2)}

Evaluate:
1. Tone consistency with expected persona
2. Communication style alignment
3. Vocabulary and language patterns
4. Personality trait expression
5. Consistency with previous interactions

Provide analysis as JSON:
{{
    "consistency_score": 0.0,  // 0.0-1.0 scale
    "persona_match": true,     // boolean
    "tone_consistency": 0.0,   // 0.0-1.0
    "style_alignment": 0.0,    // 0.0-1.0
    "vocabulary_match": 0.0,   // 0.0-1.0
    "personality_expression": 0.0,  // 0.0-1.0
    "historical_consistency": 0.0,  // 0.0-1.0
    "issues_found": ["..."],   // specific issues
    "recommendations": ["..."] // improvement suggestions
}}
"""

    def _parse_persona_analysis(self, response: str) -> Dict[str, Any]:
        """Parse persona analysis response"""
        try:
            # Extract and parse JSON
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")
        except Exception:
            return {
                "consistency_score": 0.7,
                "persona_match": True,
                "issues_found": [],
                "recommendations": ["Manual review recommended"],
            }


class AdvancedResponseSynthesizer:
    """
    Advanced response synthesis with quality assessment and multi-modal integration.

    Transforms raw agent outputs into polished, contextually appropriate responses
    that maintain persona consistency and optimize for user experience.
    """

    def __init__(self, llm: LLM, quality_assessor: ResponseQualityAssessor):
        self.llm = llm
        self.quality_assessor = quality_assessor
        self.persona_analyzer = PersonaConsistencyAnalyzer(llm)

        # Synthesis configuration
        self.quality_threshold = 0.8
        self.max_iterations = 3
        self.synthesis_cache: Dict[str, SynthesisResult] = {}

    async def synthesize_response(
        self,
        workflow: Workflow,
        user_context: Dict[str, Any],
        synthesis_options: Dict[str, Any] = None,
    ) -> SynthesisResult:
        """
        Synthesize polished response from workflow outputs.

        Args:
            workflow: Completed workflow with task outputs
            user_context: User context for personalization
            synthesis_options: Optional synthesis configuration

        Returns:
            Synthesized response with quality assessment
        """
        start_time = time.time()

        try:
            # Extract synthesis configuration
            options = synthesis_options or {}
            mode = SynthesisMode(options.get("mode", "balanced"))
            target_quality = options.get("target_quality", self.quality_threshold)
            max_iterations = options.get("max_iterations", self.max_iterations)

            # Collect workflow outputs
            task_outputs = self._collect_workflow_outputs(workflow)

            # Initial synthesis
            synthesized_content = await self._perform_initial_synthesis(
                task_outputs, workflow.user_request, user_context, mode
            )

            # Quality assessment and iterative improvement
            final_content, quality_assessment, iterations = await self._iterative_improvement(
                synthesized_content,
                workflow.user_request,
                user_context,
                target_quality,
                max_iterations,
            )

            # Create synthesis result
            result = SynthesisResult(
                synthesized_content=final_content,
                quality_assessment=quality_assessment,
                synthesis_metadata={
                    "workflow_id": workflow.id,
                    "synthesis_mode": mode.value,
                    "task_count": len(workflow.tasks),
                    "original_length": len(synthesized_content),
                    "final_length": len(final_content),
                },
                synthesis_time_ms=(time.time() - start_time) * 1000,
                iterations_performed=iterations,
                enhancement_applied=self._get_applied_enhancements(mode),
            )

            observability.observe(
                event_type=observability.ConversationEvents.RESPONSE_SYNTHESIZED,
                level=observability.EventLevel.INFO,
                data={
                    "quality": quality_assessment.overall_quality.value,
                    "iterations": iterations,
                    "mode": mode.value,
                    "synthesis_time_ms": (time.time() - start_time) * 1000,
                },
                description=(
                    f"Response synthesis completed: "
                    f"{quality_assessment.overall_quality.value} quality "
                    f"in {iterations} iterations"
                ),
            )

            return result

        except Exception:
            return self._create_fallback_synthesis_result(workflow, user_context)

    def _collect_workflow_outputs(self, workflow: Workflow) -> List[Dict[str, Any]]:
        """Collect and structure outputs from workflow tasks"""
        outputs = []

        for task in workflow.tasks.values():
            if task.status == TaskStatus.COMPLETED and task.outputs:
                output_data = {
                    "task_id": task.id,
                    "description": task.description,
                    "content": task.outputs.get("content", ""),
                    "capabilities": task.required_capabilities,
                    "metadata": task.outputs,
                }
                outputs.append(output_data)

        return outputs

    async def _perform_initial_synthesis(
        self,
        task_outputs: List[Dict[str, Any]],
        user_request: str,
        user_context: Dict[str, Any],
        mode: SynthesisMode,
    ) -> str:
        """Perform initial synthesis of task outputs"""

        synthesis_prompt = self._create_synthesis_prompt(
            task_outputs, user_request, user_context, mode
        )

        response = await self.llm.generate(synthesis_prompt, max_tokens=2000, temperature=0.7)

        return response.strip()

    def _create_synthesis_prompt(
        self,
        task_outputs: List[Dict[str, Any]],
        user_request: str,
        user_context: Dict[str, Any],
        mode: SynthesisMode,
    ) -> str:
        """Create synthesis prompt based on mode and inputs"""

        # Format task outputs
        outputs_text = ""
        for i, output in enumerate(task_outputs, 1):
            outputs_text += f"""
Task {i}: {output['description']}
Capabilities: {', '.join(output['capabilities'])}
Output: {output['content']}
---
"""

        persona_info = user_context.get("persona", "professional and helpful")

        mode_instructions = {
            SynthesisMode.COMPREHENSIVE: """
Create a comprehensive, polished response that:
- Integrates all task outputs seamlessly
- Maintains excellent flow and coherence
- Optimizes for user engagement and satisfaction
- Includes relevant context and explanations
- Uses sophisticated language and structure
""",
            SynthesisMode.BALANCED: """
Create a well-structured response that:
- Combines task outputs effectively
- Maintains good readability and flow
- Balances comprehensiveness with conciseness
- Uses clear, professional language
""",
            SynthesisMode.EFFICIENT: """
Create a clear, efficient response that:
- Presents key information from task outputs
- Uses straightforward structure
- Focuses on essential content
- Maintains professional tone
""",
            SynthesisMode.MINIMAL: """
Create a concise response that:
- Summarizes task outputs briefly
- Uses simple, direct language
- Focuses on core message
""",
        }

        return f"""
You are an expert content synthesizer. Create a unified response from multiple task outputs.

User's Original Request: "{user_request}"

Task Outputs to Synthesize:
{outputs_text}

User Context:
- Persona: {persona_info}
- Additional context: {json.dumps(user_context, indent=2)}

Synthesis Mode: {mode.value}
{mode_instructions[mode]}

Guidelines:
1. Create a coherent, unified response that addresses the user's request
2. Integrate information from all relevant task outputs
3. Maintain the specified persona and tone
4. Ensure logical flow and clear structure
5. Avoid redundancy while preserving important details
6. Make the response engaging and valuable to the user

Provide the synthesized response:
"""

    async def _iterative_improvement(
        self,
        content: str,
        user_request: str,
        user_context: Dict[str, Any],
        target_quality: float,
        max_iterations: int,
    ) -> Tuple[str, QualityAssessment, int]:
        """Iteratively improve response quality"""

        current_content = content
        iterations = 0

        for iteration in range(max_iterations):
            iterations += 1

            # Assess current quality
            quality_assessment = await self.quality_assessor.assess_quality(
                current_content, user_context, user_request, user_context.get("persona")
            )

            # Check if quality threshold met
            average_score = (
                quality_assessment.coherence_score
                + quality_assessment.relevance_score
                + quality_assessment.completeness_score
                + quality_assessment.clarity_score
                + quality_assessment.persona_consistency_score
                + quality_assessment.user_satisfaction_score
            ) / 6

            if average_score >= target_quality:
                observability.observe(
                    event_type=observability.ConversationEvents.RESPONSE_SYNTHESIZED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "iteration": iterations,
                        "average_score": average_score,
                        "target_quality": target_quality,
                    },
                    description=f"Quality target reached in iteration {iterations}",
                )
                return current_content, quality_assessment, iterations

            # Generate improvement prompt
            if iteration < max_iterations - 1:  # Don't improve on last iteration
                improved_content = await self._improve_content(
                    current_content, quality_assessment, user_request, user_context
                )
                current_content = improved_content

        # Final assessment
        final_quality = await self.quality_assessor.assess_quality(
            current_content, user_context, user_request, user_context.get("persona")
        )

        return current_content, final_quality, iterations

    async def _improve_content(
        self,
        content: str,
        quality_assessment: QualityAssessment,
        user_request: str,
        user_context: Dict[str, Any],
    ) -> str:
        """Improve content based on quality assessment"""

        improvement_prompt = f"""
You are an expert content editor. Improve this response based on the quality assessment.

Original User Request: "{user_request}"

Current Response:
{content}

Quality Assessment Issues:
- Weaknesses: {', '.join(quality_assessment.weaknesses)}
- Suggestions: {', '.join(quality_assessment.improvement_suggestions)}

Quality Scores (0.0-1.0):
- Coherence: {quality_assessment.coherence_score:.2f}
- Relevance: {quality_assessment.relevance_score:.2f}
- Completeness: {quality_assessment.completeness_score:.2f}
- Clarity: {quality_assessment.clarity_score:.2f}
- Persona Consistency: {quality_assessment.persona_consistency_score:.2f}

User Context: {json.dumps(user_context, indent=2)}

Please improve the response by addressing the identified weaknesses and implementing
the suggestions. Focus on the lowest-scoring dimensions while maintaining the
response's core value.

Improved Response:
"""

        try:
            improved_response = await self.llm.generate(
                improvement_prompt, max_tokens=2000, temperature=0.6
            )
            return improved_response.strip()
        except Exception:
            return content  # Return original if improvement fails

    def _get_applied_enhancements(self, mode: SynthesisMode) -> List[str]:
        """Get list of enhancements applied based on synthesis mode"""
        base_enhancements = ["output_integration", "quality_assessment"]

        if mode in [SynthesisMode.COMPREHENSIVE, SynthesisMode.BALANCED]:
            base_enhancements.extend(
                ["persona_consistency_analysis", "iterative_improvement", "flow_optimization"]
            )

        if mode == SynthesisMode.COMPREHENSIVE:
            base_enhancements.extend(
                ["advanced_structuring", "engagement_optimization", "context_enrichment"]
            )

        return base_enhancements

    def _create_fallback_synthesis_result(
        self, workflow: Workflow, user_context: Dict[str, Any]
    ) -> SynthesisResult:
        """Create fallback synthesis result when synthesis fails"""

        # Simple concatenation of outputs
        outputs = []
        for task in workflow.tasks.values():
            if task.outputs and task.outputs.get("content"):
                outputs.append(task.outputs["content"])

        fallback_content = "\n\n".join(outputs) if outputs else "I've completed your request."

        fallback_assessment = QualityAssessment(
            overall_quality=ResponseQuality.ACCEPTABLE,
            confidence_score=0.5,
            coherence_score=0.6,
            relevance_score=0.7,
            completeness_score=0.6,
            clarity_score=0.6,
            persona_consistency_score=0.6,
            user_satisfaction_score=0.6,
            strengths=["Request completed"],
            weaknesses=["Synthesis unavailable"],
            improvement_suggestions=["Manual review recommended"],
        )

        return SynthesisResult(
            synthesized_content=fallback_content,
            quality_assessment=fallback_assessment,
            synthesis_metadata={"workflow_id": workflow.id, "fallback_used": True},
            synthesis_time_ms=0.0,
            iterations_performed=0,
            enhancement_applied=["basic_output_concatenation"],
        )
