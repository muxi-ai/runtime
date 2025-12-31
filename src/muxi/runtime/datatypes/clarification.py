"""
Core data types and classes for the clarification system.

This module defines the fundamental data structures used throughout
the intelligent parameter collection and clarification system.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time
from ..utils.id_generator import generate_nanoid

from .type_definitions import (
    ToolParameters,
    AvailableInformation,
    CollectedInformation,
    Context,
)


class ClarificationStatus(Enum):
    """Status of a clarification request"""

    CLARIFYING = "clarifying"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RequestType(Enum):
    """Type of clarification request"""

    TOOL_CALL = "tool_call"
    REASONING = "reasoning"
    MIXED = "mixed"


class QuestionStyle(Enum):
    """Style of clarification questions"""

    CONVERSATIONAL = "conversational"
    FORMAL = "formal"
    BRIEF = "brief"


class ClarificationMode(Enum):
    """Mode of clarification conversation"""

    REACTIVE = "reactive"  # Traditional: detect missing info and ask
    PROACTIVE_QUESTIONING = "proactive_questioning"  # User requests guided questions
    PLAN_ANALYSIS = "plan_analysis"  # Analyze multi-step user plans
    CONTEXT_BUILDING = "context_building"  # Build comprehensive context before action
    GOAL_ACHIEVEMENT = "goal_achievement"  # Work toward specific information goal


class ProactiveRequestType(Enum):
    """Type of proactive clarification request"""

    GUIDED_QUESTIONING = "guided_questioning"  # "Ask me questions until..."
    PLAN_FEEDBACK = "plan_feedback"  # "I want to do A-B-C, what do you think?"
    CONTEXT_FIRST = "context_first"  # "Understand my situation first"
    STEP_BY_STEP = "step_by_step"  # "Walk me through this"
    COMPREHENSIVE_ADVICE = "comprehensive_advice"  # "Get all info before advising"


class PlanningWorkflowType(Enum):
    """Type of planning workflow detected"""

    TRAVEL_PLANNING = "travel_planning"  # Trip booking with research
    INVESTMENT_PLANNING = "investment_planning"  # Investment decisions with analysis
    BUSINESS_PLANNING = "business_planning"  # Business decisions with research
    PRODUCT_SELECTION = "product_selection"  # Purchase decisions with comparison
    EVENT_PLANNING = "event_planning"  # Event coordination with venue/cost research
    GENERAL_PLANNING = "general_planning"  # Generic planning with information gathering


class WorkflowState(Enum):
    """State of a planning workflow"""

    INFORMATION_GATHERING = "information_gathering"  # Collecting data via tools
    DATA_SYNTHESIS = "data_synthesis"  # Processing and analyzing collected data
    OPTION_PRESENTATION = "option_presentation"  # Presenting choices to user
    DECISION_REFINEMENT = "decision_refinement"  # Helping user refine choices
    PLANNING_COMPLETE = "planning_complete"  # Workflow finished


class ClarificationResultStatus(Enum):
    """Status of a clarification result"""

    COMPLETE = "complete"
    CONTINUE = "continue"
    ERROR = "error"


@dataclass
class ClarificationQuestion:
    """A single clarification question"""

    question_id: str
    question_text: str
    parameter_name: str
    parameter_type: str
    parameter_description: Optional[str] = None
    required: bool = True
    validation_rules: Optional[Dict[str, Any]] = None
    context_hints: Optional[List[str]] = None
    style: QuestionStyle = QuestionStyle.CONVERSATIONAL
    # New fields for proactive questioning
    goal_area: Optional[str] = None  # Which goal area this question targets
    priority: int = 5  # 1-10, higher = more important
    follow_up_questions: List[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """Represents a tool call extracted from model response"""

    name: str
    parameters: ToolParameters
    call_id: Optional[str] = None

    def __post_init__(self):
        if self.call_id is None:
            self.call_id = f"clr_{generate_nanoid()}"


@dataclass
class InformationAnalysis:
    """Result of analyzing information requirements"""

    missing_info: List[str]
    available_info: AvailableInformation
    confidence_scores: Dict[str, float]
    suggestions: List[str]
    can_proceed: bool
    reasoning_context_needed: Optional[str] = None
    is_actionable: bool = True  # New field: whether the request requires action


@dataclass
class ToolInformationAnalysis(InformationAnalysis):
    """Tool-specific information analysis"""

    tool_name: str = ""
    tool_schema: Dict[str, Any] = field(default_factory=dict)
    missing_required_params: List[str] = field(default_factory=list)
    missing_optional_params: List[str] = field(default_factory=list)
    parameter_confidence: Dict[str, float] = field(default_factory=dict)


@dataclass
class ReasoningInformationAnalysis(InformationAnalysis):
    """Reasoning-specific information analysis"""

    intent: str = ""
    context_gaps: List[str] = field(default_factory=list)
    user_background_needed: List[str] = field(default_factory=list)
    complexity_level: str = "moderate"  # "simple", "moderate", "complex"


@dataclass
class ClarificationRequest:
    """Tracks a multi-turn clarification request"""

    # Required fields (no defaults)
    user_id: str
    agent_id: str
    request_type: RequestType

    # Optional fields (with defaults)
    request_id: Optional[str] = None
    tool_name: Optional[str] = None
    intent: str = ""
    provided_info: CollectedInformation = field(default_factory=dict)
    missing_info: List[str] = field(default_factory=list)
    clarification_plan: List[ClarificationQuestion] = field(default_factory=list)
    current_step: int = 0
    context: Context = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: ClarificationStatus = ClarificationStatus.CLARIFYING

    def __post_init__(self):
        if self.request_id is None:
            self.request_id = str(f"req_{generate_nanoid()}")


@dataclass
class ClarificationResult:
    """Result of processing a clarification response"""

    status: ClarificationResultStatus
    complete_params: Optional[Dict[str, Any]] = None
    next_question: Optional[str] = None
    error_message: Optional[str] = None
    confidence: float = 0.0
    extracted_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClarificationResponse:
    """User's response to a clarification request"""

    request_type: str = "credential_required"
    answers: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: Optional[str] = None


@dataclass
class ClarificationConfig:
    """Configuration for the clarification system"""

    enabled: bool = True
    max_questions: Optional[int] = None  # Kept for backward compatibility - None means not explicitly set
    max_rounds: Optional[Dict[str, int]] = None  # New mode-specific configuration
    style: QuestionStyle = QuestionStyle.CONVERSATIONAL
    timeout_seconds: int = 300
    auto_fill_from_context: bool = True
    reasoning_requirements: bool = True


class ClarificationError(Exception):
    """Base exception for clarification system errors"""

    pass


class InformationAnalysisError(ClarificationError):
    """Error during information analysis"""

    pass


class QuestionGenerationError(ClarificationError):
    """Error during question generation"""

    pass


class ParameterExtractionError(ClarificationError):
    """Error during parameter extraction from user response"""

    pass


class ContextEnrichmentError(ClarificationError):
    """Error during context enrichment"""

    pass


@dataclass
class ProactiveRequest:
    """A request for proactive clarification/questioning"""

    request_type: ProactiveRequestType
    goal: str  # What the user wants to achieve
    original_message: str
    completion_criteria: Optional[str] = None  # When to stop asking questions
    max_questions: int = 10
    question_areas: List[str] = field(default_factory=list)  # Areas to focus on
    confidence: float = 0.0


@dataclass
class MultiStepPlan:
    """A multi-step plan submitted by user for analysis"""

    steps: List[str]
    goal: str
    original_message: str
    # step_index -> [dependency_indices]
    step_dependencies: Dict[int, List[int]] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class PlanStepAnalysis:
    """Analysis of a single plan step"""

    step_index: int
    step_text: str
    feasibility_score: float  # 0.0-1.0
    clarity_score: float  # How clear/specific the step is
    requirements: List[str]  # What's needed for this step
    potential_issues: List[str]
    suggested_clarifications: List[str]
    dependencies: List[int]  # Indices of prerequisite steps


@dataclass
class PlanAnalysis:
    """Complete analysis of a multi-step plan"""

    plan: MultiStepPlan
    overall_feasibility: float
    step_analyses: List[PlanStepAnalysis]
    missing_steps: List[str]
    suggested_reordering: Optional[List[int]] = None
    clarification_questions: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class GoalContext:
    """Context for achieving a specific information goal"""

    goal: str
    goal_type: str  # e.g., "investment_advice", "business_planning", "technical_guidance"
    required_info_areas: List[str]
    collected_info: Dict[str, Any] = field(default_factory=dict)
    completion_percentage: float = 0.0
    next_focus_area: Optional[str] = None


@dataclass
class ClarificationSession:
    """Extended session for proactive clarification"""

    # Required fields (no defaults)
    user_id: str
    agent_id: str
    mode: ClarificationMode

    # Optional fields (with defaults)
    session_id: Optional[str] = None
    proactive_request: Optional[ProactiveRequest] = None
    goal_context: Optional[GoalContext] = None
    plan_analysis: Optional[PlanAnalysis] = None
    questions_asked: int = 0
    max_questions: int = 10
    completion_criteria_met: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.session_id is None:
            self.session_id = str(f"ssn_{generate_nanoid()}")


@dataclass
class PlanningWorkflowRequest:
    """A request that involves planning workflow with information gathering"""

    workflow_type: PlanningWorkflowType
    planning_goal: str  # e.g., "book a trip to NYC"
    information_requests: List[str]  # e.g., ["check weather", "find fares"]
    original_message: str
    detected_tools: List[str] = field(default_factory=list)  # Tools mentioned/implied
    context_hints: Dict[str, Any] = field(default_factory=dict)  # Extracted context
    confidence: float = 0.0


@dataclass
class ToolExecutionResult:
    """Result from executing a tool in a planning workflow"""

    tool_name: str
    parameters: Dict[str, Any]
    result: Any
    execution_time: float
    success: bool
    error_message: Optional[str] = None
    planning_relevance: str = ""  # How this result relates to planning goal


@dataclass
class WorkflowSynthesis:
    """Synthesized insights from multiple tool results for planning"""

    planning_goal: str
    tool_results: List[ToolExecutionResult]
    key_insights: List[str]  # Main takeaways from the data
    options: List[Dict[str, Any]]  # Structured choices for user
    trade_offs: List[str]  # Key trade-offs identified
    recommendations: List[str]  # AI recommendations based on data
    follow_up_questions: List[str]  # Questions to continue planning
    confidence_score: float = 0.0


@dataclass
class PlanningWorkflowSession:
    """Active planning workflow session"""

    # Required fields (no defaults)
    user_id: str
    agent_id: str
    workflow_request: PlanningWorkflowRequest
    current_state: WorkflowState

    # Optional fields (with defaults)
    session_id: Optional[str] = None
    executed_tools: List[ToolExecutionResult] = field(default_factory=list)
    synthesis: Optional[WorkflowSynthesis] = None
    planning_context: Dict[str, Any] = field(default_factory=dict)
    questions_asked: int = 0
    max_questions: int = 10
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.session_id is None:
            self.session_id = str(f"ssn_{generate_nanoid()}")


@dataclass
class PlanningOption:
    """A specific option presented to user for decision-making"""

    option_id: str
    title: str
    description: str
    pros: List[str]
    cons: List[str]
    estimated_cost: Optional[str] = None
    estimated_time: Optional[str] = None
    risk_level: Optional[str] = None  # "low", "medium", "high"
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
