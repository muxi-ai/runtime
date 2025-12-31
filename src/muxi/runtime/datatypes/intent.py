"""
Intent Detection Data Types

This module defines data types for the unified multilingual intent detection system.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class IntentType(Enum):
    """Types of intent that can be detected."""

    # Query routing
    QUERY_TYPE = "query_type"  # knowledge vs memory

    # Clarification
    CLARIFICATION_CATEGORY = "clarification_category"  # budget, timeline, etc.

    # Scheduling
    SCHEDULE_TYPE = "schedule_type"  # one-time vs recurring

    # Content analysis
    CONTENT_CATEGORY = "content_category"  # technical, explanatory, etc.

    # Error classification
    ERROR_TYPE = "error_type"  # format, size, permission, etc.

    # User intent
    LEARNING_INTENT = "learning_intent"  # tutorial, explanation, etc.
    PROACTIVE_REQUEST = "proactive_request"  # guided questioning, etc.

    # Message type
    MESSAGE_TYPE = "message_type"  # request, query, consultation, etc.


class IntentResult(BaseModel):
    """Result of intent detection."""

    intent_type: IntentType = Field(description="Type of intent detected")
    intent: str = Field(description="Detected intent value")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    reasoning: Optional[str] = Field(None, description="Explanation for the detection")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    # For clarification intents
    extracted_question: Optional[str] = Field(None, description="Extracted question if applicable")

    # For multi-option intents
    alternatives: List[Dict[str, float]] = Field(
        default_factory=list, description="Alternative intents with confidence scores"
    )


class QueryType(str, Enum):
    """Types of queries for routing."""

    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class ClarificationCategory(str, Enum):
    """Categories for clarification questions."""

    BUDGET = "budget"
    TIMELINE = "timeline"
    PREFERENCES = "preferences"
    REQUIREMENTS = "requirements"
    SCOPE = "scope"
    LOCATION = "location"
    OTHER = "other"
    NONE = "none"


class ScheduleType(str, Enum):
    """Types of schedule requests."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"
    UNCLEAR = "unclear"


class ContentCategory(str, Enum):
    """Categories for content analysis."""

    TECHNICAL = "technical"
    EXPLANATORY = "explanatory"
    INSTRUCTIONAL = "instructional"
    CONVERSATIONAL = "conversational"
    MIXED = "mixed"


class ErrorCategory(str, Enum):
    """Categories for error classification."""

    FORMAT = "format"
    SIZE = "size"
    PERMISSION = "permission"
    NETWORK = "network"
    TIMEOUT = "timeout"
    PARSING = "parsing"
    MEMORY = "memory"
    API = "api"
    UNKNOWN = "unknown"


class IntentDetectionContext(BaseModel):
    """Context for intent detection."""

    # Available options for the intent
    options: Optional[List[str]] = Field(None, description="Valid intent options")

    # Recent conversation context
    recent_messages: Optional[List[Dict[str, str]]] = Field(
        None, description="Recent conversation messages for context"
    )

    # User information
    user_language: Optional[str] = Field(None, description="User's preferred language")
    user_timezone: Optional[str] = Field(None, description="User's timezone")

    # Additional context
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
