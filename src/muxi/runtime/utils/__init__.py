"""
Utilities for the MUXI Framework.

This module provides various utility functions used throughout the framework.
"""

# Re-export utility functions
from .id_generator import get_default_nanoid
from .version import get_version
from .document import load_document, chunk_text
from .dependency_validator import DependencyValidator
from .async_operation_manager import (
    AsyncOperationManager,
    get_operation_manager,
    set_timeout_config,
    execute_with_timeout,
)
from .retry_manager import (
    RetryManager,
    get_retry_manager,
    set_default_retry_config,
    retry_network_operation,
    retry_api_call,
    classify_error_as_transient,
)

__all__ = [
    "get_default_nanoid",
    "get_version",
    "load_document",
    "chunk_text",
    "DependencyValidator",
    "AsyncOperationManager",
    "get_operation_manager",
    "set_timeout_config",
    "execute_with_timeout",
    "RetryManager",
    "get_retry_manager",
    "set_default_retry_config",
    "retry_network_operation",
    "retry_api_call",
    "classify_error_as_transient",
]
