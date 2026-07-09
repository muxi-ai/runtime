# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Event Substrate Package
# Description:  Immutable event log underneath every memory projection
# Role:         Public surface for the memory event substrate
# Usage:        from muxi.runtime.services.memory.events import MemoryEventService
# Author:       Muxi Framework Team
# =============================================================================

from .decay import DecaySettings
from .models import (
    EVENT_ARTIFACT_SAVED,
    EVENT_FACT_CONTRADICTED,
    EVENT_FACT_EXTRACTED,
    EVENT_GRAPH_EXTRACTED,
    EVENT_INGESTION_FILTERED,
    EVENT_INTERACTION_TURN,
    EVENT_LESSON_RECORDED,
    EVENT_LOG_ENTRY,
    EVENT_MEMORY_INGESTED,
    EVENT_USER_DELETION,
    MemoryEvent,
    ProjectionCheckpoint,
    append_event_id,
)
from .projectors import (
    ArtifactMetadataProjector,
    CaptainsLogProjector,
    FlatFactProjector,
    KnowledgeGraphProjector,
    apply_fact_event,
)
from .service import MemoryEventService
from .storage import MemoryEventStorage

__all__ = [
    "EVENT_ARTIFACT_SAVED",
    "EVENT_FACT_CONTRADICTED",
    "EVENT_FACT_EXTRACTED",
    "EVENT_GRAPH_EXTRACTED",
    "EVENT_INGESTION_FILTERED",
    "EVENT_INTERACTION_TURN",
    "EVENT_LESSON_RECORDED",
    "EVENT_LOG_ENTRY",
    "EVENT_MEMORY_INGESTED",
    "EVENT_USER_DELETION",
    "MemoryEvent",
    "ProjectionCheckpoint",
    "append_event_id",
    "ArtifactMetadataProjector",
    "CaptainsLogProjector",
    "DecaySettings",
    "FlatFactProjector",
    "KnowledgeGraphProjector",
    "apply_fact_event",
    "MemoryEventService",
    "MemoryEventStorage",
]
