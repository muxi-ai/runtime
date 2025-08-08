"""
Intelligent clarification and multi-turn conversation management for MUXI.

This module provides intelligent handling of incomplete requests that require
natural clarifying questions to gather missing information. This applies to both
external tool calls and internal agent reasoning.

Key Components:
- InformationAnalyzer: Analyzes requests and detects missing information
- ClarificationManager: Manages multi-turn clarification requests
- ClarificationQuestionGenerator: Generates natural language questions
- ContextualParameterEnricher: Enriches parameters from user context
- ClarificationResponseParser: Parses user responses to extract structured data
- InformationRequirements: Standardized requirement definitions

Proactive Clarification
- ProactiveClarificationIntentDetector: Detects explicit turn-taking requests
- ClarificationModeManager: Manages proactive questioning sessions
- PlanAnalyzer: Analyzes multi-step user plans

Planning Workflow Detection & Continuity
- PlanningWorkflowDetector: Detects implicit planning workflows
- WorkflowSynthesizer: Synthesizes tool results into decision insights
- PlanningContinuationManager: Manages planning workflow sessions

Usage:
    from muxi.formation.clarification import (
        InformationAnalyzer,
        ClarificationManager,
        ClarificationQuestionGenerator
    )

    # Initialize components
    analyzer = InformationAnalyzer(model=llm_model)
    manager = ClarificationManager(overlord=overlord)
    generator = ClarificationQuestionGenerator(model=llm_model)

    # Analyze request for missing information
    analysis = await analyzer.analyze_request(
        user_message="Book me a restaurant",
        intent="restaurant_booking",
        available_tools=["book_restaurant"],
        user_context=user_context
    )

    # Start clarification if needed
    if analysis.missing_info:
        request = await manager.start_clarification(
            user_id=user_id,
            agent_id=agent_id,
            request_type=RequestType.TOOL_CALL,
            intent="restaurant_booking",
            tool_name="book_restaurant"
        )
"""

from ...datatypes.clarification import (
    # Core data types
    ClarificationRequest,
    ClarificationResult,
    ClarificationResultStatus,
    ClarificationQuestion,
    ClarificationConfig,
    ToolCall,
    ToolCallResult,
    # Analysis types
    InformationAnalysis,
    ToolInformationAnalysis,
    ReasoningInformationAnalysis,
    ContextAnalysis,
    # Enums
    ClarificationStatus,
    RequestType,
    QuestionStyle,
    ClarificationMode,
    ProactiveRequestType,
    # Proactive clarification types
    ProactiveRequest,
    MultiStepPlan,
    PlanStepAnalysis,
    PlanAnalysis,
    GoalContext,
    ClarificationSession,
    # Planning workflow types
    PlanningWorkflowType,
    WorkflowState,
    PlanningWorkflowRequest,
    ToolExecutionResult,
    WorkflowSynthesis,
    PlanningWorkflowSession,
    PlanningOption,
    # Utility types
    ParameterMapping,
    # Exceptions
    ClarificationError,
    InformationAnalysisError,
    QuestionGenerationError,
    ParameterExtractionError,
    ContextEnrichmentError,
)

# Core components
from .analyzer import InformationAnalyzer
from .manager import ClarificationManager
from .generator import ClarificationQuestionGenerator
from .enricher import ContextualParameterEnricher
from .parser import ClarificationResponseParser
from .requirements import InformationRequirements
from .tool_processor import EnhancedToolProcessor
from .context import ClarificationContext

# Proactive clarification components
from .proactive_detector import ProactiveClarificationIntentDetector
from .mode_manager import ClarificationModeManager
from .plan_analyzer import PlanAnalyzer

# Planning workflow components
from .planning_workflow_detector import PlanningWorkflowDetector
from .workflow_synthesizer import WorkflowSynthesizer
from .planning_continuation_manager import PlanningContinuationManager

# Public API
__all__ = [
    # Core classes
    "InformationAnalyzer",
    "ClarificationManager",
    "ClarificationQuestionGenerator",
    "ContextualParameterEnricher",
    "ClarificationResponseParser",
    "InformationRequirements",
    "EnhancedToolProcessor",
    "ClarificationContext",
    # Proactive Clarification
    "ProactiveClarificationIntentDetector",
    "ClarificationModeManager",
    "PlanAnalyzer",
    # Planning Workflow
    "PlanningWorkflowDetector",
    "WorkflowSynthesizer",
    "PlanningContinuationManager",
    # Data types
    "ClarificationRequest",
    "ClarificationResult",
    "ClarificationResultStatus",
    "ClarificationQuestion",
    "ClarificationConfig",
    "ToolCall",
    "ToolCallResult",
    # Analysis types
    "InformationAnalysis",
    "ToolInformationAnalysis",
    "ReasoningInformationAnalysis",
    "ContextAnalysis",
    # Enums
    "ClarificationStatus",
    "RequestType",
    "QuestionStyle",
    "ClarificationMode",
    "ProactiveRequestType",
    # Proactive clarification types
    "ProactiveRequest",
    "MultiStepPlan",
    "PlanStepAnalysis",
    "PlanAnalysis",
    "GoalContext",
    "ClarificationSession",
    # Planning workflow types
    "PlanningWorkflowType",
    "WorkflowState",
    "PlanningWorkflowRequest",
    "ToolExecutionResult",
    "WorkflowSynthesis",
    "PlanningWorkflowSession",
    "PlanningOption",
    # Utility types
    "ParameterMapping",
    # Exceptions
    "ClarificationError",
    "InformationAnalysisError",
    "QuestionGenerationError",
    "ParameterExtractionError",
    "ContextEnrichmentError",
]


def create_clarification_system(overlord, model=None):
    """
    Convenience function to create a complete clarification system

    Args:
        overlord: The overlord instance for coordination
        model: Optional LLM model for advanced features

    Returns:
        Dictionary containing all clarification components
    """
    return {
        "analyzer": InformationAnalyzer(model=model),
        "manager": ClarificationManager(overlord=overlord),
        "generator": ClarificationQuestionGenerator(model=model),
        "enricher": ContextualParameterEnricher(overlord=overlord),
        "parser": ClarificationResponseParser(model=model),
        "requirements": InformationRequirements(),
        "tool_processor": EnhancedToolProcessor(
            agent=None,  # Will be set later when agents are loaded
            clarification_analyzer=InformationAnalyzer(model=model),
            clarification_enricher=ContextualParameterEnricher(overlord=overlord),
        ),
        "proactive_detector": ProactiveClarificationIntentDetector(model=model),
        "mode_manager": ClarificationModeManager(overlord=overlord),
        "plan_analyzer": PlanAnalyzer(model=model),
        "planning_detector": PlanningWorkflowDetector(model=model),
        "workflow_synthesizer": WorkflowSynthesizer(model=model),
        "planning_manager": PlanningContinuationManager(),
    }
