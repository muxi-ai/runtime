"""
A2A External Registry Client (SDK Implementation)

This module provides SDK-based client functionality for communicating with external
A2A registries. It handles agent registration, discovery, and health
monitoring across multiple external registries using the official A2A SDK.
"""

# Re-export the SDK implementation as the main registry client
from .registry_client_sdk import (
    A2ARegistryClientSDK as A2ARegistryClient,
    RegistryResponse,
    RegistryConfig
)

# Make the SDK client the default
__all__ = ['A2ARegistryClient', 'RegistryResponse', 'RegistryConfig']
