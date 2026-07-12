"""
Self-Improving Formation services (tuning).

The ``tuning:`` config surface, the scheduled loop over the event spool
(digest step + tune step), the MUXI.md/PENDING-MUXI.md file contract,
and the tuner's experiment memories.
"""

from .config import (
    DEFAULT_INTERVAL_HOURS,
    TuningConfig,
    TuningConfigError,
    parse_tuning_config,
)
from .experiments import ExperimentStore, learning_hash
from .muxi_md import MUXI_MD_MAX_BYTES, MuxiMdFile
from .service import TuningService, yaml_declares_file_transport
from .tuner import TunerStep

__all__ = [
    "DEFAULT_INTERVAL_HOURS",
    "ExperimentStore",
    "MUXI_MD_MAX_BYTES",
    "MuxiMdFile",
    "TunerStep",
    "TuningConfig",
    "TuningConfigError",
    "TuningService",
    "learning_hash",
    "parse_tuning_config",
    "yaml_declares_file_transport",
]
