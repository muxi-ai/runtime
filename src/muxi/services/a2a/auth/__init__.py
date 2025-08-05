"""
A2A Authentication Module

This module provides SDK-based authentication for Agent-to-Agent communication.
"""

from .inbound import A2AInboundAuthenticator
from .outbound import A2AAuthManager

__all__ = [
    "A2AInboundAuthenticator",
    "A2AAuthManager",
]
