"""
Coding-agent delegation (headless CLIs).

MUXI formations delegate coding tasks to external headless coding CLIs
(claude-code, droid, ...) as fire-and-collect background work: the
built-in ``delegate_coding`` tool spawns the developer's chosen CLI as a
tracked subprocess, returns a job handle immediately, and re-enters the
conversation when the run completes.

MUXI ships the mechanism only: adapters are declarative content (bundled
dormant templates, formation-local shadowing, inline escape hatch);
installation, auth, and sandboxing are the developer's business; vendor
taxonomies pass through opaquely (``extra_args``, opaque ``model``).
"""

from .adapter import ParsedOutput, build_command, parse_output, parse_stream_json_line
from .config import (
    BUILTIN_ADAPTERS_DIR,
    CLEANUP_MODES,
    OUTPUT_MODES,
    AdapterConfig,
    CodingConfig,
    CodingConfigError,
    find_workdir_root,
    list_bundled_adapters,
    parse_coding_config,
    resolve_adapter_template,
    validate_coding_runtime,
)
from .models import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_ORPHANED,
    STATUS_RUNNING,
    STATUS_TIMED_OUT,
    TERMINAL_STATUSES,
    CodingDelegation,
)
from .service import DelegationJob, DelegationService

__all__ = [
    "AdapterConfig",
    "BUILTIN_ADAPTERS_DIR",
    "CLEANUP_MODES",
    "CodingConfig",
    "CodingConfigError",
    "CodingDelegation",
    "DelegationJob",
    "DelegationService",
    "OUTPUT_MODES",
    "ParsedOutput",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_ORPHANED",
    "STATUS_RUNNING",
    "STATUS_TIMED_OUT",
    "TERMINAL_STATUSES",
    "build_command",
    "find_workdir_root",
    "list_bundled_adapters",
    "parse_coding_config",
    "parse_output",
    "parse_stream_json_line",
    "resolve_adapter_template",
    "validate_coding_runtime",
]
