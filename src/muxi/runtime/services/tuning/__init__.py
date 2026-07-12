"""
Self-Improving Formation services (tuning).

Phase 1: the ``tuning:`` config surface, the scheduled digest loop over
the event spool, and the MUXI.md file contract. Phase 2 adds the tuner
step (detection, distillation, curation, pending flow, morning report).
"""

from .config import (
    DEFAULT_INTERVAL_HOURS,
    TuningConfig,
    TuningConfigError,
    parse_tuning_config,
)
from .muxi_md import MuxiMdFile
from .service import TuningService, yaml_declares_file_transport

__all__ = [
    "DEFAULT_INTERVAL_HOURS",
    "MuxiMdFile",
    "TuningConfig",
    "TuningConfigError",
    "TuningService",
    "parse_tuning_config",
    "yaml_declares_file_transport",
]
