# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Distillery Package
# Description:  POST /v1/memories/distilled accept path + trust registry
# Role:         Public surface for distilled-batch intake (Phase 3b)
# Usage:        from muxi.runtime.services.memory.distillery import (
#                   MemoryDistilleryService,
#               )
# Author:       Muxi Framework Team
# =============================================================================

from .models import (
    PROVISIONAL_CONFIDENCE_CAP,
    QUOTA_RETENTION_DAYS,
    STATUS_ACTIVE,
    STATUS_REVOKED,
    TRUST_LEVELS,
    TRUST_PROVISIONAL,
    TRUST_VERIFIED,
    DistilleryQuotaCounter,
    RegisteredDistillery,
)
from .quotas import DistilleryQuotaStore
from .registry import DistilleryRegistry
from .service import (
    DISPOSITION_FAILED,
    DISPOSITION_PROJECTED,
    DISPOSITION_RECORDED,
    DISTILLERY_EVENT_TYPES,
    EMBEDDING_MODE_NONE,
    EMBEDDING_MODE_PRE_COMPUTED,
    HARD_MAX_BATCH_SIZE,
    SOURCE_DISTILLERY,
    DistilledEvent,
    DistilleryAuthError,
    DistilleryRateLimitError,
    DistilleryRevokedError,
    DistilleryUnavailableError,
    MemoryDistilleryService,
    user_id_in_scope,
    validate_distilled_event,
)
from .verification import (
    SIGNATURE_DOMAIN,
    SignatureVerificationError,
    check_timestamp,
    parse_public_key,
    signed_message,
    verify_signature,
)

__all__ = [
    "PROVISIONAL_CONFIDENCE_CAP",
    "QUOTA_RETENTION_DAYS",
    "STATUS_ACTIVE",
    "STATUS_REVOKED",
    "TRUST_LEVELS",
    "TRUST_PROVISIONAL",
    "TRUST_VERIFIED",
    "DistilleryQuotaCounter",
    "DistilleryQuotaStore",
    "RegisteredDistillery",
    "DistilleryRegistry",
    "DISPOSITION_FAILED",
    "DISPOSITION_PROJECTED",
    "DISPOSITION_RECORDED",
    "DISTILLERY_EVENT_TYPES",
    "EMBEDDING_MODE_NONE",
    "EMBEDDING_MODE_PRE_COMPUTED",
    "HARD_MAX_BATCH_SIZE",
    "SOURCE_DISTILLERY",
    "DistilledEvent",
    "DistilleryAuthError",
    "DistilleryRateLimitError",
    "DistilleryRevokedError",
    "DistilleryUnavailableError",
    "MemoryDistilleryService",
    "user_id_in_scope",
    "validate_distilled_event",
    "SIGNATURE_DOMAIN",
    "SignatureVerificationError",
    "check_timestamp",
    "parse_public_key",
    "signed_message",
    "verify_signature",
]
