"""Artifact Memory (Phase 1): persistent capture of produced work.

Everything agents produce -- generated files today, explicit saves and
RCE outputs later -- is captured as a gzipped, encrypted blob with a
metadata row in the ``artifacts`` table. Phase 2 (manifest injection,
retrieval tools, semantic search) waits on the memory-revamp Knowledge
Index layer and is intentionally absent here.
"""

from .models import FORMATION_INSTANCE_ID_KEY, Artifact, SystemConfig
from .service import ArtifactMemoryService, ArtifactMemorySettings, parse_artifacts_config
from .storage import ArtifactMemoryStorage

__all__ = [
    "Artifact",
    "ArtifactMemoryService",
    "ArtifactMemorySettings",
    "ArtifactMemoryStorage",
    "FORMATION_INSTANCE_ID_KEY",
    "SystemConfig",
    "parse_artifacts_config",
]
