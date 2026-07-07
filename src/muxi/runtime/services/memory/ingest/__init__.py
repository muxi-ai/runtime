# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Ingestion Package
# Description:  POST /v1/memories accept path + tiered processing pipeline
# Role:         Public surface for memory ingestion (Memory Ingestion Phase 3a)
# Usage:        from muxi.runtime.services.memory.ingest import MemoryIngestionService
# Author:       Muxi Framework Team
# =============================================================================

from .classification import (
    CATEGORY_SPECS,
    CATEGORY_UNKNOWN,
    CONTENT_CATEGORIES,
    DEFAULT_FILTER_LEVEL,
    FILTER_LEVELS,
    FILTERED_CATEGORIES,
    build_category_specs,
    classify_content,
    is_filtered,
)
from .service import (
    DISPOSITION_FAILED,
    DISPOSITION_FILTERED,
    DISPOSITION_STORED,
    STATUS_ACCEPTED,
    STATUS_DUPLICATE,
    STATUS_INVALID,
    IngestionBusyError,
    IngestionUnavailableError,
    IngestItem,
    MemoryIngestionService,
    validate_item,
)

__all__ = [
    "CATEGORY_SPECS",
    "CATEGORY_UNKNOWN",
    "CONTENT_CATEGORIES",
    "DEFAULT_FILTER_LEVEL",
    "FILTER_LEVELS",
    "FILTERED_CATEGORIES",
    "build_category_specs",
    "classify_content",
    "is_filtered",
    "DISPOSITION_FAILED",
    "DISPOSITION_FILTERED",
    "DISPOSITION_STORED",
    "STATUS_ACCEPTED",
    "STATUS_DUPLICATE",
    "STATUS_INVALID",
    "IngestionBusyError",
    "IngestionUnavailableError",
    "IngestItem",
    "MemoryIngestionService",
    "validate_item",
]
