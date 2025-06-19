"""
Validation Data Types

Core data structures used for validation operations across the muxi runtime system.
"""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ServiceDependency:
    """Represents a service dependency requirement."""

    name: str
    type: str  # 'package', 'service', 'config', 'file', 'env'
    required: bool = True
    minimum_version: Optional[str] = None
    description: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of dependency validation."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    missing_dependencies: List[ServiceDependency]
    circular_dependencies: List[List[str]]
