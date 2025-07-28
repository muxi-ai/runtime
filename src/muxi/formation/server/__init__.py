"""
Formation Server Package

This package provides the HTTP API server for MUXI formations,
exposing formation management and user interaction capabilities.
"""

from .server import FormationServer

__all__ = ["FormationServer"]
